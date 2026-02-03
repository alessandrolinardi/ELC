"""
Security Module for ELC Tools
Implements persistent rate limiting using Supabase, IP tracking, and abuse prevention.

Uses Supabase for reliable persistence across deploys and instances.
"""

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

import streamlit as st

logger = logging.getLogger(__name__)

# Security limits
MAX_VALIDATIONS_PER_DAY_GLOBAL = 5000  # Total daily limit across all users
MAX_VALIDATIONS_PER_DAY_PER_IP = 2000  # Per-IP daily limit
MAX_VALIDATIONS_PER_HOUR_PER_IP = 500  # Per-IP hourly limit
MIN_SECONDS_BETWEEN_REQUESTS = 5  # Minimum gap between requests per IP
MAX_FAILED_ATTEMPTS_PER_HOUR = 10  # Max failed attempts before temporary ban
BAN_DURATION_MINUTES = 30  # Temporary ban duration


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


def _get_ip_hash(ip: str) -> str:
    """Hash IP address for privacy-preserving tracking."""
    salt = "elc_tools_2024_salt"
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:16]


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
            # Use session_id as a stable identifier (unique per browser tab)
            return f"session_{ctx.session_id[:16]}"
    except (ImportError, AttributeError):
        pass

    # Method 2: Try st.context.headers (newer Streamlit versions)
    try:
        if hasattr(st, 'context') and hasattr(st.context, 'headers'):
            headers = st.context.headers
            if headers:
                # Try common forwarded IP headers
                for header in ['X-Forwarded-For', 'X-Real-IP', 'CF-Connecting-IP']:
                    ip = headers.get(header, '')
                    if ip:
                        # X-Forwarded-For may have multiple IPs
                        return ip.split(',')[0].strip()
    except (AttributeError, TypeError):
        pass

    # Method 3: Use session state with persistent ID
    try:
        if '_client_id' not in st.session_state:
            # Generate a unique ID for this session
            st.session_state._client_id = str(uuid.uuid4())[:16]
        return f"client_{st.session_state._client_id}"
    except Exception:
        pass

    # Final fallback: use a hash of current time (least reliable)
    return f"anon_{hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()[:8]}"


def _get_or_create_rate_record(client, ip_hash: str, today: str, current_hour: str) -> dict:
    """Get existing rate limit record or create a new one."""
    try:
        # Try to get existing record for this IP/date/hour
        response = client.table("rate_limits").select("*").eq(
            "ip_hash", ip_hash
        ).eq("date", today).eq("hour", current_hour).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]

        # Create new record
        new_record = {
            "ip_hash": ip_hash,
            "date": today,
            "hour": current_hour,
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
        logger.error(f"Error getting/creating rate record: {e}")
        return None


def is_ip_banned(ip: str) -> Tuple[bool, Optional[str]]:
    """Check if an IP is temporarily banned."""
    client = _get_supabase_client()
    if client is None:
        return False, None  # Allow if DB unavailable

    ip_hash = _get_ip_hash(ip)
    now = datetime.now()

    try:
        # Check for any active ban
        response = client.table("rate_limits").select("banned_until").eq(
            "ip_hash", ip_hash
        ).not_.is_("banned_until", "null").execute()

        if response.data:
            for record in response.data:
                if record.get("banned_until"):
                    ban_until = datetime.fromisoformat(record["banned_until"].replace("Z", "+00:00")).replace(tzinfo=None)
                    if now < ban_until:
                        remaining = (ban_until - now).seconds // 60
                        return True, f"Troppi tentativi. Riprova tra {remaining} minuti."

        return False, None
    except Exception as e:
        logger.error(f"Error checking ban status: {e}")
        return False, None


def _get_daily_totals(client, ip_hash: str, today: str) -> Tuple[int, int]:
    """Get daily totals for global and per-IP usage."""
    try:
        # Get global daily total
        global_response = client.table("rate_limits").select("request_count").eq(
            "date", today
        ).execute()
        global_today = sum(r.get("request_count", 0) for r in (global_response.data or []))

        # Get IP daily total
        ip_response = client.table("rate_limits").select("request_count").eq(
            "ip_hash", ip_hash
        ).eq("date", today).execute()
        ip_today = sum(r.get("request_count", 0) for r in (ip_response.data or []))

        return global_today, ip_today
    except Exception as e:
        logger.error(f"Error getting daily totals: {e}")
        return 0, 0


def check_rate_limit(ip: str, rows_to_validate: int) -> Tuple[bool, str, dict]:
    """
    Check if request is within rate limits.

    Returns:
        (is_allowed, message, usage_info)
    """
    client = _get_supabase_client()
    if client is None:
        # Allow requests if Supabase unavailable, but log warning
        logger.warning("Supabase unavailable - rate limiting disabled")
        return True, "OK", {}

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    # Check if IP is banned
    banned, ban_msg = is_ip_banned(ip)
    if banned:
        return False, ban_msg, {}

    # Get or create current hour record
    record = _get_or_create_rate_record(client, ip_hash, today, current_hour)
    if record is None:
        return True, "OK", {}  # Allow if DB error

    # Check minimum time between requests
    if record.get("last_request"):
        try:
            last_request_str = record["last_request"]
            if isinstance(last_request_str, str):
                last_request = datetime.fromisoformat(last_request_str.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                last_request = last_request_str
            elapsed = (now - last_request).total_seconds()
            if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
                wait_time = int(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
                return False, f"Attendi {wait_time} secondi prima della prossima validazione.", {}
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing last_request timestamp: {e}")

    # Get daily totals
    global_today, ip_today = _get_daily_totals(client, ip_hash, today)
    ip_this_hour = record.get("request_count", 0)

    # Check global daily limit
    if global_today + rows_to_validate > MAX_VALIDATIONS_PER_DAY_GLOBAL:
        return False, f"Limite giornaliero globale raggiunto ({MAX_VALIDATIONS_PER_DAY_GLOBAL}). Riprova domani.", {}

    # Check per-IP daily limit
    if ip_today + rows_to_validate > MAX_VALIDATIONS_PER_DAY_PER_IP:
        remaining = MAX_VALIDATIONS_PER_DAY_PER_IP - ip_today
        return False, f"Limite giornaliero raggiunto. Rimanenti: {remaining}/{MAX_VALIDATIONS_PER_DAY_PER_IP}", {}

    # Check per-IP hourly limit
    if ip_this_hour + rows_to_validate > MAX_VALIDATIONS_PER_HOUR_PER_IP:
        remaining = MAX_VALIDATIONS_PER_HOUR_PER_IP - ip_this_hour
        return False, f"Limite orario raggiunto. Rimanenti: {remaining}/{MAX_VALIDATIONS_PER_HOUR_PER_IP}", {}

    usage_info = {
        "global_today": global_today,
        "ip_today": ip_today,
        "ip_this_hour": ip_this_hour,
        "ip_daily_limit": MAX_VALIDATIONS_PER_DAY_PER_IP,
        "ip_hourly_limit": MAX_VALIDATIONS_PER_HOUR_PER_IP
    }

    return True, "OK", usage_info


def record_usage(ip: str, rows_validated: int):
    """Record API usage after successful validation."""
    client = _get_supabase_client()
    if client is None:
        return

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    try:
        # Get or create record
        record = _get_or_create_rate_record(client, ip_hash, today, current_hour)
        if record is None:
            return

        # Update the record with incremented count
        new_count = record.get("request_count", 0) + rows_validated

        client.table("rate_limits").update({
            "request_count": new_count,
            "last_request": now.isoformat()
        }).eq("ip_hash", ip_hash).eq("date", today).eq("hour", current_hour).execute()

        logger.debug(f"Recorded {rows_validated} validations for {ip_hash[:8]}...")
    except Exception as e:
        logger.error(f"Error recording usage: {e}")


def record_failed_attempt(ip: str):
    """Record a failed attempt (for abuse detection)."""
    client = _get_supabase_client()
    if client is None:
        return

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    try:
        # Get or create record
        record = _get_or_create_rate_record(client, ip_hash, today, current_hour)
        if record is None:
            return

        new_failed = record.get("failed_attempts", 0) + 1

        update_data = {"failed_attempts": new_failed}

        # Check if should be banned
        if new_failed >= MAX_FAILED_ATTEMPTS_PER_HOUR:
            ban_until = now + timedelta(minutes=BAN_DURATION_MINUTES)
            update_data["banned_until"] = ban_until.isoformat()
            logger.warning(f"IP {ip_hash[:8]}... banned until {ban_until}")

        client.table("rate_limits").update(update_data).eq(
            "ip_hash", ip_hash
        ).eq("date", today).eq("hour", current_hour).execute()
    except Exception as e:
        logger.error(f"Error recording failed attempt: {e}")


def get_usage_stats(ip: str) -> dict:
    """Get current usage statistics for display."""
    client = _get_supabase_client()
    if client is None:
        return {
            "global_today": 0,
            "global_limit": MAX_VALIDATIONS_PER_DAY_GLOBAL,
            "ip_today": 0,
            "ip_daily_limit": MAX_VALIDATIONS_PER_DAY_PER_IP,
            "ip_this_hour": 0,
            "ip_hourly_limit": MAX_VALIDATIONS_PER_HOUR_PER_IP
        }

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    try:
        global_today, ip_today = _get_daily_totals(client, ip_hash, today)

        # Get hourly usage
        hourly_response = client.table("rate_limits").select("request_count").eq(
            "ip_hash", ip_hash
        ).eq("hour", current_hour).execute()
        ip_this_hour = sum(r.get("request_count", 0) for r in (hourly_response.data or []))

        return {
            "global_today": global_today,
            "global_limit": MAX_VALIDATIONS_PER_DAY_GLOBAL,
            "ip_today": ip_today,
            "ip_daily_limit": MAX_VALIDATIONS_PER_DAY_PER_IP,
            "ip_this_hour": ip_this_hour,
            "ip_hourly_limit": MAX_VALIDATIONS_PER_HOUR_PER_IP
        }
    except Exception as e:
        logger.error(f"Error getting usage stats: {e}")
        return {
            "global_today": 0,
            "global_limit": MAX_VALIDATIONS_PER_DAY_GLOBAL,
            "ip_today": 0,
            "ip_daily_limit": MAX_VALIDATIONS_PER_DAY_PER_IP,
            "ip_this_hour": 0,
            "ip_hourly_limit": MAX_VALIDATIONS_PER_HOUR_PER_IP
        }


def validate_excel_content(df) -> Tuple[bool, Optional[str]]:
    """
    Validate Excel content for security issues.

    Checks for:
    - Suspicious formulas that could indicate injection attempts
    - Excessively long cell values
    - Unusual characters
    """
    MAX_CELL_LENGTH = 1000
    SUSPICIOUS_PATTERNS = ['=CMD(', '=SYSTEM(', '=EXEC(', '|', '=HYPERLINK(', '=IMPORTXML(']

    try:
        for col in df.columns:
            for idx, value in df[col].items():
                if not isinstance(value, str):
                    continue

                # Check cell length
                if len(value) > MAX_CELL_LENGTH:
                    return False, f"Cella troppo lunga nella colonna '{col}' (max {MAX_CELL_LENGTH} caratteri)"

                # Check for suspicious patterns
                value_upper = value.upper()
                for pattern in SUSPICIOUS_PATTERNS:
                    if pattern in value_upper:
                        return False, f"Contenuto non valido rilevato nella colonna '{col}'"
    except Exception as e:
        logger.warning(f"Error validating Excel content: {e}")
        # Don't block on validation errors

    return True, None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    import re
    import os
    # Remove path separators and null bytes
    sanitized = re.sub(r'[/\\:\x00]', '_', filename)
    # Remove leading dots (hidden files)
    sanitized = sanitized.lstrip('.')
    # Limit length
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    return sanitized or "unnamed"


def cleanup_old_records():
    """
    Clean up rate limit records older than 7 days.
    Call this periodically (e.g., once per day).
    """
    client = _get_supabase_client()
    if client is None:
        return

    try:
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        client.table("rate_limits").delete().lt("date", cutoff_date).execute()
        logger.info(f"Cleaned up rate limit records older than {cutoff_date}")
    except Exception as e:
        logger.error(f"Error cleaning up old records: {e}")
