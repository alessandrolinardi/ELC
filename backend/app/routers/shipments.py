"""Shipments Quotation endpoints."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from ..limiter import limiter
from ..services.job_store import job_store
from ..core.shipments import parse_shipments_excel, build_from_address, send_rates_request

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
