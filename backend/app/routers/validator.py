"""Address Validator endpoints."""
import asyncio
import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import pandas as pd

from ..config import get_settings
from ..services.job_store import job_store
from ..core.zip_validator import ZipValidator
from ..core.security import (
    check_rate_limit, record_usage, validate_excel_content,
    sanitize_filename, record_failed_attempt
)

router = APIRouter()


def _process_validation(
    job_id: str,
    excel_bytes: bytes,
    confidence: int,
    street_confidence: int,
    bypass_pin: str,
    client_ip: str,
):
    """Run address validation in background thread."""
    settings = get_settings()
    try:
        # Parse Excel
        df = pd.read_excel(io.BytesIO(excel_bytes))

        # Content validation
        valid, error = validate_excel_content(df)
        if not valid:
            record_failed_attempt(client_ip)
            job_store.update_status(job_id, "failed", error=f"Invalid content: {error}")
            return

        # Row limit
        if len(df) > settings.max_excel_rows:
            job_store.update_status(job_id, "failed", error=f"Too many rows ({len(df)}). Max: {settings.max_excel_rows}")
            return

        # Rate limit check
        pin_valid = bool(settings.bypass_pin) and bypass_pin == settings.bypass_pin
        if not pin_valid:
            allowed, message, _ = check_rate_limit(client_ip, len(df))
            if not allowed:
                job_store.update_status(job_id, "failed", error=message)
                return

        # Run validation
        validator = ZipValidator(
            confidence_threshold=confidence,
            street_confidence_threshold=street_confidence,
            google_api_key=settings.google_address_validation_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        def progress_callback(current, total, message):
            job_store.update_progress(job_id, current, total, message)

        report, preprocessed_df = validator.process_dataframe(df, progress_callback=progress_callback)

        # Generate output files
        corrected_excel = validator.generate_corrected_excel(preprocessed_df, report)
        review_excel = validator.generate_review_report(report)

        job_store.save_file(job_id, "corrected.xlsx", corrected_excel)
        job_store.save_file(job_id, "review.xlsx", review_excel)

        # Record usage
        if not pin_valid:
            record_usage(client_ip, len(df))

        # Build per-row results
        row_results = []
        for r in report.results:
            if r.is_valid and r.street_verified:
                status = "verified"
            elif r.auto_corrected or r.street_auto_corrected:
                status = "corrected"
            else:
                status = "review"
            corrections = []
            if r.auto_corrected and r.suggested_zip:
                corrections.append(f"CAP \u2192 {r.suggested_zip}")
            if r.street_auto_corrected and r.suggested_street:
                corrections.append(f"Via \u2192 {r.suggested_street}")

            row_results.append({
                "status": status,
                "city": r.city or "",
                "street": r.street or "",
                "original_zip": r.original_zip or "",
                "suggested_zip": r.suggested_zip,
                "suggested_street": r.suggested_street,
                "corrections": corrections,
            })

        # Complete
        job_store.update_status(job_id, "complete", result={
            "total_rows": report.total_rows,
            "valid_count": report.valid_count,
            "corrected_count": report.corrected_count,
            "review_count": report.review_count,
            "skipped_count": report.skipped_count,
            "street_verified_count": report.street_verified_count,
            "street_corrected_count": report.street_corrected_count,
            "po_invalid_count": report.po_invalid_count,
            "results": row_results,
            "files": {
                "corrected": f"/api/v1/jobs/{job_id}/files/corrected.xlsx",
                "review": f"/api/v1/jobs/{job_id}/files/review.xlsx",
            },
        })
    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/validator")
async def create_validator_job(
    request: Request,
    excel_file: UploadFile = File(...),
    confidence_threshold: int = Form(90),
    street_confidence_threshold: int = Form(85),
    bypass_pin: str = Form(""),
):
    settings = get_settings()

    # File size check
    content = await excel_file.read()
    if len(content) / (1024 * 1024) > settings.max_file_size_mb:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {settings.max_file_size_mb}MB"}
        })

    client_ip = request.client.host if request.client else "unknown"

    # Create job and run in background
    job_id = job_store.create_job("validator")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_validation, job_id, content,
        confidence_threshold, street_confidence_threshold, bypass_pin, client_ip,
    )

    return {"ok": True, "data": {"job_id": job_id}}
