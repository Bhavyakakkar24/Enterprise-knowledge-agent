"""
config.py - Environment & Application Configuration

Loads and validates environment variables from .env using python-dotenv.
Raises clear errors for missing or empty configuration without exposing secret values.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")

# List of required environment variables to validate on startup
# Note: AZURE_OPENAI_API_VERSION and FLASK_DEBUG are omitted here to support flexible defaults.
REQUIRED_VARS = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DIMENSIONS",
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_STORAGE_CONTAINER_NAME",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_API_KEY",
    "AZURE_SEARCH_INDEX_NAME",
    "FLASK_PORT",
    "FLASK_SECRET_KEY",
    "ENTRA_CLIENT_ID",
    "ENTRA_CLIENT_SECRET",
    "ENTRA_TENANT_ID",
    "ALLOWED_USER_EMAILS",
]

# Identify any missing or empty required variables
missing_vars = [
    var for var in REQUIRED_VARS
    if not os.getenv(var) or not os.getenv(var).strip()
]

if missing_vars:
    raise ValueError(
        f"Missing or empty required environment variable(s): {', '.join(missing_vars)}. "
        f"Please verify your .env file."
    )

# Azure OpenAI / Foundry Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "").strip() or None
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "").strip()
AZURE_OPENAI_EMBEDDING_DIMENSIONS = int(os.getenv("AZURE_OPENAI_EMBEDDING_DIMENSIONS", "1536"))

# Azure Blob Storage Configuration
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "").strip()

# Azure AI Search Configuration
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_API_KEY", "").strip()
AZURE_SEARCH_INDEX_NAME = os.getenv("AZURE_SEARCH_INDEX_NAME", "").strip()

# Flask Application Configuration
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").strip().lower() in ("true", "1", "yes")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "").strip()

# Microsoft Entra ID (Azure AD) Authentication Configuration
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "").strip()
ENTRA_CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET", "").strip()
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "").strip()
ENTRA_REDIRECT_URI = os.getenv("ENTRA_REDIRECT_URI", "").strip() or f"http://localhost:{FLASK_PORT}/auth/callback"
ENTRA_AUTHORITY = f"https://login.microsoftonline.com/{ENTRA_TENANT_ID}"
ENTRA_SCOPES = ["User.Read"]


# Allowed user emails list (stripped and lowercased for case-insensitive verification)
ALLOWED_USER_EMAILS = [
    email.strip().lower()
    for email in os.getenv("ALLOWED_USER_EMAILS", "").split(",")
    if email.strip()
]

