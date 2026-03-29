"""Shipments — parse Excel, call rates webhook, create shipments."""
import io
import math
import time
import requests
from typing import Optional, Callable
from urllib.parse import urlparse, urlunparse

import pandas as pd

from .config_compat import get_secret
from .excel_parser import ExcelParser
from .logging_config import get_logger
from .utils import map_columns

logger = get_logger(__name__)

POLL_INTERVAL = 15  # seconds between polls


# Columns to search for identifiers (priority order — ShippyPro order number is most reliable)
_POD_IDENTIFIER_COLUMNS = [
    # ShippyPro order numbers — always present, works even for external shipments
    ("numero ordine shippypro", "shippypro_order"),
    ("shippypro order", "shippypro_order"),
    ("numero ordine", "shippypro_order"),
    # Tracking numbers
    ("tracking", "tracking"),
    ("tracking number", "tracking"),
    ("trackingnumber", "tracking"),
    ("tracking_number", "tracking"),
    ("codice tracking", "tracking"),
    ("n. tracking", "tracking"),
    ("numero tracking", "tracking"),
    # Marketplace order IDs
    ("id ordine marketplace", "marketplace_id"),
    ("marketplace order id", "marketplace_id"),
    ("order id", "marketplace_id"),
]

SMALL_BATCH_THRESHOLD = 50  # Below this, use sequential single calls


def extract_identifiers_from_excel(excel_bytes: bytes, filename: str = "upload.xls") -> list[str]:
    """Extract POD identifiers from an Excel file.

    Searches for multiple column types in priority order:
    1. Numero ordine ShippyPro (most reliable — always present, works as direct OrderID)
    2. Tracking numbers
    3. ID Ordine Marketplace

    Uses the best available column. Falls back to ExcelParser's tracking
    column detection for non-ShippyPro files.

    Returns a deduplicated list of non-empty identifiers.
    """
    parser = ExcelParser()

    try:
        df = parser._try_read_excel(io.BytesIO(excel_bytes), filename)
    except Exception as e:
        raise ValueError(f"Impossibile leggere il file: {e}")

    df.columns = [str(col).strip().replace('\n', ' ') for col in df.columns]
    col_lower_map = {col.lower().strip(): col for col in df.columns}

    # Find the best identifier column
    found_col = None
    found_type = None
    for alias, col_type in _POD_IDENTIFIER_COLUMNS:
        if alias in col_lower_map:
            found_col = col_lower_map[alias]
            found_type = col_type
            break

    # Fallback: use ExcelParser's tracking column finder
    if not found_col:
        found_col = parser._find_column(df, 'tracking')
        found_type = "tracking"

    if not found_col:
        raise ValueError(
            f"Nessuna colonna identificativo trovata. "
            f"Servono: Tracking, Numero ordine ShippyPro, o ID Ordine Marketplace. "
            f"Colonne trovate: {', '.join(df.columns.tolist())}"
        )

    logger.info("POD identifier column: '%s' (type: %s) in %d rows", found_col, found_type, len(df))

    identifiers = []
    seen: set[str] = set()
    for val in df[found_col]:
        if pd.isna(val):
            continue
        # For numeric ShippyPro order IDs, convert float to int string
        if isinstance(val, float) and val == int(val):
            s = str(int(val))
        else:
            s = str(val).strip()
        if not s or s.lower() == 'nan':
            continue
        normalized = s.upper().replace(' ', '')
        if normalized and normalized not in seen:
            seen.add(normalized)
            identifiers.append(s.strip())  # Keep original casing for marketplace IDs

    return identifiers


def send_sequential_pod_requests(
    identifiers: list[str],
    on_progress: Optional[Callable[[str, dict], None]] = None,
) -> dict:
    """Fetch PODs sequentially using single calls (for small batches <50).

    Uses the single POD endpoint with a small delay between calls.
    Returns a result dict matching the bulk format for consistency.
    """
    results = []
    summary = {"found": 0, "no_pod": 0, "unmatched": 0, "ambiguous": 0, "error": 0}
    total = len(identifiers)

    for i, identifier in enumerate(identifiers):
        result = fetch_single_pod(identifier)

        status = result["status"]
        item: dict = {"input_value": identifier, "status": status}

        if status == "found":
            item["tracking_number"] = result.get("tracking_number", "")
            item["carrier"] = result.get("carrier", "")
            item["pod_base64"] = result.get("pod_base64", "")
            summary["found"] += 1
        elif status == "not_found":
            item["status"] = "unmatched"
            item["message"] = result.get("error_message", "")
            summary["unmatched"] += 1
        elif status == "ambiguous":
            item["message"] = result.get("error_message", "")
            summary["ambiguous"] += 1
        else:
            item["status"] = "error"
            item["message"] = result.get("error_message", "")
            summary["error"] += 1

        results.append(item)

        if on_progress:
            on_progress(
                f"POD: {i + 1}/{total} elaborati ({summary['found']} trovati)",
                {"progress": {"total": total, "fetched": i + 1, "found": summary["found"]}, "status": "processing"},
            )

        # Small delay to respect rate limits (not needed for last item)
        if i < total - 1:
            time.sleep(1)

    return {
        "status": "completed",
        "summary": {**summary, "total_input": total, "duplicates_removed": 0},
        "results": results,
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
        phone = get("phone") or ""  # Platform fills fallback contacts server-side

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

    # Non-200 responses indicate infrastructure errors (rate limit, auth, gateway)
    if resp.status_code != 200:
        try:
            body = resp.json()
            detail = body.get("detail", body.get("error", body.get("message", "")))
        except ValueError:
            detail = resp.text[:200]
        logger.error("Ship webhook HTTP %d: %s", resp.status_code, detail)
        return {
            "status": "failed",
            "error_message": f"Errore HTTP {resp.status_code}: {detail}" if detail else f"Errore HTTP {resp.status_code}",
        }

    try:
        result = resp.json()
    except ValueError:
        return {
            "status": "failed",
            "error_message": "Risposta non valida dal server spedizioni.",
        }

    # Check status field per Shipments platform spec
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
            "error_details": result.get("error_details"),
            "sp_order_id": result.get("sp_order_id"),
            "data": result,
        }
    else:
        # Unexpected status
        return {
            "status": "failed",
            "error_message": f"Stato imprevisto: {status}. Risposta: {result}",
        }


# ---------------------------------------------------------------------------
# Batch Ship
# ---------------------------------------------------------------------------

BATCH_POLL_INTERVAL = 10  # seconds between batch status polls


def _derive_batch_ship_url(rates_url: str) -> str:
    """Derive /api/webhook/ship-batch from the rates webhook URL."""
    parsed = urlparse(rates_url.rstrip("/"))
    path_parts = parsed.path.rsplit("/", 1)
    batch_path = path_parts[0] + "/ship-batch" if len(path_parts) > 1 else "/api/webhook/ship-batch"
    return urlunparse(parsed._replace(path=batch_path))


def _get_webhook_headers() -> dict:
    """Build common headers for webhook calls."""
    secret = get_secret("rates", "webhook_secret")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Webhook-Secret"] = secret
    return headers


def build_batch_shipments(
    parsed_shipments: list[dict],
    carrier_name: str,
    carrier_id: int,
    carrier_service: str,
    from_address: dict,
    transaction_id_prefix: str = "",
) -> list[dict]:
    """Enrich parsed shipment dicts with carrier selection and from_address.

    Takes the output of parse_shipments_excel() and adds the fields
    required by the ship-batch webhook.
    """
    batch = []
    for i, shipment in enumerate(parsed_shipments):
        row = {
            "carrier_name": carrier_name,
            "carrier_id": carrier_id,
            "carrier_service": carrier_service,
            "from_address": from_address,
            "to_address": shipment["to_address"],
            "parcels": shipment["parcels"],
        }
        if shipment.get("content_description"):
            row["content_description"] = shipment["content_description"]
        if transaction_id_prefix:
            row["transaction_id"] = f"{transaction_id_prefix}-{i + 1}"
        batch.append(row)
    return batch


def send_batch_ship_request(
    batch_key: str,
    shipments: list[dict],
    on_progress: Optional[Callable[[str, dict], None]] = None,
) -> tuple[bool, str, Optional[dict]]:
    """Submit a batch ship job and poll until complete.

    The batch API is async: POST returns a batch_id instantly,
    then GET /api/webhook/ship-batch/{batch_id} is polled.

    on_progress is called with (message, progress_dict) on each poll cycle.

    Returns:
        (success, message, result_dict)
        result_dict contains: batch_id, total, status, progress, shipments[]
    """
    rates_url = get_secret("rates", "webhook_url")
    if not rates_url:
        return False, "RATES_WEBHOOK_URL non configurato.", None

    batch_url = _derive_batch_ship_url(rates_url)
    headers = _get_webhook_headers()

    payload = {
        "batch_key": batch_key,
        "shipments": shipments,
    }

    logger.info("Batch ship request to %s — %d shipments, key=%s",
                batch_url, len(shipments), batch_key)

    # --- Step 1: Submit batch ---
    try:
        resp = requests.post(batch_url, json=payload, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {e}", None

    # Handle 422 validation errors (row-level)
    if resp.status_code == 422:
        try:
            body = resp.json()
            detail = body.get("detail", {})
            if isinstance(detail, dict) and "errors" in detail:
                return False, "Validazione fallita", {
                    "validation_errors": detail["errors"],
                    "message": detail.get("message", "Validation failed"),
                }
            return False, f"Validazione fallita: {detail}", None
        except ValueError:
            return False, f"Errore validazione (HTTP 422)", None

    if resp.status_code not in (200, 201, 202):
        try:
            body = resp.json()
            detail = body.get("detail", body.get("error", ""))
            msg = f"Errore: {detail}" if detail else f"Errore HTTP {resp.status_code}"
        except ValueError:
            msg = f"Errore HTTP {resp.status_code}"
        return False, msg, None

    try:
        submit_data = resp.json()
        batch_id = submit_data.get("batch_id")
    except ValueError:
        return False, "Risposta non valida dal server.", None

    if not batch_id:
        return False, "Il server non ha restituito un batch_id.", None

    poll_url = f"{batch_url}/{batch_id}"
    logger.info("Batch %s submitted — polling %s", batch_id, poll_url)

    if on_progress:
        total = submit_data.get("total", len(shipments))
        on_progress(f"Batch avviato: {total} spedizioni in elaborazione...", {
            "batch_id": batch_id, "total": total, "status": "processing",
        })

    # --- Step 2: Poll for results ---
    start_time = time.time()
    max_poll_time = 900  # 15 minutes

    while True:
        time.sleep(BATCH_POLL_INTERVAL)
        elapsed = int(time.time() - start_time)

        if elapsed > max_poll_time:
            return False, f"Timeout: il batch non è terminato dopo {max_poll_time // 60} minuti.", {
                "batch_id": batch_id, "status": "timeout",
            }

        try:
            resp = requests.get(poll_url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.warning("Batch poll error (will retry): %s", e)
            continue

        if resp.status_code == 404:
            return False, "Batch non trovato o scaduto sul server remoto.", None
        if resp.status_code != 200:
            continue  # Transient error, retry

        try:
            status_data = resp.json()
        except ValueError:
            continue

        batch_status = status_data.get("status")
        progress = status_data.get("progress", {})

        if on_progress:
            shipped = progress.get("shipped", 0)
            failed = progress.get("failed", 0)
            queued = progress.get("queued", 0)
            total = status_data.get("total", 0)
            done = shipped + failed
            on_progress(
                f"Elaborazione: {done}/{total} completate ({shipped} OK, {failed} errori, {queued} in coda)",
                {"batch_id": batch_id, "progress": progress, "status": batch_status},
            )

        if batch_status == "completed":
            logger.info("Batch %s completed: %s", batch_id, progress)
            return True, "Batch completato", status_data

        if batch_status == "failed":
            error = status_data.get("error", "Errore sconosciuto")
            return False, f"Batch fallito: {error}", status_data


# ---------------------------------------------------------------------------
# POD (Proof of Delivery)
# ---------------------------------------------------------------------------

POD_POLL_INTERVAL = 3  # seconds between POD job polls


def _derive_pod_url(rates_url: str) -> str:
    """Derive /api/webhook/pod from the rates webhook URL."""
    parsed = urlparse(rates_url.rstrip("/"))
    path_parts = parsed.path.rsplit("/", 1)
    pod_path = path_parts[0] + "/pod" if len(path_parts) > 1 else "/api/webhook/pod"
    return urlunparse(parsed._replace(path=pod_path))


def _derive_pod_batch_url(rates_url: str) -> str:
    """Derive /api/webhook/pod-batch from the rates webhook URL."""
    parsed = urlparse(rates_url.rstrip("/"))
    path_parts = parsed.path.rsplit("/", 1)
    pod_path = path_parts[0] + "/pod-batch" if len(path_parts) > 1 else "/api/webhook/pod-batch"
    return urlunparse(parsed._replace(path=pod_path))


def _derive_pod_jobs_url(rates_url: str, job_id: str) -> str:
    """Derive /api/webhook/pod-jobs/{job_id} from the rates webhook URL."""
    parsed = urlparse(rates_url.rstrip("/"))
    path_parts = parsed.path.rsplit("/", 1)
    base = path_parts[0] if len(path_parts) > 1 else "/api/webhook"
    return urlunparse(parsed._replace(path=f"{base}/pod-jobs/{job_id}"))


def fetch_single_pod(identifier: str) -> dict:
    """Fetch a single POD by tracking number or transaction ID.

    Returns:
        Dict with keys: status ("found"|"not_found"|"error"),
        pod_base64, tracking_number, carrier, file_type, error_message.
    """
    rates_url = get_secret("rates", "webhook_url")
    if not rates_url:
        return {"status": "error", "error_message": "RATES_WEBHOOK_URL non configurato."}

    pod_url = _derive_pod_url(rates_url)
    headers = _get_webhook_headers()

    logger.info("POD request for: %s", identifier)

    try:
        resp = requests.post(pod_url, json={"identifier": identifier}, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        return {"status": "error", "error_message": f"Errore connessione: {e}"}

    if resp.status_code == 200:
        result = resp.json()
        return {
            "status": "found",
            "pod_base64": result.get("pod_base64", ""),
            "tracking_number": result.get("tracking_number", ""),
            "carrier": result.get("carrier", ""),
            "file_type": result.get("file_type", "application/pdf"),
        }

    # Error responses
    try:
        body = resp.json()
        detail = body.get("detail", body.get("error", body.get("message", "")))
    except ValueError:
        detail = resp.text[:200]

    if resp.status_code == 404:
        return {"status": "not_found", "error_message": detail or "Spedizione non trovata o POD non ancora disponibile."}
    elif resp.status_code == 409:
        return {"status": "ambiguous", "error_message": detail or "Identificativo corrisponde a più spedizioni."}
    elif resp.status_code == 429:
        return {"status": "error", "error_message": "Rate limit raggiunto. Riprova tra qualche secondo."}
    else:
        return {"status": "error", "error_message": f"Errore HTTP {resp.status_code}: {detail}"}


def send_batch_pod_request(
    identifiers: list[str],
    on_progress: Optional[Callable[[str, dict], None]] = None,
) -> tuple[bool, str, Optional[dict]]:
    """Submit a bulk POD job and poll until complete.

    Returns:
        (success, message, result_dict)
        result_dict contains: job_id, status, summary, results[]
    """
    rates_url = get_secret("rates", "webhook_url")
    if not rates_url:
        return False, "RATES_WEBHOOK_URL non configurato.", None

    batch_url = _derive_pod_batch_url(rates_url)
    headers = _get_webhook_headers()

    logger.info("Bulk POD request — %d identifiers", len(identifiers))

    # --- Step 1: Submit ---
    try:
        resp = requests.post(batch_url, json={"identifiers": identifiers}, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {e}", None

    if resp.status_code == 409:
        return False, "Un altro job POD è già in corso. Riprova tra qualche minuto.", None

    if resp.status_code == 422:
        try:
            detail = resp.json().get("detail", "Input non valido")
        except ValueError:
            detail = "Input non valido"
        return False, f"Validazione fallita: {detail}", None

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", "")
        except ValueError:
            detail = ""
        return False, f"Errore HTTP {resp.status_code}: {detail}", None

    try:
        submit_data = resp.json()
        remote_job_id = submit_data.get("job_id")
    except ValueError:
        return False, "Risposta non valida.", None

    if not remote_job_id:
        return False, "Il server non ha restituito un job_id.", None

    poll_url = _derive_pod_jobs_url(rates_url, remote_job_id)
    total = submit_data.get("total", len(identifiers))
    logger.info("POD job %s submitted — polling %s", remote_job_id, poll_url)

    if on_progress:
        on_progress(f"Job POD avviato: {total} identificativi in elaborazione...", {
            "job_id": remote_job_id, "total": total, "status": "processing",
        })

    # --- Step 2: Poll ---
    start_time = time.time()
    max_poll_time = 300  # 5 minutes (POD is faster than ship)

    while True:
        time.sleep(POD_POLL_INTERVAL)
        elapsed = int(time.time() - start_time)

        if elapsed > max_poll_time:
            return False, f"Timeout: il job POD non è terminato dopo {max_poll_time // 60} minuti.", {
                "job_id": remote_job_id, "status": "timeout",
            }

        try:
            resp = requests.get(poll_url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            logger.warning("POD poll error (will retry): %s", e)
            continue

        if resp.status_code == 404:
            return False, "Job POD non trovato o scaduto.", None
        if resp.status_code != 200:
            continue

        try:
            status_data = resp.json()
        except ValueError:
            continue

        job_status = status_data.get("status")
        progress = status_data.get("progress", {})

        if on_progress:
            fetched = progress.get("fetched", 0)
            found = progress.get("found", 0)
            total_p = progress.get("total", total)
            on_progress(
                f"POD: {fetched}/{total_p} elaborati ({found} trovati)",
                {"job_id": remote_job_id, "progress": progress, "status": job_status},
            )

        if job_status == "completed":
            logger.info("POD job %s completed: %s", remote_job_id, status_data.get("summary"))
            return True, "Job POD completato", status_data

        if job_status == "failed":
            error = status_data.get("error", "Errore sconosciuto")
            return False, f"Job POD fallito: {error}", status_data


def download_pod_file(remote_job_id: str, file_key: str) -> tuple[bool, str, Optional[bytes]]:
    """Download a single POD PDF from a completed bulk job.

    Returns:
        (success, error_message, pdf_bytes)
    """
    rates_url = get_secret("rates", "webhook_url")
    if not rates_url:
        return False, "RATES_WEBHOOK_URL non configurato.", None

    url = _derive_pod_jobs_url(rates_url, remote_job_id) + f"/files/{file_key}"
    headers = _get_webhook_headers()

    try:
        resp = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {e}", None

    if resp.status_code == 200:
        return True, "", resp.content

    try:
        detail = resp.json().get("detail", "")
    except ValueError:
        detail = resp.text[:200]
    return False, f"Errore HTTP {resp.status_code}: {detail}", None


def download_pod_zip(remote_job_id: str) -> tuple[bool, str, Optional[bytes]]:
    """Download all PODs from a completed bulk job as a ZIP archive.

    Returns:
        (success, error_message, zip_bytes)
    """
    rates_url = get_secret("rates", "webhook_url")
    if not rates_url:
        return False, "RATES_WEBHOOK_URL non configurato.", None

    url = _derive_pod_jobs_url(rates_url, remote_job_id) + "/zip"
    headers = _get_webhook_headers()

    try:
        resp = requests.get(url, headers=headers, timeout=60)
    except requests.exceptions.RequestException as e:
        return False, f"Errore connessione: {e}", None

    if resp.status_code == 200:
        return True, "", resp.content
    if resp.status_code == 409:
        return False, "Il job è ancora in elaborazione.", None

    try:
        detail = resp.json().get("detail", "")
    except ValueError:
        detail = resp.text[:200]
    return False, f"Errore HTTP {resp.status_code}: {detail}", None
