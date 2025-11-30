import os
from functools import wraps
from flask import request, jsonify, g
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)

_supabase_client = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables must be set")

        _supabase_client = create_client(supabase_url, supabase_key)

    return _supabase_client


def get_auth_token() -> str | None:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def validate_token(token: str) -> dict | None:
    try:
        # Verify token with Supabase
        supabase = get_supabase()
        user = supabase.auth.get_user(token)
        return user.user if user else None
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return None


def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_auth_token()

        if not token:
            return jsonify({"error": "Missing authorization token"}), 401

        user = validate_token(token)

        if not user:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Attach user to Flask request context
        g.current_user = {
            "id": user.id,
            "email": user.email,
            "user_metadata": user.user_metadata or {},
        }

        return f(*args, **kwargs)

    return decorated_function


def get_current_user() -> dict | None:
    return getattr(g, "current_user", None)
