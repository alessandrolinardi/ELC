"""Freight request business logic — upload file to Supabase Storage, notify via Zapier."""
import uuid
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from .config_compat import get_secret, get_supabase_client
from .logging_config import get_logger

logger = get_logger(__name__)

STORAGE_BUCKET = "freight-requests"
SIGNED_URL_EXPIRY = 604800  # 7 days in seconds


def generate_reference_id() -> str:
    """Generate a unique freight request reference ID."""
    return f"FRQ-{uuid.uuid4().hex[:8]}"


def upload_freight_file(file_bytes: bytes, filename: str, reference_id: str) -> str:
    """Upload file to Supabase Storage and return a signed download URL.
    Raises Exception on failure.
    """
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client unavailable")

    path = f"{reference_id}/{filename}"
    try:
        client.storage.from_(STORAGE_BUCKET).upload(path, file_bytes)
        result = client.storage.from_(STORAGE_BUCKET).create_signed_url(path, SIGNED_URL_EXPIRY)
        signed_url = result.get("signedURL") or result.get("signedUrl", "")
        if not signed_url:
            raise RuntimeError(f"No signed URL returned for {path}")
        return signed_url
    except Exception as e:
        logger.exception("Error uploading freight file %s: %s", path, e)
        raise


def send_freight_request(
    file_url: str,
    filename: str,
    reference_id: str,
    sender_address: dict,
    notes: Optional[str],
) -> tuple[bool, str]:
    """Build JSON payload and POST to Zapier. Returns (success, message)."""
    zapier_url = get_secret("zapier", "webhook_url")
    if not zapier_url:
        logger.error("No Zapier webhook URL configured for freight request")
        return False, "Webhook non configurato"

    rome = ZoneInfo("Europe/Rome")
    timestamp = datetime.now(rome).strftime("%d/%m/%Y %H:%M")

    payload = {
        "event_type": "freight_request",
        "reference_id": reference_id,
        "subject": f"FREIGHT REQUEST - {reference_id}",
        "timestamp": timestamp,

        "from_name": sender_address.get("from_name", ""),
        "from_company": sender_address.get("from_company", ""),
        "from_street1": sender_address.get("from_street1", ""),
        "from_city": sender_address.get("from_city", ""),
        "from_state": sender_address.get("from_state", ""),
        "from_zip": sender_address.get("from_zip", ""),
        "from_country": sender_address.get("from_country", "IT"),
        "from_phone": sender_address.get("from_phone", ""),

        "notes": notes or "",
        "has_notes": bool(notes),

        "filename": filename,
        "file_url": file_url,
    }

    try:
        resp = requests.post(zapier_url, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info("Freight request %s sent to Zapier", reference_id)
            return True, "Richiesta inviata"
        logger.error("Zapier freight webhook HTTP %s for %s", resp.status_code, reference_id)
        return False, f"Errore nell'invio della richiesta (HTTP {resp.status_code})"
    except Exception as e:
        logger.error("Zapier freight webhook error for %s: %s", reference_id, e)
        return False, "Errore nell'invio della richiesta, riprova"
