"""Shipments endpoints — quotation + ship + POD."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import Response

from ..limiter import limiter
from ..services.job_store import job_store
from ..core.shipments import (
    parse_shipments_excel, build_from_address, send_rates_request,
    send_ship_request, build_batch_shipments, send_batch_ship_request,
    fetch_single_pod, send_batch_pod_request, download_pod_file, download_pod_zip,
)
from ..schemas.shipments import ShipRequest, ShipBatchRequest, PodRequest, PodBatchRequest

router = APIRouter()


def _process_quotation(
    job_id: str,
    excel_bytes: bytes,
    from_address: dict,
):
    """Background task: parse Excel → call rates webhook → store result."""
    try:
        # Phase 1: Parse Excel
        job_store.update_progress(job_id, 0, 100, "Analisi file in corso...")
        shipments = parse_shipments_excel(excel_bytes)

        if not shipments:
            job_store.update_status(job_id, "failed", error="Nessuna spedizione trovata nel file.")
            return

        count = len(shipments)
        est_minutes = max(1, round(count / 1.8 / 60))
        job_store.update_progress(
            job_id, 10, 100,
            f"{count} spedizioni trovate. Richiesta tariffe in corso... (~{est_minutes} min)"
        )

        # Phase 2: Call rates webhook (async job — POST then poll)
        def on_progress(msg: str):
            job_store.update_progress(job_id, 50, 100, msg)

        payload = {"from_address": from_address, "shipments": shipments}
        success, message, result = send_rates_request(payload, on_progress=on_progress)

        if not success:
            job_store.update_status(job_id, "failed", error=message)
            return

        # Store webhook response as result
        job_store.update_status(job_id, "complete", result=result or {"message": message})

    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/shipments-quotation")
@limiter.limit("10/hour")
async def create_shipments_quotation(
    request: Request,
    file: UploadFile = File(...),
    from_name: str = Form(...),
    from_company: str = Form(""),
    from_street1: str = Form(...),
    from_city: str = Form(...),
    from_state: str = Form(""),
    from_zip: str = Form(...),
    from_country: str = Form("IT"),
    from_phone: str = Form(...),
    from_email: str = Form(""),
):
    # Validate file
    if not file.filename or not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "INVALID_FILE", "message": "Il file deve essere in formato Excel (.xlsx)"}
        })

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": "Il file supera il limite di 50MB"}
        })

    from_address = build_from_address(
        name=from_name, street1=from_street1, city=from_city,
        zip_code=from_zip, country=from_country, phone=from_phone,
        company=from_company, state=from_state, email=from_email,
    )

    job_id = job_store.create_job("shipments_quotation")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _process_quotation, job_id, content, from_address)

    return {"ok": True, "data": {"job_id": job_id}}


# --- Ship endpoint ---

def _process_ship(job_id: str, ship_data: dict):
    """Background task: call ship webhook → store result."""
    try:
        job_store.update_progress(job_id, 0, 100, "Creazione spedizione in corso...")
        result = send_ship_request(ship_data)

        job_store.update_progress(job_id, 90, 100, "Elaborazione risposta...")

        if result["status"] == "shipped":
            job_store.update_status(job_id, "complete", result=result)
        else:
            job_store.update_status(job_id, "failed", error=result.get("error_message", "Errore sconosciuto"))

    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/ship")
@limiter.limit("10/hour")
async def create_shipment(request: Request, body: ShipRequest):
    """Create a shipment with carrier label via the Ship webhook.

    Returns a job_id for polling — the ship call takes ~6-8s (Ship + GetOrder).
    """
    # Build the payload matching the webhook spec
    ship_data = {
        "carrier_name": body.carrier_name.value,
        "carrier_id": body.carrier_id,
        "carrier_service": body.carrier_service,
        "from_address": body.from_address.model_dump(),
        "to_address": body.to_address.model_dump(),
        "parcels": [p.model_dump() for p in body.parcels],
        "content_description": body.content_description,
        "insurance": body.insurance,
        "cash_on_delivery": body.cash_on_delivery,
        "incoterm": body.incoterm,
    }
    if body.total_value is not None:
        ship_data["total_value"] = body.total_value
    if body.transaction_id:
        ship_data["transaction_id"] = body.transaction_id

    job_id = job_store.create_job("ship")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _process_ship, job_id, ship_data)

    return {"ok": True, "data": {"job_id": job_id}}


# --- Batch Ship endpoint ---

def _process_batch_ship(
    job_id: str,
    batch_key: str,
    shipments: list[dict],
):
    """Background task: submit batch to ship-batch webhook → poll → store result."""
    try:
        def on_progress(message: str, data: dict):
            progress = data.get("progress", {})
            shipped = progress.get("shipped", 0)
            total_done = shipped + progress.get("failed", 0)
            total = data.get("total", len(shipments))
            pct = int(total_done / total * 100) if total > 0 else 0
            job_store.update_progress(job_id, pct, 100, message)

        success, message, result = send_batch_ship_request(
            batch_key=batch_key,
            shipments=shipments,
            on_progress=on_progress,
        )

        if not success:
            # Attach validation errors if present
            error_result = None
            if result and result.get("validation_errors"):
                error_result = {"validation_errors": result["validation_errors"]}
            job_store.update_status(job_id, "failed", error=message, result=error_result)
            return

        job_store.update_status(job_id, "complete", result=result or {"message": message})

    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/ship-batch")
@limiter.limit("5/hour")
async def create_batch_shipment(request: Request, body: ShipBatchRequest):
    """Create a batch of shipments with carrier labels via the ship-batch webhook.

    Accepts pre-parsed shipments (from quotation flow) enriched with carrier selection.
    Returns a job_id for polling — batch processing takes ~8 min for 400 shipments.
    """
    batch_shipments = build_batch_shipments(
        parsed_shipments=body.shipments,
        carrier_name=body.carrier_name.value,
        carrier_id=body.carrier_id,
        carrier_service=body.carrier_service,
        from_address=body.from_address.model_dump(),
        transaction_id_prefix=body.transaction_id_prefix or "",
    )

    job_id = job_store.create_job("ship_batch")
    batch_key = body.batch_key

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _process_batch_ship, job_id, batch_key, batch_shipments)

    return {"ok": True, "data": {"job_id": job_id, "batch_key": batch_key, "total": len(batch_shipments)}}


# --- POD endpoints ---

@router.post("/jobs/pod")
@limiter.limit("30/hour")
async def get_pod(request: Request, body: PodRequest):
    """Fetch a single Proof of Delivery by tracking number or transaction ID.

    Returns the POD as base64-encoded PDF in the response.
    Synchronous — no job polling needed (~2-5s).
    """
    result = await asyncio.get_running_loop().run_in_executor(
        None, fetch_single_pod, body.identifier,
    )

    if result["status"] == "found":
        return {"ok": True, "data": result}
    else:
        return {"ok": False, "error": {
            "code": result["status"].upper(),
            "message": result.get("error_message", "POD non disponibile"),
        }}


def _process_batch_pod(job_id: str, identifiers: list[str]):
    """Background task: submit bulk POD job → poll → store result."""
    try:
        def on_progress(message: str, data: dict):
            progress = data.get("progress", {})
            fetched = progress.get("fetched", 0)
            total = progress.get("total", len(identifiers))
            pct = int(fetched / total * 100) if total > 0 else 0
            job_store.update_progress(job_id, pct, 100, message)

        success, message, result = send_batch_pod_request(
            identifiers=identifiers,
            on_progress=on_progress,
        )

        if not success:
            job_store.update_status(job_id, "failed", error=message)
            return

        job_store.update_status(job_id, "complete", result=result or {"message": message})

    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/pod-batch")
@limiter.limit("10/hour")
async def get_pod_batch(request: Request, body: PodBatchRequest):
    """Fetch PODs for up to 500 tracking numbers / transaction IDs.

    Returns a job_id for polling. Processing takes ~1-3 min depending on count.
    """
    job_id = job_store.create_job("pod_batch")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _process_batch_pod, job_id, body.identifiers)

    return {"ok": True, "data": {"job_id": job_id, "total": len(body.identifiers)}}


@router.post("/jobs/pod-download")
@limiter.limit("30/hour")
async def download_single_pod_file(request: Request, remote_job_id: str = Form(...), file_key: str = Form(...)):
    """Download a single POD PDF from a completed bulk job on the Shipments platform."""
    success, error, pdf_bytes = await asyncio.get_running_loop().run_in_executor(
        None, download_pod_file, remote_job_id, file_key,
    )
    if not success:
        raise HTTPException(status_code=502, detail=error)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="pod_{file_key}.pdf"'})


@router.post("/jobs/pod-download-zip")
@limiter.limit("10/hour")
async def download_pod_zip_file(request: Request, remote_job_id: str = Form(...)):
    """Download all PODs from a completed bulk job as a ZIP archive."""
    success, error, zip_bytes = await asyncio.get_running_loop().run_in_executor(
        None, download_pod_zip, remote_job_id,
    )
    if not success:
        raise HTTPException(status_code=502, detail=error)
    return Response(content=zip_bytes, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="pods_{remote_job_id[:8]}.zip"'})
