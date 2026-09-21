"""
app.py - Main Flask Application Entry Point

Provides REST API and UI endpoints:
- GET /: Serves the Web Chat Interface
- GET /api/health: Health check status
- POST /api/chat: Custom AI Agent chat endpoint with RAG tool calling & memory
"""

from flask import Flask, request, jsonify, render_template
from openai import AuthenticationError, RateLimitError, APIError

import config
from services.agent_service import AgentService

app = Flask(__name__)
agent_service = AgentService()


@app.route("/", methods=["GET"])
def index():
    """Serves the main chat application UI."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify backend service status."""
    return jsonify({"status": "ok"}), 200


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Chat endpoint for enterprise assistant.
    Expects JSON body: { "question": "...", "history": [...] }
    Returns JSON body: { "answer": "...", "sources": [...] }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or "question" not in data:
        return (
            jsonify({"error": "Invalid request. JSON body must contain a 'question' string field."}),
            400,
        )

    raw_question = data.get("question")
    raw_history = data.get("history", [])

    try:
        # Validate question
        validated_question = agent_service.validate_question(raw_question)

        # Run custom agent loop with conversation history
        result = agent_service.answer_question(validated_question, history=raw_history)

        return jsonify(result), 200

    except ValueError as val_err:
        return jsonify({"error": str(val_err)}), 400
    except AuthenticationError:
        return (
            jsonify({"error": "Authentication failed with Azure AI Foundry. Please check your API keys."}),
            500,
        )
    except RateLimitError:
        return (
            jsonify({"error": "Azure OpenAI rate limit exceeded. Please try again in a few moments."}),
            429,
        )
    except APIError as api_err:
        return jsonify({"error": f"Azure OpenAI API error: {str(api_err)}"}), 500
    except Exception as exc:
        return jsonify({"error": f"Internal server error: {str(exc)}"}), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
