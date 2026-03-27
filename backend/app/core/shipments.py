"""Shipments — parse Excel, call rates webhook, create shipments."""
import io
import math
import time
import requests
from typing import Optional, Callable
from urllib.parse import urlparse, urlunparse

import pandas as pd

from .config_compat import get_secret
from .logging_config import get_logger
from .utils import map_columns

logger = get_logger(__name__)

POLL_INTERVAL = 15  # seconds between polls

# Carrier name/ID constants (must match ShippyPro account)
CARRIER_IDS = {
    "MyDHL": 9536,
    "UPSv2": 7743,
    "FedExv2": 3699,
}


def _clean(val) -> Optional[str]:
    """Return None if val is empty, 'None', NaN, or whitespace."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    if s.lower() in ("none", "nan", ""):
        return None
    return s


def _clean_num(val, default: float = 1.0) -> float:
    """Return a positive float, defaulting if val is missing/zero/invalid."""
    if val is None:
        return default
    try:
        n = float(val)
        if math.isnan(n) or n <= 0:
            return default
        return n
    except (ValueError, TypeError):
        return default


def parse_shipments_excel(excel_bytes: bytes) -> list[dict]:
    """Parse Excel into a list of shipment dicts for the rates API.

    Returns a list of shipments ready for the webhook payload.
    Omits optional fields if empty rather than sending null.
    """
    df = pd.read_excel(io.BytesIO(excel_bytes))
    col_map = map_columns(df)

    shipments = []
    for _, row in df.iterrows():
        def get(field):
            col = col_map.get(field)
            return _clean(row.get(col)) if col else None

        # Required fields — use fallbacks for missing data
        name = get("name") or "Recipient"
        street1 = get("street") or ""
        city = get("city") or ""
        zip_code = get("zip") or ""
        country = get("country") or "IT"
        phone = get("phone") or "0000000000"

        to_address = {
            "name": name,
            "street1": street1,
            "city": city,
            "zip": zip_code,
            "country": country.upper()[:2],
            "phone": phone,
        }

        # Optional fields — omit if empty
        company = get("company")
        if company:
            to_address["company"] = company
        state = get("state")
        if state:
            to_address["state"] = state
        email = get("email")
        if email:
            to_address["email"] = email

        # Parcels
        parcel_count = max(1, int(_clean_num(get("parcels"), 1)))
        weight = _clean_num(get("weight"), 1)
        length = _clean_num(get("length"), 1)
        width = _clean_num(get("width"), 1)
        height = _clean_num(get("height"), 1)

        parcels = [
            {"length": length, "width": width, "height": height, "weight": round(weight, 2)}
            for _ in range(parcel_count)
        ]

        shipment: dict = {
            "to_address": to_address,
            "parcels": parcels,
        }

        content = get("content_description")
        if content:
            shipment["content_description"] = content

        shipments.append(shipment)

    return shipments


def build_from_address(
    name: str, street1: str, city: str, zip_code: str, country: str, phone: str,
    company: str = "", state: str = "", email: str = "",
) -> dict:
    """Build from_address dict, omitting empty optional fields."""
    addr = {
        "name": name,
        "street1": street1,
        "city": city,
        "zip": zip_code,
        "country": country.upper()[:2],
        "phone": phone,
    }
    if company:
        addr["company"] = company
    if state:
        addr["state"] = state
    if email:
        addr["email"] = email
    return addr


def send_rates_request(
    payload: dict,
    on_progress: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str, Optional[dict]]:
    """Submit a rates job and poll until complete.

    The rates API is async: POST returns a job_id instantly,
    then GET /api/webhook/rates/{job_id} is polled every 15s.

    on_progress is called with a status message on each poll cycle.
    """
    base_url = get_secret("rates", "webhook_url")
    secret = get_secret("rates", "webhook_secret")

    if not base_url:
        return False, "RATES_WEBHOOK_URL non configurato.", None

    # Strip trailing path segments — we need the base URL
    # Config should be set to: https://shipments-backend.onrender.com/api/webhook/rates
    submit_url = base_url.rstrip("/")

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret

    # --- Step 1: Submit job ---
    try:
        resp = requests.post(submit_url, json=payload, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {e}", None

    if resp.status_code == 409:
        return False, "Un altro job è già in corso. Riprova tra qualche minuto.", None

    if resp.status_code not in (200, 201, 202):
        try:
            body = resp.json()
            detail = body.get("detail", body.get("error", ""))
            msg = f"Errore: {detail}" if detail else f"Errore HTTP {resp.status_code}"
        except ValueError:
            msg = f"Errore HTTP {resp.status_code}"
        return False, msg, None

    try:
        job_data = resp.json()
        remote_job_id = job_data.get("job_id")
    except ValueError:
        return False, "Risposta non valida dal server.", None

    if not remote_job_id:
        return False, "Il server non ha restituito un job_id.", None

    poll_url = f"{submit_url}/{remote_job_id}"
    logger.info("Rates job submitted: %s — polling %s", remote_job_id, poll_url)

    # --- Step 2: Poll for results ---
    start_time = time.time()
    max_poll_time = 900  # 15 minutes max

    while True:
        time.sleep(POLL_INTERVAL)
        elapsed = int(time.time() - start_time)

        if on_progress:
            minutes = elapsed // 60
            seconds = elapsed % 60
            on_progress(f"Elaborazione tariffe in corso... ({minutes}m {seconds:02d}s)")

        if elapsed > max_poll_time:
            return False, f"Timeout: il job non è terminato dopo {max_poll_time // 60} minuti.", None

        try:
            resp = requests.get(poll_url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.warning("Poll error (will retry): %s", e)
            continue

        if resp.status_code == 404:
            return False, "Job non trovato o scaduto sul server remoto.", None
        if resp.status_code == 401:
            return False, "Autenticazione fallita (X-Webhook-Secret).", None
        if resp.status_code != 200:
            continue  # Transient error, retry

        try:
            status_data = resp.json()
        except ValueError:
            continue

        job_status = status_data.get("status")

        if job_status == "completed":
            result = status_data.get("result")
            return True, "Quotazione completata", result

        if job_status == "failed":
            error = status_data.get("error", "Errore sconosciuto")
            return False, f"Job fallito: {error}", None


def _derive_ship_url(rates_url: str) -> str:
    """Derive the /api/webhook/ship URL from the rates webhook URL.

    rates_url is typically: https://host/api/webhook/rates
    We replace the last path segment: .../rates → .../ship
    """
    parsed = urlparse(rates_url.rstrip("/"))
    path_parts = parsed.path.rsplit("/", 1)
    ship_path = path_parts[0] + "/ship" if len(path_parts) > 1 else "/api/webhook/ship"
    return urlunparse(parsed._replace(path=ship_path))


def send_ship_request(ship_data: dict) -> dict:
    """Call the Ship webhook endpoint to create a shipment with carrier label.

    Uses the same base URL and secret as the rates webhook.

    Args:
        ship_data: Dict with carrier_name, carrier_id, carrier_service,
                   from_address, to_address, parcels, and optional fields.

    Returns:
        Dict with keys: status, tracking_number, label_url, sp_order_id,
        error_message, and the full response data.
    """
    rates_url = get_secret("rates", "webhook_url")
    secret = get_secret("rates", "webhook_secret")

    if not rates_url:
        return {
            "status": "failed",
            "error_message": "RATES_WEBHOOK_URL non configurato.",
        }

    ship_url = _derive_ship_url(rates_url)

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret

    logger.info("Ship request to %s — carrier=%s service=%s",
                ship_url, ship_data.get("carrier_name"), ship_data.get("carrier_service"))

    try:
        resp = requests.post(ship_url, json=ship_data, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        logger.error("Ship request failed: %s", e)
        return {
            "status": "failed",
            "error_message": f"Errore connessione: {e}",
        }

    try:
        result = resp.json()
    except ValueError:
        return {
            "status": "failed",
            "error_message": f"Risposta non valida (HTTP {resp.status_code})",
        }

    # Check status field (not HTTP code) per Shipments platform spec
    status = result.get("status", "")

    if status == "shipped":
        return {
            "status": "shipped",
            "sp_order_id": result.get("sp_order_id"),
            "tracking_number": result.get("tracking_number") or "",
            "tracking_carrier": result.get("tracking_carrier") or "",
            "label_url": result.get("label_url") or "",
            "error_message": None,
            "data": result,
        }
    elif status == "failed":
        return {
            "status": "failed",
            "error_message": result.get("error_message", "Errore sconosciuto dal server spedizioni."),
            "sp_order_id": result.get("sp_order_id"),
            "data": result,
        }
    else:
        # Unexpected status
        return {
            "status": "failed",
            "error_message": f"Stato imprevisto: {status}. Risposta: {result}",
        }
