"""
Security Module for ELC Tools
Implements persistent rate limiting using Supabase with a simple 12-hour window.

Uses Supabase for reliable persistence across deploys and instances.
"""

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

import streamlit as st

logger = logging.getLogger(__name__)

# Security limits - simplified to 12-hour window
MAX_VALIDATIONS_PER_12H = 1000  # Maximum validations per 12-hour window (global)
MIN_SECONDS_BETWEEN_REQUESTS = 3  # Minimum gap between requests


def _get_supabase_client():
    """Get Supabase client using Streamlit secrets."""
    try:
        from supabase import create_client

        if "supabase" not in st.secrets:
            logger.warning("Supabase not configured in secrets")
            return None

        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]

        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


def _get_current_period() -> Tuple[str, str, datetime]:
    """
    Get current 12-hour period identifier.
    Returns (date_str, period_id, period_end_time)

    Period ID format: "2026-02-03-AM" or "2026-02-03-PM"
    AM = 00:00-11:59, PM = 12:00-23:59
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if now.hour < 12:
        period_id = f"{today}-AM"
        period_end = now.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        period_id = f"{today}-PM"
        period_end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    return today, period_id, period_end


def get_client_ip() -> str:
    """
    Get client IP address from Streamlit.
    Uses multiple fallback methods for reliability.
    """
    # Method 1: Try Streamlit's experimental get_script_run_ctx
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx and hasattr(ctx, 'session_id'):
            return f"session_{ctx.session_id[:16]}"
    except (ImportError, AttributeError):
        pass

    # Method 2: Try st.context.headers (newer Streamlit versions)
    try:
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            headers = st.context.headers
            if headers:
                for header in ['X-Forwarded-For', 'X-Real-IP', 'CF-Connecting-IP']:
                    ip = headers.get(header, '')
                    if ip:
                        return ip.split(',')[0].strip()
    except (AttributeError, TypeError):
        pass

    # Method 3: Use session state with persistent ID
    try:
        if '_client_id' not in st.session_state:
            st.session_state._client_id = str(uuid.uuid4())[:16]
        return f"client_{st.session_state._client_id}"
    except Exception:
        pass

    # Final fallback
    return f"anon_{hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:8]}"


def _get_period_usage(client, period_id: str) -> int:
    """Get total usage for the current 12-hour period (global)."""
    try:
        response = client.table("rate_limits").select("request_count").eq(
            "hour", period_id
        ).execute()

        total = sum(r.get("request_count", 0) for r in (response.data or []))
        logger.debug(f"Period {period_id} usage: {total}")
        return total
    except Exception as e:
        logger.error(f"Error getting period usage: {e}")
        return 0


def _get_or_create_record(client, period_id: str) -> dict:
    """Get or create a rate limit record for the current period."""
    # Use a fixed identifier for global tracking
    global_id = "global"
    today = period_id.rsplit("-", 1)[0]  # Extract date from period_id

    try:
        response = client.table("rate_limits").select("*").eq(
            "ip_hash", global_id
        ).eq("hour", period_id).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]

        # Create new record
        new_record = {
            "ip_hash": global_id,
            "date": today,
            "hour": period_id,
            "request_count": 0,
            "failed_attempts": 0,
            "banned_until": None,
            "last_request": None
        }

        insert_response = client.table("rate_limits").insert(new_record).execute()
        if insert_response.data:
            return insert_response.data[0]

        return new_record
    except Exception as e:
        logger.error(f"Error getting/creating record: {e}")
        return None


def check_rate_limit(ip: str, rows_to_validate: int) -> Tuple[bool, str, dict]:
    """
    Check if request is within rate limits.

    Returns:
        (is_allowed, message, usage_info)
    """
    client = _get_supabase_client()
    if client is None:
        logger.warning("Supabase unavailable - rate limiting disabled")
        return True, "OK", {}

    today, period_id, period_end = _get_current_period()

    # Get current period usage
    current_usage = _get_period_usage(client, period_id)

    # Check if we'd exceed the limit
    if current_usage + rows_to_validate > MAX_VALIDATIONS_PER_12H:
        remaining = MAX_VALIDATIONS_PER_12H - current_usage
        time_left = period_end - datetime.now()
        hours_left = int(time_left.total_seconds() // 3600)
        mins_left = int((time_left.total_seconds() % 3600) // 60)

        return False, f"Limite raggiunto ({current_usage}/{MAX_VALIDATIONS_PER_12H}). Riprova tra {hours_left}h {mins_left}m.", {}

    # Get the record to check last_request time
    record = _get_or_create_record(client, period_id)
    if record and record.get("last_request"):
        try:
            last_request_str = record["last_request"]
            if isinstance(last_request_str, str):
                last_request = datetime.fromisoformat(last_request_str.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                last_request = last_request_str
            elapsed = (datetime.now() - last_request).total_seconds()
            if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
                wait_time = int(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
                return False, f"Attendi {wait_time} secondi prima della prossima validazione.", {}
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing last_request: {e}")

    usage_info = {
        "current_usage": current_usage,
        "limit": MAX_VALIDATIONS_PER_12H,
        "remaining": MAX_VALIDATIONS_PER_12H - current_usage,
        "period_id": period_id
    }

    return True, "OK", usage_info


def record_usage(ip: str, rows_validated: int):
    """Record API usage after successful validation."""
    client = _get_supabase_client()
    if client is None:
        return

    today, period_id, _ = _get_current_period()

    try:
        record = _get_or_create_record(client, period_id)
        if record is None:
            return

        new_count = record.get("request_count", 0) + rows_validated

        client.table("rate_limits").update({
            "request_count": new_count,
            "last_request": datetime.now().isoformat()
        }).eq("ip_hash", "global").eq("hour", period_id).execute()

        logger.debug(f"Recorded {rows_validated} validations, total now: {new_count}")
    except Exception as e:
        logger.error(f"Error recording usage: {e}")


def record_failed_attempt(ip: str):
    """Record a failed attempt (kept for API compatibility)."""
    pass  # Simplified - no longer tracking failed attempts


def get_usage_stats(ip: str) -> dict:
    """Get current usage statistics for display."""
    client = _get_supabase_client()

    today, period_id, period_end = _get_current_period()

    default_stats = {
        "current_usage": 0,
        "limit": MAX_VALIDATIONS_PER_12H,
        "remaining": MAX_VALIDATIONS_PER_12H,
        "period_id": period_id,
        "period_end": period_end.strftime("%H:%M")
    }

    if client is None:
        return default_stats

    try:
        current_usage = _get_period_usage(client, period_id)

        return {
            "current_usage": current_usage,
            "limit": MAX_VALIDATIONS_PER_12H,
            "remaining": MAX_VALIDATIONS_PER_12H - current_usage,
            "period_id": period_id,
            "period_end": period_end.strftime("%H:%M")
        }
    except Exception as e:
        logger.error(f"Error getting usage stats: {e}")
        return default_stats


def validate_excel_content(df) -> Tuple[bool, Optional[str]]:
    """
    Validate Excel content for security issues.
    """
    MAX_CELL_LENGTH = 1000
    SUSPICIOUS_PATTERNS = ['=CMD(', '=SYSTEM(', '=EXEC(', '|', '=HYPERLINK(', '=IMPORTXML(']

    try:
        for col in df.columns:
            for idx, value in df[col].items():
                if not isinstance(value, str):
                    continue

                if len(value) > MAX_CELL_LENGTH:
                    return False, f"Cella troppo lunga nella colonna '{col}' (max {MAX_CELL_LENGTH} caratteri)"

                value_upper = value.upper()
                for pattern in SUSPICIOUS_PATTERNS:
                    if pattern in value_upper:
                        return False, f"Contenuto non valido rilevato nella colonna '{col}'"
    except Exception as e:
        logger.warning(f"Error validating Excel content: {e}")

    return True, None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    import re
    import os
    sanitized = re.sub(r'[/\\:\x00]', '_', filename)
    sanitized = sanitized.lstrip('.')
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    return sanitized or "unnamed"


def cleanup_old_records():
    """Clean up rate limit records older than 7 days."""
    client = _get_supabase_client()
    if client is None:
        return

    try:
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        client.table("rate_limits").delete().lt("date", cutoff_date).execute()
        logger.info(f"Cleaned up records older than {cutoff_date}")
    except Exception as e:
        logger.error(f"Error cleaning up old records: {e}")


def get_debug_info(ip: str) -> dict:
    """Get debug information about rate limiting state."""
    client = _get_supabase_client()
    today, period_id, period_end = _get_current_period()

    debug_info = {
        "client_ip": ip,
        "period_id": period_id,
        "period_end": period_end.strftime("%H:%M"),
        "supabase_connected": client is not None,
        "current_usage": 0,
        "limit": MAX_VALIDATIONS_PER_12H
    }

    if client is None:
        return debug_info

    try:
        current_usage = _get_period_usage(client, period_id)
        debug_info["current_usage"] = current_usage

        # Get raw record for debugging
        response = client.table("rate_limits").select("*").eq(
            "hour", period_id
        ).execute()

        debug_info["records"] = [
            {
                "ip_hash": r.get("ip_hash", "")[:8] + "...",
                "date": str(r.get("date")),
                "hour": r.get("hour"),
                "request_count": r.get("request_count"),
                "last_request": r.get("last_request")
            }
            for r in (response.data or [])
        ]
        debug_info["record_count"] = len(response.data or [])

    except Exception as e:
        debug_info["error"] = str(e)

    return debug_info


# Keep old constants for backwards compatibility with app.py imports
MAX_VALIDATIONS_PER_DAY_PER_IP = MAX_VALIDATIONS_PER_12H
MAX_VALIDATIONS_PER_HOUR_PER_IP = MAX_VALIDATIONS_PER_12H
