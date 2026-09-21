"""
app.py - Main Flask Application Entry Point

Initializes minimal Flask REST API with health check endpoint.
"""

from flask import Flask, jsonify
import config

app = Flask(__name__)


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify backend service status."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG
    )
