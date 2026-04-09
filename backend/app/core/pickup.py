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


def _build_zapier_payload(record: dict, event_type: str) -> dict:
    """Build the full Zapier webhook payload from a DB record.

    Used by both creation and cancellation flows. Recomputes all derived
    fields from the raw columns stored in elc_pickups.
    """
    from zoneinfo import ZoneInfo

    # Parse stored values
    carrier = record["carrier"]
    pickup_date_str = record["pickup_date"]  # ISO "2026-04-10"
    time_start_str = record["time_start"]     # ISO "09:00:00"
    time_end_str = record["time_end"]
    company = record["company"]
    contact_name = record.get("contact_name", "")
    address = record["address"]
    zip_code = record["zip_code"]
    city = record["city"]
    province = record.get("province", "")
    phone = record.get("phone", "")
    reference = record.get("reference", "")
    num_packages = record["num_packages"]
    weight_per_package = float(record["weight_per_package"])
    length = float(record["length"])
    width = float(record["width"])
    height = float(record["height"])
    use_pallet = record.get("use_pallet", False)
    num_pallets = record.get("num_pallets", 0)
    pallet_length = float(record.get("pallet_length", 0))
    pallet_width = float(record.get("pallet_width", 0))
    pallet_height = float(record.get("pallet_height", 0))
    notes = record.get("notes", "")

    # Derived values
    total_weight = num_packages * weight_per_package
    shipment_type = "FREIGHT" if total_weight > 70 else "NORMAL"
    package_volume = length * width * height / 1_000_000
    total_volume = package_volume * num_packages

    # Parse date for formatting
    parts = pickup_date_str.split("-")  # "2026-04-10"
    date_str = f"{parts[2]}/{parts[1]}/{parts[0]}"  # "10/04/2026"

    # Time formatting — strip seconds if present
    ts = time_start_str[:5]  # "09:00"
    te = time_end_str[:5]    # "16:00"

    # Timestamp in Europe/Rome
    rome = ZoneInfo("Europe/Rome")
    timestamp = datetime.now(rome).strftime("%d/%m/%Y %H:%M")

    # Subject
    if event_type == "cancellation":
        subject = f"ANNULLAMENTO - {carrier} - {date_str} - {shipment_type}"
    else:
        subject = f"{carrier} - {date_str} - {shipment_type}"

    # Dimensions strings
    package_dimensions_str = f"{length} x {width} x {height} cm"
    pallet_dimensions_str = f"{pallet_length} x {pallet_width} x {pallet_height} cm" if use_pallet else "-"

    payload = {
        # Dedup
        "request_id": str(uuid.uuid4()),

        # Meta
        "event_type": event_type,
        "subject": subject,
        "timestamp": timestamp,
        "shipment_type": shipment_type,

        # Carrier
        "carrier": carrier,

        # Date/Time
        "pickup_date": date_str,
        "time_start": ts,
        "time_end": te,
        "time_window": f"{ts} - {te}",

        # Address — individual
        "company": company,
        "contact_name": contact_name,
        "address": address,
        "zip_code": zip_code,
        "city": city,
        "province": province,
        "phone": phone,
        "reference": reference,
        # Address — formatted
        "full_address": f"{address}, {zip_code} {city} ({province})",
        "address_line1": f"{company} - {contact_name}" if contact_name else company,
        "address_line2": f"{address}, {zip_code} {city} ({province})",

        # Packages — individual
        "num_packages": num_packages,
        "weight_per_package": weight_per_package,
        "weight_per_package_str": f"{weight_per_package} kg",
        "package_length": length,
        "package_width": width,
        "package_height": height,
        # Packages — calculated
        "total_weight": total_weight,
        "total_weight_str": f"{total_weight:.1f} kg",
        "package_dimensions": package_dimensions_str,
        "package_volume_m3": round(package_volume, 3),
        "total_volume_m3": round(total_volume, 3),

        # Pallet
        "use_pallet": use_pallet,
        "use_pallet_str": "Si" if use_pallet else "No",
        "num_pallets": num_pallets if use_pallet else 0,
        "pallet_length": pallet_length if use_pallet else 0,
        "pallet_width": pallet_width if use_pallet else 0,
        "pallet_height": pallet_height if use_pallet else 0,
        "pallet_dimensions": pallet_dimensions_str,

        # Notes
        "notes": notes if notes else "",
        "has_notes": bool(notes),

        # Summary
        "summary_packages": f"{num_packages} colli x {weight_per_package} kg = {total_weight:.1f} kg totali",
        "summary_dimensions": f"Dimensioni collo: {package_dimensions_str}",
        "summary_pallet": f"{num_pallets} pallet ({pallet_dimensions_str})" if use_pallet else "Nessun pallet",
    }

    # Event-type-specific fields
    if event_type == "creation":
        t_start = time(*[int(x) for x in time_start_str.split(":")[:2]])
        t_end = time(*[int(x) for x in time_end_str.split(":")[:2]])
        d = date(*[int(x) for x in pickup_date_str.split("-")])

        payload["pickup_webhook"] = _build_pickup_webhook_payload(
            carrier=carrier, contact_name=contact_name, company=company,
            address=address, city=city, province=province, zip_code=zip_code,
            phone=phone, pickup_date=d, time_start=t_start, time_end=t_end,
            num_packages=num_packages, weight_per_package=weight_per_package,
            length=length, width=width, height=height, notes=notes,
            use_pallet=use_pallet, num_pallets=num_pallets,
            pallet_dimensions_str=pallet_dimensions_str,
        )
    elif event_type == "cancellation":
        payload["cancellation_reason"] = record.get("cancellation_reason")
        cancelled_at_raw = record.get("cancelled_at", "")
        if cancelled_at_raw:
            try:
                dt = datetime.fromisoformat(cancelled_at_raw)
                payload["cancelled_at"] = dt.astimezone(rome).strftime("%d/%m/%Y %H:%M")
            except Exception:
                payload["cancelled_at"] = cancelled_at_raw
        else:
            payload["cancelled_at"] = timestamp

    return payload


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
    # Build a record dict matching DB column format for the shared helper
    record = {
        "carrier": carrier,
        "pickup_date": pickup_date.isoformat(),
        "time_start": time_start.isoformat(),
        "time_end": time_end.isoformat(),
        "company": company,
        "contact_name": contact_name,
        "address": address,
        "zip_code": zip_code,
        "city": city,
        "province": province,
        "phone": phone,
        "reference": reference,
        "num_packages": num_packages,
        "weight_per_package": weight_per_package,
        "length": length,
        "width": width,
        "height": height,
        "use_pallet": use_pallet,
        "num_pallets": num_pallets,
        "pallet_length": pallet_length,
        "pallet_width": pallet_width,
        "pallet_height": pallet_height,
        "notes": notes,
    }
    payload = _build_zapier_payload(record, "creation")

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
    # DISABLED: pickup webhook is on hold until further notice.
    # The payload is still built (pickup_webhook key in payload) for when we re-enable.
    pickup_msg = ""
    pickup_result: Optional[dict] = None
    pickup_url = None  # was: get_secret("pickup", "webhook_url")
    pickup_secret = get_secret("pickup", "webhook_secret")
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
    if not zapier_url and not pickup_url:
        return False, "Nessun webhook configurato. Aggiungi ZAPIER_WEBHOOK_URL.", None

    # If the pickup webhook failed, that's a hard failure
    if pickup_url and pickup_msg:
        return False, pickup_msg, pickup_result

    # Zapier is the active path
    if zapier_msg:
        return False, zapier_msg, None

    return True, "Richiesta inviata", pickup_result


from .pickup_store import get_pickup, cancel_pickup, update_zapier_status


def send_cancellation_notification(pickup_record: dict, reason: str | None) -> bool:
    """Build cancellation Zapier payload and POST to webhook. Returns True if successful."""
    zapier_url = get_secret("zapier", "webhook_url")
    if not zapier_url:
        logger.warning("No Zapier webhook URL configured — cancellation notification skipped")
        return False

    payload = _build_zapier_payload(pickup_record, "cancellation")
    try:
        resp = requests.post(zapier_url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error("Zapier cancellation webhook HTTP %s", resp.status_code)
        return False
    except Exception as e:
        logger.error("Zapier cancellation webhook error: %s", e)
        return False


def cancel_pickup_flow(pickup_id: str, reason: str | None) -> dict:
    """Orchestrate pickup cancellation: validate → cancel → notify.
    Returns a result dict with ok, message, zapier_notified, and optionally status_code for errors.
    """
    from zoneinfo import ZoneInfo

    # Step 1: Fetch and validate
    record = get_pickup(pickup_id)
    if record is None:
        return {"ok": False, "status_code": 404, "message": "Ritiro non trovato"}

    if record.get("pickup_status") == "cancelled":
        return {"ok": False, "status_code": 409, "message": "Pickup già annullato"}

    # Date check — Europe/Rome timezone
    rome = ZoneInfo("Europe/Rome")
    today_rome = datetime.now(rome).date()
    pickup_date = date.fromisoformat(record["pickup_date"])
    if pickup_date < today_rome:
        return {"ok": False, "status_code": 422, "message": "Non è possibile annullare un ritiro passato"}

    # Step 2: Atomic conditional update
    logger.info("Cancelling pickup %s (carrier=%s, date=%s, reason=%s)",
                pickup_id, record["carrier"], record["pickup_date"], reason)
    cancelled_record = cancel_pickup(pickup_id, reason)
    if cancelled_record is None:
        return {"ok": False, "status_code": 409, "message": "Pickup già annullato"}

    # Step 3: Notify via Zapier
    zapier_notified = send_cancellation_notification(cancelled_record, reason)

    # Step 4: Persist notification status
    update_zapier_status(pickup_id, zapier_notified)

    if not zapier_notified:
        logger.error("Zapier notification failed for pickup %s cancellation", pickup_id)

    return {
        "ok": True,
        "message": "Ritiro annullato" if zapier_notified else "Ritiro annullato, ma notifica non inviata",
        "zapier_notified": zapier_notified,
    }
