"""Pickup request business logic -- sends to Zapier webhook + pickup webhook."""
import hashlib
import uuid
import requests
from datetime import datetime, date, time
from typing import Optional

from .config_compat import get_secret
from .logging_config import get_logger

logger = get_logger(__name__)


CARRIER_MAP = {
    "DHL": {"carrier_name": "MyDHL", "carrier_id": 9536},
    "UPS": {"carrier_name": "UPSv2", "carrier_id": 7743},
    "FedEx": {"carrier_name": "FedExv2", "carrier_id": 3699},
}


def _build_pickup_webhook_payload(
    carrier: str,
    contact_name: str,
    company: str,
    address: str,
    city: str,
    province: str,
    zip_code: str,
    phone: str,
    pickup_date: date,
    time_start: time,
    time_end: time,
    num_packages: int,
    weight_per_package: float,
    length: float,
    width: float,
    height: float,
    notes: str,
    use_pallet: bool,
    num_pallets: int,
    pallet_dimensions_str: str,
) -> dict:
    """Build the flat payload expected by the shipments-backend pickup webhook."""
    carrier_info = CARRIER_MAP.get(carrier, {"carrier_name": carrier, "carrier_id": 0})
    time_windows = _split_time_window(time_start, time_end)

    return {
        "carrier_name": carrier_info["carrier_name"],
        "carrier_id": carrier_info["carrier_id"],
        "from_name": contact_name or company,
        "from_company": company,
        "from_street1": address,
        "from_city": city,
        "from_state": province,
        "from_zip": zip_code,
        "from_country": "IT",
        "from_phone": phone,
        "to_country": "IT",
        "parcels": [
            {
                "length": length,
                "width": width,
                "height": height,
                "weight": round(weight_per_package, 2),
            }
            for _ in range(num_packages)
        ],
        "pickup_date": pickup_date.isoformat(),
        "pickup_morning_min": time_windows["PickupMorningMintime"],
        "pickup_morning_max": time_windows["PickupMorningMaxtime"],
        "pickup_afternoon_min": time_windows["PickupAfternoonMintime"],
        "pickup_afternoon_max": time_windows["PickupAfternoonMaxtime"],
        "pickup_note": _build_pickup_note(notes, use_pallet, num_pallets, pallet_dimensions_str),
        "order_ids": _generate_order_id(carrier, pickup_date, company, zip_code, time_start),
    }


def _generate_order_id(carrier: str, pickup_date: date, company: str, zip_code: str, time_start: time) -> str:
    """Generate a deterministic order_id for idempotency.

    Same carrier + date + company + zip + time_start within 24h → same order_id,
    so the shipments-backend deduplicates accidental double-submits.
    time_start is included so two pickups for the same entity on the same day
    (e.g. morning run + afternoon run) get distinct IDs.
    """
    key = f"ELC-{carrier}-{pickup_date.isoformat()}-{company}-{zip_code}-{time_start.strftime('%H%M')}"
    short_hash = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"ELC-{short_hash}"


def _build_pickup_note(
    notes: str,
    use_pallet: bool,
    num_pallets: int,
    pallet_dimensions_str: str,
) -> str:
    """Build PickupNote (max 255 chars) combining user notes + pallet info."""
    parts = []
    if use_pallet and num_pallets > 0:
        parts.append(f"{num_pallets} pallet ({pallet_dimensions_str})")
    if notes:
        parts.append(notes)
    result = " | ".join(parts)
    return result[:255]


def _split_time_window(
    start: time, end: time, midday: time = time(13, 0),
) -> dict[str, str]:
    """Split a single time window into ShippyPro morning/afternoon format.

    Rules:
    - If the window is entirely before midday → morning only, afternoon empty
    - If the window is entirely after midday → morning empty, afternoon only
    - If it spans both → split at midday boundary
    """
    s, e = start.strftime("%H:%M"), end.strftime("%H:%M")
    m = midday.strftime("%H:%M")

    if end <= midday:
        # Entirely morning
        return {
            "PickupMorningMintime": s,
            "PickupMorningMaxtime": e,
            "PickupAfternoonMintime": "",
            "PickupAfternoonMaxtime": "",
        }
    elif start >= midday:
        # Entirely afternoon
        return {
            "PickupMorningMintime": "",
            "PickupMorningMaxtime": "",
            "PickupAfternoonMintime": s,
            "PickupAfternoonMaxtime": e,
        }
    else:
        # Spans both
        return {
            "PickupMorningMintime": s,
            "PickupMorningMaxtime": m,
            "PickupAfternoonMintime": m,
            "PickupAfternoonMaxtime": e,
        }


def send_pickup_request(
    carrier: str,
    pickup_date: date,
    time_start: time,
    time_end: time,
    company: str,
    contact_name: str,
    address: str,
    zip_code: str,
    city: str,
    province: str,
    phone: str,
    reference: str,
    num_packages: int,
    weight_per_package: float,
    length: float,
    width: float,
    height: float,
    use_pallet: bool,
    num_pallets: int,
    pallet_length: float,
    pallet_width: float,
    pallet_height: float,
    notes: str,
) -> tuple[bool, str, Optional[dict]]:
    """
    Send pickup request via Zapier webhook + pickup webhook.

    Returns:
        Tuple of (success, message, pickup_webhook_response)
    """
    # Calculate totals
    total_weight = num_packages * weight_per_package
    shipment_type = "FREIGHT" if total_weight > 70 else "NORMAL"
    package_volume = length * width * height / 1000000  # in cubic meters
    total_volume = package_volume * num_packages

    # Format date/time
    date_str = pickup_date.strftime("%d/%m/%Y")
    time_start_str = time_start.strftime("%H:%M")
    time_end_str = time_end.strftime("%H:%M")
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

    # Build subject for email
    subject = f"{carrier} - {date_str} - {shipment_type}"

    # Build dimensions strings
    package_dimensions_str = f"{length} x {width} x {height} cm"
    pallet_dimensions_str = f"{pallet_length} x {pallet_width} x {pallet_height} cm" if use_pallet else "-"

    # Unique request ID for deduplication
    request_id = str(uuid.uuid4())

    # Prepare payload for Zapier - all fields exposed individually
    payload = {
        # === Dedup ===
        "request_id": request_id,

        # === Email/Meta fields ===
        "subject": subject,
        "timestamp": timestamp,
        "shipment_type": shipment_type,

        # === Carrier ===
        "carrier": carrier,

        # === Date/Time ===
        "pickup_date": date_str,
        "time_start": time_start_str,
        "time_end": time_end_str,
        "time_window": f"{time_start_str} - {time_end_str}",

        # === Address - Individual fields ===
        "company": company,
        "contact_name": contact_name,
        "address": address,
        "zip_code": zip_code,
        "city": city,
        "province": province,
        "phone": phone,
        "reference": reference,
        # Address - Formatted
        "full_address": f"{address}, {zip_code} {city} ({province})",
        "address_line1": f"{company} - {contact_name}" if contact_name else company,
        "address_line2": f"{address}, {zip_code} {city} ({province})",

        # === Package Details - Individual fields ===
        "num_packages": num_packages,
        "weight_per_package": weight_per_package,
        "weight_per_package_str": f"{weight_per_package} kg",
        "package_length": length,
        "package_width": width,
        "package_height": height,
        # Package - Calculated
        "total_weight": total_weight,
        "total_weight_str": f"{total_weight:.1f} kg",
        "package_dimensions": package_dimensions_str,
        "package_volume_m3": round(package_volume, 3),
        "total_volume_m3": round(total_volume, 3),

        # === Pallet Details ===
        "use_pallet": use_pallet,
        "use_pallet_str": "Si" if use_pallet else "No",
        "num_pallets": num_pallets if use_pallet else 0,
        "pallet_length": pallet_length if use_pallet else 0,
        "pallet_width": pallet_width if use_pallet else 0,
        "pallet_height": pallet_height if use_pallet else 0,
        "pallet_dimensions": pallet_dimensions_str,

        # === Notes ===
        "notes": notes if notes else "",
        "has_notes": bool(notes),

        # === Summary for email body ===
        "summary_packages": f"{num_packages} colli x {weight_per_package} kg = {total_weight:.1f} kg totali",
        "summary_dimensions": f"Dimensioni collo: {package_dimensions_str}",
        "summary_pallet": f"{num_pallets} pallet ({pallet_dimensions_str})" if use_pallet else "Nessun pallet",

        # === Pickup webhook payload (matches shipments-backend schema) ===
        "pickup_webhook": _build_pickup_webhook_payload(
            carrier=carrier,
            contact_name=contact_name,
            company=company,
            address=address,
            city=city,
            province=province,
            zip_code=zip_code,
            phone=phone,
            pickup_date=pickup_date,
            time_start=time_start,
            time_end=time_end,
            num_packages=num_packages,
            weight_per_package=weight_per_package,
            length=length,
            width=width,
            height=height,
            notes=notes,
            use_pallet=use_pallet,
            num_pallets=num_pallets,
            pallet_dimensions_str=pallet_dimensions_str,
        ),
    }

    # --- Send to Zapier (email + Trello) ---
    zapier_msg = ""
    zapier_url = get_secret("zapier", "webhook_url")
    if zapier_url:
        try:
            resp = requests.post(zapier_url, json=payload, timeout=10)
            if resp.status_code != 200:
                zapier_msg = f"Zapier HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            zapier_msg = "Zapier timeout"
        except requests.exceptions.RequestException as e:
            zapier_msg = f"Zapier: {e}"

    # --- Send to pickup webhook (ShippyPro processing) ---
    pickup_msg = ""
    pickup_result: Optional[dict] = None
    pickup_url = get_secret("pickup", "webhook_url")
    pickup_secret = get_secret("pickup", "webhook_secret")
    logger.info("Pickup webhook URL: %s (secret set: %s)", pickup_url, bool(pickup_secret))
    if pickup_url:
        try:
            headers = {"X-Webhook-Secret": pickup_secret} if pickup_secret else {}
            logger.info("Sending pickup webhook to %s with payload keys: %s", pickup_url, list(payload["pickup_webhook"].keys()))
            resp = requests.post(pickup_url, json=payload["pickup_webhook"], headers=headers, timeout=40)
            logger.info("Pickup webhook response: HTTP %s, body: %s", resp.status_code, resp.text[:500])
            if 200 <= resp.status_code < 300:
                try:
                    pickup_result = resp.json()
                except ValueError:
                    pass
            else:
                # Try to extract error detail from response body
                try:
                    body = resp.json()
                    detail = body.get("detail", body.get("error", ""))
                    pickup_msg = f"Pickup: {detail}" if detail else f"Pickup HTTP {resp.status_code}"
                except ValueError:
                    pickup_msg = f"Pickup HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            pickup_msg = "Pickup webhook timeout (>40s)"
        except requests.exceptions.RequestException as e:
            logger.error("Pickup webhook exception: %s", e)
            pickup_msg = f"Pickup webhook: {e}"

    # --- Result ---
    # Pickup webhook is the primary business path; Zapier is secondary (notifications).
    if not zapier_url and not pickup_url:
        return False, "Nessun webhook configurato. Aggiungi ZAPIER_WEBHOOK_URL o PICKUP_WEBHOOK_URL.", None

    # If the pickup webhook failed, that's a hard failure
    if pickup_url and pickup_msg:
        return False, pickup_msg, pickup_result

    # Pickup succeeded (or not configured). Zapier failure is a warning, not a blocker.
    message = "Richiesta inviata"
    if zapier_msg:
        logger.warning("Zapier webhook failed: %s", zapier_msg)
        message += f" (avviso: notifica Zapier fallita)"

    return True, message, pickup_result
