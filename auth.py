"""
auth.py - Microsoft Entra ID Authentication & Authorization Module

Provides MSAL ConfidentialClientApplication integration, authorization code flow helpers,
session validation, and email allow-list enforcement.
"""

import logging
from functools import wraps
import msal
from flask import session, redirect, url_for, request, jsonify

import config

logger = logging.getLogger("auth")


def get_msal_client() -> msal.ConfidentialClientApplication:
    """Instantiates and returns the MSAL ConfidentialClientApplication."""
    return msal.ConfidentialClientApplication(
        client_id=config.ENTRA_CLIENT_ID,
        client_credential=config.ENTRA_CLIENT_SECRET,
        authority=config.ENTRA_AUTHORITY,
    )


def initiate_auth_flow(redirect_uri: str = None) -> dict:
    """
    Initiates MSAL authorization code flow and returns the auth flow metadata dict.
    The returned dict includes 'auth_uri', 'state', and PKCE / nonce parameters.
    Forces Microsoft account chooser dialog (prompt='select_account').
    """
    client = get_msal_client()
    return client.initiate_auth_code_flow(
        scopes=config.ENTRA_SCOPES,
        redirect_uri=redirect_uri or config.ENTRA_REDIRECT_URI,
        prompt="select_account",
    )



def acquire_token_by_auth_flow(auth_flow: dict, request_args: dict) -> dict:
    """
    Exchanges the authorization code for tokens using MSAL flow state.
    Returns token response dictionary containing 'id_token_claims' or 'error' on failure.
    """
    client = get_msal_client()
    return client.acquire_token_by_auth_code_flow(
        auth_code_flow=auth_flow,
        auth_response=request_args,
    )


def extract_user_info(id_token_claims: dict) -> dict:
    """
    Safely extracts email and display name from ID token claims.
    Supports email, preferred_username, upn, and unique_name claims.
    """
    if not id_token_claims or not isinstance(id_token_claims, dict):
        return {"email": "", "name": ""}

    email = (
        id_token_claims.get("email")
        or id_token_claims.get("preferred_username")
        or id_token_claims.get("upn")
        or id_token_claims.get("unique_name")
        or ""
    ).strip().lower()

    name = (
        id_token_claims.get("name")
        or id_token_claims.get("preferred_username")
        or id_token_claims.get("email")
        or "Employee"
    ).strip()

    return {"email": email, "name": name}


def is_email_allowed(email: str) -> bool:
    """
    Verifies whether the provided email address is authorized in the allow-list.
    Comparison is case-insensitive and stripped of whitespace.
    """
    if not email:
        return False
    clean_email = email.strip().lower()
    return clean_email in config.ALLOWED_USER_EMAILS


def login_required(f):
    """
    Decorator to protect routes requiring an authenticated and allow-listed session.
    Redirects browser requests to /login and returns 401 JSON for /api/* requests.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get("user")
        if not user or not isinstance(user, dict) or not user.get("email"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized. Please log in first."}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function
