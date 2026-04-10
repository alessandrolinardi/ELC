"""Freight request business logic — base64-encode file and send to Zapier."""
import base64
import uuid
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from .config_compat import get_secret
from .logging_config import get_logger

logger = get_logger(__name__)


def generate_reference_id() -> str:
    """Generate a unique freight request reference ID."""
    return f"FRQ-{uuid.uuid4().hex[:8]}"


def send_freight_request(
    file_bytes: bytes,
    filename: str,
    reference_id: str,
    sender_address: dict,
    notes: Optional[str],
) -> tuple[bool, str]:
    """Build JSON payload with base64-encoded file and POST to Zapier.

    Returns (success, message).
    """
    zapier_url = get_secret("zapier", "webhook_url")
    if not zapier_url:
        logger.error("No Zapier webhook URL configured for freight request")
        return False, "Webhook non configurato"

    rome = ZoneInfo("Europe/Rome")
    timestamp = datetime.now(rome).strftime("%d/%m/%Y %H:%M")

    file_b64 = base64.b64encode(file_bytes).decode("ascii")

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
        "file_base64": file_b64,
    }

    try:
        resp = requests.post(zapier_url, json=payload, timeout=30)
        if resp.status_code == 200:
            logger.info("Freight request %s sent to Zapier", reference_id)
            return True, "Richiesta inviata"
        logger.error("Zapier freight webhook HTTP %s for %s", resp.status_code, reference_id)
        return False, f"Errore nell'invio della richiesta (HTTP {resp.status_code})"
    except Exception as e:
        logger.error("Zapier freight webhook error for %s: %s", reference_id, e)
        return False, "Errore nell'invio della richiesta, riprova"
