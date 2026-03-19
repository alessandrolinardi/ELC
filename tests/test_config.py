import os
import pytest


def test_get_secret_from_env_var():
    """get_secret falls back to env vars when Streamlit secrets unavailable."""
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    from src.config import get_secret
    result = get_secret("supabase", "url")
    assert result == "https://test.supabase.co"
    del os.environ["SUPABASE_URL"]


def test_get_secret_returns_none_for_unknown():
    """get_secret returns None for unmapped keys."""
    from src.config import get_secret
    result = get_secret("unknown", "key")
    assert result is None


def test_get_supabase_client_returns_none_without_config():
    """get_supabase_client returns None when secrets are missing."""
    from src.config import get_supabase_client
    for key in ["SUPABASE_URL", "SUPABASE_KEY"]:
        os.environ.pop(key, None)
    result = get_supabase_client()
    assert result is None
