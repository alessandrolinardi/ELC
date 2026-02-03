"""
Security Module for ELC Tools
Implements persistent rate limiting, IP tracking, and abuse prevention.
"""

import json
import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import threading

# Thread lock for file operations
_file_lock = threading.Lock()

# Storage file for persistent rate limiting
USAGE_FILE = Path(__file__).parent.parent / "data" / ".usage_tracking.json"

# Security limits
MAX_VALIDATIONS_PER_DAY_GLOBAL = 5000  # Total daily limit across all users
MAX_VALIDATIONS_PER_DAY_PER_IP = 2000  # Per-IP daily limit
MAX_VALIDATIONS_PER_HOUR_PER_IP = 500  # Per-IP hourly limit
MIN_SECONDS_BETWEEN_REQUESTS = 5  # Minimum gap between requests per IP
MAX_FAILED_ATTEMPTS_PER_HOUR = 10  # Max failed attempts before temporary ban
BAN_DURATION_MINUTES = 30  # Temporary ban duration


def _get_ip_hash(ip: str) -> str:
    """Hash IP address for privacy-preserving tracking."""
    # Add a salt to prevent rainbow table attacks
    salt = "elc_tools_2024_salt"
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:16]


def _ensure_data_dir():
    """Ensure data directory exists."""
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_usage_data() -> dict:
    """Load usage data from persistent storage."""
    _ensure_data_dir()
    try:
        if USAGE_FILE.exists():
            with open(USAGE_FILE, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return {
        "global": {},
        "by_ip": {},
        "bans": {},
        "last_cleanup": None
    }


def _save_usage_data(data: dict):
    """Save usage data to persistent storage."""
    _ensure_data_dir()
    with _file_lock:
        try:
            with open(USAGE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass  # Fail silently - don't crash the app


def _cleanup_old_data(data: dict) -> dict:
    """Remove data older than 24 hours to prevent file bloat."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")

    # Only cleanup once per hour
    if data.get("last_cleanup") == current_hour:
        return data

    # Clean global data (keep only today)
    if "global" in data:
        data["global"] = {k: v for k, v in data["global"].items() if k == today}

    # Clean per-IP data (keep only last 24 hours)
    cutoff = (now - timedelta(hours=24)).strftime("%Y-%m-%d-%H")
    if "by_ip" in data:
        for ip_hash in list(data["by_ip"].keys()):
            ip_data = data["by_ip"][ip_hash]
            if "hourly" in ip_data:
                ip_data["hourly"] = {k: v for k, v in ip_data["hourly"].items() if k >= cutoff}
            if "daily" in ip_data:
                ip_data["daily"] = {k: v for k, v in ip_data["daily"].items() if k == today}
            # Remove IP entries with no recent activity
            if not ip_data.get("hourly") and not ip_data.get("daily"):
                del data["by_ip"][ip_hash]

    # Clean expired bans
    if "bans" in data:
        data["bans"] = {
            ip_hash: ban_until
            for ip_hash, ban_until in data["bans"].items()
            if datetime.fromisoformat(ban_until) > now
        }

    data["last_cleanup"] = current_hour
    return data


def is_ip_banned(ip: str) -> Tuple[bool, Optional[str]]:
    """Check if an IP is temporarily banned."""
    data = _load_usage_data()
    ip_hash = _get_ip_hash(ip)

    if ip_hash in data.get("bans", {}):
        ban_until = datetime.fromisoformat(data["bans"][ip_hash])
        if datetime.now() < ban_until:
            remaining = (ban_until - datetime.now()).seconds // 60
            return True, f"Troppi tentativi. Riprova tra {remaining} minuti."
        else:
            # Ban expired, remove it
            del data["bans"][ip_hash]
            _save_usage_data(data)

    return False, None


def check_rate_limit(ip: str, rows_to_validate: int) -> Tuple[bool, str, dict]:
    """
    Check if request is within rate limits.

    Returns:
        (is_allowed, message, usage_info)
    """
    data = _load_usage_data()
    data = _cleanup_old_data(data)

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    # Check if IP is banned
    banned, ban_msg = is_ip_banned(ip)
    if banned:
        return False, ban_msg, {}

    # Initialize IP data if needed
    if ip_hash not in data["by_ip"]:
        data["by_ip"][ip_hash] = {"hourly": {}, "daily": {}, "last_request": None}

    ip_data = data["by_ip"][ip_hash]

    # Check minimum time between requests
    if ip_data.get("last_request"):
        last_request = datetime.fromisoformat(ip_data["last_request"])
        elapsed = (now - last_request).total_seconds()
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            wait_time = int(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
            return False, f"Attendi {wait_time} secondi prima della prossima validazione.", {}

    # Get current usage
    global_today = data.get("global", {}).get(today, 0)
    ip_today = ip_data.get("daily", {}).get(today, 0)
    ip_this_hour = ip_data.get("hourly", {}).get(current_hour, 0)

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

    _save_usage_data(data)
    return True, "OK", usage_info


def record_usage(ip: str, rows_validated: int):
    """Record API usage after successful validation."""
    data = _load_usage_data()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    # Update global counter
    if "global" not in data:
        data["global"] = {}
    data["global"][today] = data["global"].get(today, 0) + rows_validated

    # Update per-IP counters
    if ip_hash not in data["by_ip"]:
        data["by_ip"][ip_hash] = {"hourly": {}, "daily": {}, "last_request": None}

    ip_data = data["by_ip"][ip_hash]

    if "daily" not in ip_data:
        ip_data["daily"] = {}
    ip_data["daily"][today] = ip_data["daily"].get(today, 0) + rows_validated

    if "hourly" not in ip_data:
        ip_data["hourly"] = {}
    ip_data["hourly"][current_hour] = ip_data["hourly"].get(current_hour, 0) + rows_validated

    ip_data["last_request"] = now.isoformat()

    _save_usage_data(data)


def record_failed_attempt(ip: str):
    """Record a failed attempt (for abuse detection)."""
    data = _load_usage_data()

    now = datetime.now()
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    if ip_hash not in data["by_ip"]:
        data["by_ip"][ip_hash] = {"hourly": {}, "daily": {}, "failed_attempts": {}}

    ip_data = data["by_ip"][ip_hash]

    if "failed_attempts" not in ip_data:
        ip_data["failed_attempts"] = {}

    ip_data["failed_attempts"][current_hour] = ip_data["failed_attempts"].get(current_hour, 0) + 1

    # Check if should be banned
    failed_this_hour = ip_data["failed_attempts"].get(current_hour, 0)
    if failed_this_hour >= MAX_FAILED_ATTEMPTS_PER_HOUR:
        ban_until = now + timedelta(minutes=BAN_DURATION_MINUTES)
        if "bans" not in data:
            data["bans"] = {}
        data["bans"][ip_hash] = ban_until.isoformat()

    _save_usage_data(data)


def get_usage_stats(ip: str) -> dict:
    """Get current usage statistics for display."""
    data = _load_usage_data()

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.strftime("%Y-%m-%d-%H")
    ip_hash = _get_ip_hash(ip)

    ip_data = data.get("by_ip", {}).get(ip_hash, {})

    return {
        "global_today": data.get("global", {}).get(today, 0),
        "global_limit": MAX_VALIDATIONS_PER_DAY_GLOBAL,
        "ip_today": ip_data.get("daily", {}).get(today, 0),
        "ip_daily_limit": MAX_VALIDATIONS_PER_DAY_PER_IP,
        "ip_this_hour": ip_data.get("hourly", {}).get(current_hour, 0),
        "ip_hourly_limit": MAX_VALIDATIONS_PER_HOUR_PER_IP
    }


def get_client_ip() -> str:
    """
    Get client IP address from Streamlit.
    Falls back to a default if not available.
    """
    try:
        # Try to get from Streamlit's context
        import streamlit as st

        # Check headers for forwarded IP (common in cloud deployments)
        headers = getattr(st.context, 'headers', None)
        if headers:
            # X-Forwarded-For can contain multiple IPs, take the first
            forwarded = headers.get('X-Forwarded-For', '')
            if forwarded:
                return forwarded.split(',')[0].strip()

            # Try other common headers
            for header in ['X-Real-IP', 'CF-Connecting-IP', 'True-Client-IP']:
                ip = headers.get(header, '')
                if ip:
                    return ip.strip()

        # Fallback: use session ID as pseudo-identifier
        if hasattr(st, 'session_state') and 'session_id' in st.session_state:
            return f"session_{st.session_state.session_id}"

    except Exception:
        pass

    # Final fallback
    return "unknown"


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

    return True, None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    import re
    # Remove path separators and null bytes
    sanitized = re.sub(r'[/\\:\x00]', '_', filename)
    # Remove leading dots (hidden files)
    sanitized = sanitized.lstrip('.')
    # Limit length
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255-len(ext)] + ext
    return sanitized or "unnamed"
