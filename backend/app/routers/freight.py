"""Freight Request endpoint."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from typing import Optional

from ..limiter import limiter
from ..schemas.freight import FreightRequestForm
from ..core.freight import generate_reference_id, send_freight_request

router = APIRouter()

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 7 * 1024 * 1024  # 7MB raw (~9.3MB base64, within Zapier's ~10MB limit)


@router.post("/freight/request")
@limiter.limit("30/hour")
async def create_freight_request(
    request: Request,
    file: UploadFile = File(...),
    from_name: str = Form(...),
    from_company: str = Form(...),
    from_street1: str = Form(...),
    from_city: str = Form(...),
    from_state: str = Form(""),
    from_zip: str = Form(...),
    from_country: str = Form("IT"),
    from_phone: str = Form(""),
    notes: Optional[str] = Form(None),
):
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File richiesto"}
        })

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "Formato file non supportato. Usa .xlsx, .xls o .csv"}
        })

    # Validate sender address via schema
    form = FreightRequestForm(
        from_name=from_name,
        from_company=from_company,
        from_street1=from_street1,
        from_city=from_city,
        from_state=from_state,
        from_zip=from_zip,
        from_country=from_country,
        from_phone=from_phone,
        notes=notes,
    )

    # Read file
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File richiesto"}
        })
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File troppo grande (max 7MB)"}
        })

    # Generate reference ID
    reference_id = generate_reference_id()

    # Send to Zapier with base64-encoded file
    sender_address = form.model_dump(exclude={"notes"})
    success, message = await asyncio.to_thread(
        send_freight_request, file_bytes, file.filename, reference_id, sender_address, form.notes
    )

    if not success:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "WEBHOOK_ERROR", "message": message}
        })

    return {
        "ok": True,
        "data": {
            "message": "Richiesta inviata",
            "reference_id": reference_id,
        },
    }
