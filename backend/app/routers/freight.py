"""Freight Request endpoint."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from typing import Optional

from ..limiter import limiter
from ..schemas.freight import FreightRequestForm
from ..core.freight import generate_reference_id, upload_freight_file, send_freight_request

router = APIRouter()

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


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
    contact_email: str = Form(...),
    contact_phone: Optional[str] = Form(None),
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
        contact_email=contact_email,
        contact_phone=contact_phone,
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
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File troppo grande (max 50MB)"}
        })

    # Generate reference ID
    reference_id = generate_reference_id()

    # Upload to Supabase Storage
    try:
        file_url = await asyncio.to_thread(
            upload_freight_file, file_bytes, file.filename, reference_id
        )
    except Exception:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "STORAGE_ERROR", "message": "Errore nel caricamento del file, riprova"}
        })

    # Send to Zapier with download URL
    sender_address = form.model_dump(exclude={"notes", "contact_email", "contact_phone"})
    success, message = await asyncio.to_thread(
        send_freight_request, file_url, file.filename, reference_id, sender_address,
        form.notes, form.contact_email, form.contact_phone
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
