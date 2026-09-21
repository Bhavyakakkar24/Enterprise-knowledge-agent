"""
app.py - Main Flask Application Entry Point

Provides REST API and UI endpoints:
- GET /: Serves the Web Chat Interface
- GET /api/health: Health check status
- POST /api/chat: Custom AI Agent chat endpoint with RAG tool calling & memory
"""

import logging
import time
from flask import Flask, request, jsonify, render_template
from openai import AuthenticationError, RateLimitError, APIError, APITimeoutError
from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError, HttpResponseError

import config
from services.agent_service import AgentService

# Configure structured application logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")

app = Flask(__name__)
agent_service = AgentService()


@app.route("/", methods=["GET"])
def index():
    """Serves the main chat application UI."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify backend service status."""
    logger.info("GET /api/health - Status: 200")
    return jsonify({"status": "ok"}), 200


@app.route("/api/chat", methods=["POST"])
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
    app.run(
        host="127.0.0.1",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
