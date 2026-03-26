"""Shipments quotation — parse Excel, call rates webhook."""
import io
import math
import requests
from typing import Optional

import pandas as pd

from .config_compat import get_secret
from .logging_config import get_logger
from .utils import map_columns

logger = get_logger(__name__)


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


def send_rates_request(payload: dict) -> tuple[bool, str, Optional[dict]]:
    """POST to the rates webhook. Returns (success, message, response_data)."""
    url = get_secret("rates", "webhook_url")
    secret = get_secret("rates", "webhook_secret")

    if not url:
        return False, "RATES_WEBHOOK_URL non configurato.", None

    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=600)

        if 200 <= resp.status_code < 300:
            try:
                return True, "Quotazione completata", resp.json()
            except ValueError:
                return True, "Quotazione completata (risposta non JSON)", None
        else:
            try:
                body = resp.json()
                detail = body.get("detail", body.get("error", ""))
                msg = f"Errore webhook: {detail}" if detail else f"Errore HTTP {resp.status_code}"
            except ValueError:
                msg = f"Errore HTTP {resp.status_code}"
            return False, msg, None

    except requests.exceptions.Timeout:
        return False, "Timeout webhook (>600s). Riprova.", None
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {e}", None
