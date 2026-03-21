"""
Compatibility shim for core modules that use the old get_secret / get_supabase_client interface.
Maps calls to the new Pydantic Settings-based config.
"""
import threading

from ..config import get_settings

_supabase_client = None
_supabase_lock = threading.Lock()


def get_secret(section: str, key: str):
    """Compatibility shim for core modules that use the old get_secret interface."""
    settings = get_settings()
    mapping = {
        ("supabase", "url"): settings.supabase_url,
        ("supabase", "key"): settings.supabase_key,
        ("anthropic", "api_key"): settings.anthropic_api_key,
        ("google", "api_key"): settings.google_address_validation_api_key,
        ("zapier", "webhook_url"): settings.zapier_webhook_url,
        ("app", "bypass_pin"): settings.bypass_pin,
    }
    return mapping.get((section, key)) or None


def get_supabase_client():
    """Get shared Supabase client."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    with _supabase_lock:
        if _supabase_client is not None:
            return _supabase_client

        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_key:
            return None
        try:
            from supabase import create_client
            _supabase_client = create_client(settings.supabase_url, settings.supabase_key)
            return _supabase_client
        except Exception:
            return None
