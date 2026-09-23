"""
app.py - Main Flask Application Entry Point

Provides REST API and UI endpoints:
- GET /: Serves the Marketing Landing Page
- GET /chat: Serves the Authenticated Web Chat Interface
- GET /login: Initiates Microsoft Entra ID OAuth 2.0 Login
- GET /auth/callback: Handles Entra ID callback, token exchange, and allow-list check
- GET /logout: Clears session and redirects to landing page
- GET /api/health: Health check status (public)
- POST /api/chat: Custom AI Agent chat endpoint with RAG tool calling & memory (login required)
"""

import os
import logging
import time
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from openai import AuthenticationError, RateLimitError, APIError, APITimeoutError
from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError, HttpResponseError

import config
from auth import (
    initiate_auth_flow,
    acquire_token_by_auth_flow,
    extract_user_info,
    is_email_allowed,
    login_required,
)
from services.agent_service import AgentService

# Configure structured application logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx2").setLevel(logging.WARNING)
logger = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

agent_service = AgentService()


@app.route("/", methods=["GET"])
def landing_page():
    """Serves the marketing and overview landing page for all visitors."""
    return render_template("landing.html", user=session.get("user"))


@app.route("/chat", methods=["GET"])
@login_required
def chat_page():
    """Serves the authenticated internal chat application UI."""
    return render_template("index.html", user=session.get("user"))


@app.route("/login", methods=["GET"])
def login():
    """Initiates Microsoft Entra ID authorization code flow."""
    try:
        auth_flow = initiate_auth_flow()
        session["auth_flow"] = auth_flow
        return redirect(auth_flow["auth_uri"])
    except Exception as exc:
        logger.error(f"Error initiating MSAL login flow: {exc}", exc_info=True)
        return render_template(
            "auth_error.html",
            error_description="Unable to initiate login with Microsoft Entra ID. Please check server configuration.",
        )


@app.route("/auth/callback", methods=["GET"])
def auth_callback():
    """Handles the OAuth2 authorization code callback from Microsoft Entra ID."""
    # Handle Microsoft identity provider error query parameters (e.g. user cancelled)
    if "error" in request.args:
        error_code = request.args.get("error")
        error_description = request.args.get(
            "error_description", "Authentication was cancelled or failed."
        )
        logger.warning(f"Entra ID callback error: {error_code} - {error_description}")
        return render_template(
            "auth_error.html",
            error_code=error_code,
            error_description=error_description,
        )

    auth_flow = session.pop("auth_flow", None)
    if not auth_flow:
        logger.warning("Auth callback received without valid session auth_flow.")
        return render_template(
            "auth_error.html",
            error_description="Authentication session has expired or is invalid. Please try signing in again.",
        )

    try:
        result = acquire_token_by_auth_flow(auth_flow, request.args.to_dict())
        if "error" in result:
            error_code = result.get("error")
            error_description = result.get(
                "error_description", "Failed to acquire authentication token."
            )
            logger.error(f"MSAL token acquisition error: {error_code} - {error_description}")
            return render_template(
                "auth_error.html",
                error_code=error_code,
                error_description=error_description,
            )

        id_token_claims = result.get("id_token_claims", {})
        user_info = extract_user_info(id_token_claims)
        user_email = user_info.get("email", "").lower()

        if not user_email or not is_email_allowed(user_email):
            logger.warning(f"Unauthorized access attempt by: '{user_email}'")
            return render_template("access_denied.html", email=user_email)

        # Authorized employee session
        session["user"] = user_info
        logger.info(f"User authenticated successfully: {user_email} ({user_info.get('name')})")
        return redirect(url_for("chat_page"))

    except Exception as exc:
        logger.error(f"Exception during auth callback processing: {exc}", exc_info=True)
        return render_template(
            "auth_error.html",
            error_description="An unexpected error occurred during authentication. Please try again.",
        )


@app.route("/logout", methods=["GET"])
def logout():
    """Clears the user session and redirects to the landing page."""
    user = session.get("user", {})
    if user:
        logger.info(f"User logged out: {user.get('email')}")
    session.clear()
    return redirect(url_for("landing_page"))


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify backend service status (Public)."""
    logger.info("GET /api/health - Status: 200")
    return jsonify({"status": "ok"}), 200


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    """
    Chat endpoint for enterprise assistant.
    Expects JSON body: { "question": "...", "history": [...] }
    Returns JSON body: { "answer": "...", "sources": [...] }
    """
    start_time = time.perf_counter()
    data = request.get_json(silent=True)

    if not data or not isinstance(data, dict) or "question" not in data:
        duration = time.perf_counter() - start_time
        logger.warning(f"POST /api/chat - Status: 400 - Duration: {duration:.2f}s - Reason: Missing question field")
        return (
            jsonify({"error": "Invalid request. JSON body must contain a 'question' string field."}),
            400,
        )

    raw_question = data.get("question")
    raw_history = data.get("history", [])

    # Format truncated question for safe logging (max 80 chars)
    if isinstance(raw_question, str):
        cleaned_for_log = raw_question.strip().replace("\n", " ")
        trunc_question = cleaned_for_log[:80] + ("..." if len(cleaned_for_log) > 80 else "")
    else:
        trunc_question = "<non-string-input>"

    logger.info(f"Incoming POST /api/chat - Question: '{trunc_question}'")

    try:
        # Validate question
        validated_question = agent_service.validate_question(raw_question)

        # Run custom agent loop with conversation history
        result = agent_service.answer_question(validated_question, history=raw_history)

        duration = time.perf_counter() - start_time
        tool_calls = result.get("tool_calls_count", 0)

        logger.info(
            f"Completed POST /api/chat - Status: 200 - Duration: {duration:.2f}s - Tool Calls: {tool_calls}"
        )

        return (
            jsonify({
                "answer": result.get("answer", ""),
                "sources": result.get("sources", []),
            }),
            200,
        )

    except ValueError as val_err:
        duration = time.perf_counter() - start_time
        logger.warning(
            f"POST /api/chat - Status: 400 - Duration: {duration:.2f}s - Validation Error: {str(val_err)}"
        )
        return jsonify({"error": str(val_err)}), 400

    except (RateLimitError,) as rate_err:
        duration = time.perf_counter() - start_time
        logger.warning(
            f"POST /api/chat - Status: 429 - Duration: {duration:.2f}s - Rate limit exceeded"
        )
        return (
            jsonify({"error": "Azure AI rate limit exceeded. Please wait a moment and try again."}),
            429,
        )

    except (AuthenticationError, ClientAuthenticationError):
        duration = time.perf_counter() - start_time
        logger.error(
            f"POST /api/chat - Status: 500 - Duration: {duration:.2f}s - Authentication failure"
        )
        return (
            jsonify({"error": "Authentication failed with Azure AI services. Please check server API keys."}),
            500,
        )

    except (APITimeoutError, ServiceRequestError, TimeoutError):
        duration = time.perf_counter() - start_time
        logger.error(
            f"POST /api/chat - Status: 504 - Duration: {duration:.2f}s - Request timeout"
        )
        return (
            jsonify({"error": "Request to Azure AI services timed out. Please try again."}),
            504,
        )

    except HttpResponseError as resp_err:
        duration = time.perf_counter() - start_time
        if resp_err.status_code == 429:
            logger.warning(f"POST /api/chat - Status: 429 - Duration: {duration:.2f}s - Azure Search Rate Limit")
            return jsonify({"error": "Azure AI Search rate limit exceeded. Please try again in a moment."}), 429
        elif resp_err.status_code in (401, 403):
            logger.error(f"POST /api/chat - Status: 500 - Duration: {duration:.2f}s - Azure Search Auth Failure")
            return jsonify({"error": "Authentication failed with Azure Search service. Please check API keys."}), 500
        else:
            logger.error(f"POST /api/chat - Status: 502 - Duration: {duration:.2f}s - Azure Service Error HTTP {resp_err.status_code}")
            return jsonify({"error": "Azure Search service encountered an error. Please try again."}), 502

    except APIError as api_err:
        duration = time.perf_counter() - start_time
        logger.error(
            f"POST /api/chat - Status: 500 - Duration: {duration:.2f}s - OpenAI API error"
        )
        return jsonify({"error": "An error occurred communicating with the Azure OpenAI model."}), 500

    except Exception as exc:
        duration = time.perf_counter() - start_time
        logger.error(
            f"POST /api/chat - Status: 500 - Duration: {duration:.2f}s - Unhandled Exception: {type(exc).__name__}",
            exc_info=True,
        )
        return jsonify({"error": "An unexpected internal server error occurred. Please try again."}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", config.FLASK_PORT))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=config.FLASK_DEBUG,
    )

