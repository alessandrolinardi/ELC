"""
Centralized configuration and secrets access.
Works with both Streamlit secrets (local dev) and environment variables (Render).
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SECRET_MAP = {
    ("supabase", "url"): "SUPABASE_URL",
    ("supabase", "key"): "SUPABASE_KEY",
    ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
    ("google", "api_key"): "GOOGLE_ADDRESS_VALIDATION_API_KEY",
    ("zapier", "webhook_url"): "ZAPIER_WEBHOOK_URL",
    ("app", "bypass_pin"): "BYPASS_PIN",
}

_supabase_client = None


def get_secret(section: str, key: str) -> Optional[str]:
    """Get secret from Streamlit secrets or environment variables."""
    # Try Streamlit secrets first (for local dev)
    try:
        import streamlit as st
        return st.secrets[section][key]
    except (KeyError, FileNotFoundError, ImportError, AttributeError):
        pass

    # Fall back to env vars via explicit mapping (Render)
    env_key = SECRET_MAP.get((section, key))
    if env_key:
        return os.environ.get(env_key)
    return None


def get_supabase_client():
    """Get shared Supabase client. Returns None if not configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client
        url = get_secret("supabase", "url")
        key = get_secret("supabase", "key")
        if not url or not key:
            return None
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None
