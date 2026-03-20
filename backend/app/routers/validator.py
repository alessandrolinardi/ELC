"""Address Validator endpoints."""
import asyncio
import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import pandas as pd

from ..config import get_settings
from ..services.job_store import job_store
from ..core.zip_validator import ZipValidator
from ..core.address_parser import AddressParser
from ..core.models import ParsedAddress
from ..core.security import (
    check_rate_limit, record_usage, validate_excel_content,
    sanitize_filename, record_failed_attempt
)
from ..schemas.validator import ConfirmRequest

router = APIRouter()


# ---------------------------------------------------------------------------
# Phase 1: Parse only (AI parsing, no Google validation)
# ---------------------------------------------------------------------------

def _process_parse(
    job_id: str,
    excel_bytes: bytes,
    confidence: int,
    street_confidence: int,
    pin_valid: bool,
    client_ip: str,
):
    """Run AI address parsing in background thread (Phase 1)."""
    settings = get_settings()
    try:
        # Parse Excel
        df = pd.read_excel(io.BytesIO(excel_bytes))
        df = df.reset_index(drop=True)

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
        if not pin_valid:
            allowed, message, _ = check_rate_limit(client_ip, len(df))
            if not allowed:
                job_store.update_status(job_id, "failed", error=message)
                return

        # Build raw addresses for parser
        validator = ZipValidator(
            confidence_threshold=confidence,
            street_confidence_threshold=street_confidence,
            google_api_key=settings.google_address_validation_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )
        col_map = validator._map_columns(df)

        def progress_callback(current, total, message):
            job_store.update_progress(job_id, current, total, message)

        progress_callback(0, 100, "Parsing addresses with AI...")

        raw_addresses = []
        for idx, row in df.iterrows():
            street = str(row.get(col_map.get('street', ''), ''))
            city = str(row.get(col_map['city'], ''))
            zip_val = str(row.get(col_map['zip'], ''))
            raw_addresses.append({"street": street, "city": city, "zip": zip_val})

        parsed_addresses = validator.address_parser.parse_all(raw_addresses)

        progress_callback(100, 100, "Parsing complete")

        # Build per-row data
        rows = []
        ai_parsed = 0
        regex_fallback = 0
        ai_modified = 0
        unchanged = 0

        for i, (parsed_addr, raw) in enumerate(zip(parsed_addresses, raw_addresses)):
            original_street = raw["street"]
            parsed_street = parsed_addr.full_street
            changed = original_street.strip().lower() != parsed_street.strip().lower()

            changes = []
            if changed:
                changes.append(f"street: {original_street} → {parsed_street}")

            method = parsed_addr.parse_method
            if method == "ai":
                ai_parsed += 1
            else:
                regex_fallback += 1

            if changed:
                ai_modified += 1
            else:
                unchanged += 1

            rows.append({
                "index": i,
                "original": {"street": original_street, "city": raw["city"], "zip": raw["zip"]},
                "parsed": {"street": parsed_street, "city": raw["city"], "zip": raw["zip"]},
                "parsed_components": {
                    "street_prefix": parsed_addr.street_prefix,
                    "street_name": parsed_addr.street_name,
                    "house_number": parsed_addr.house_number,
                    "location_info": parsed_addr.location_info,
                    "country_code": parsed_addr.country_code,
                },
                "method": method,
                "changed": changed,
                "changes": changes,
            })

        # Save original Excel to disk for Phase 2
        job_store.save_file(job_id, "original.xlsx", excel_bytes)

        # Build result with config for Phase 2
        result = {
            "parsing_summary": {
                "total": len(raw_addresses),
                "ai_parsed": ai_parsed,
                "regex_fallback": regex_fallback,
                "ai_modified": ai_modified,
                "unchanged": unchanged,
            },
            "rows": rows,
            "config": {
                "confidence": confidence,
                "street_confidence": street_confidence,
                "pin_valid": pin_valid,
                "client_ip": client_ip,
            },
        }

        job_store.update_status(job_id, "parsed", result=result)
    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


# ---------------------------------------------------------------------------
# Phase 2: Validate (Google validation on confirmed/edited addresses)
# ---------------------------------------------------------------------------

def _process_validate(
    job_id: str,
    parsed_rows: list,
    confidence: int,
    street_confidence: int,
    pin_valid: bool,
    client_ip: str,
    retry_regex: bool,
):
    """Run Google validation in background thread (Phase 2)."""
    settings = get_settings()
    try:
        # Retry regex rows if requested
        if retry_regex:
            regex_rows = [r for r in parsed_rows if r["method"] == "regex" and not r.get("edited")]
            if regex_rows:
                job_store.update_progress(job_id, 0, len(regex_rows), "Nuovo tentativo AI...")
                parser = AddressParser(api_key=settings.anthropic_api_key)
                addresses = [
                    {"street": r["original"]["street"], "city": r["original"]["city"], "zip": r["original"]["zip"]}
                    for r in regex_rows
                ]
                try:
                    re_parsed = parser.parse_all(addresses)
                    for row, new_parsed in zip(regex_rows, re_parsed):
                        row["parsed"]["street"] = new_parsed.full_street
                        row["parsed_components"] = {
                            "street_prefix": new_parsed.street_prefix,
                            "street_name": new_parsed.street_name,
                            "house_number": new_parsed.house_number,
                            "location_info": new_parsed.location_info,
                            "country_code": new_parsed.country_code,
                        }
                        row["method"] = new_parsed.parse_method
                except Exception:
                    pass  # Keep regex results

        # Load original Excel — reset index to ensure 0-based alignment
        excel_path = job_store.get_file_path(job_id, "original.xlsx")
        if not excel_path:
            job_store.update_status(job_id, "failed", error="Original Excel file not found")
            return
        df = pd.read_excel(excel_path).reset_index(drop=True)

        # Build ParsedAddress objects from confirmed rows
        parsed_addresses = []
        for row in parsed_rows:
            comp = row["parsed_components"]
            parsed_addresses.append(ParsedAddress(
                street_prefix=comp["street_prefix"],
                street_name=comp["street_name"],
                house_number=comp["house_number"],
                location_info=comp.get("location_info", ""),
                country_code=comp.get("country_code", "IT"),
                confidence="medium",
            ))

        # Run Google validation (Phase 2)
        validator = ZipValidator(
            confidence_threshold=confidence,
            street_confidence_threshold=street_confidence,
            google_api_key=settings.google_address_validation_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        def progress_callback(current, total, message):
            job_store.update_progress(job_id, current, total, message)

        report, preprocessed_df = validator._validate_addresses(df, parsed_addresses, progress_callback)

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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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

    # Validate bypass_pin in request handler (not in background thread)
    pin_valid = bool(settings.bypass_pin) and bypass_pin == settings.bypass_pin

    # Create job and run Phase 1 in background
    job_id = job_store.create_job("validator")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_parse, job_id, content,
        confidence_threshold, street_confidence_threshold, pin_valid, client_ip,
    )

    return {"ok": True, "data": {"job_id": job_id}}


@router.post("/jobs/{job_id}/confirm")
async def confirm_validation(job_id: str, body: ConfirmRequest):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "JOB_NOT_FOUND", "message": "Job not found or expired"}
        })
    if status["status"] != "parsed":
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "INVALID_STATE", "message": f"Job is in state '{status['status']}', expected 'parsed'"}
        })

    # Apply user edits
    parsed_rows = status["result"]["rows"]
    for idx_str, field_edits in body.edits.items():
        idx = int(idx_str)
        row = next((r for r in parsed_rows if r["index"] == idx), None)
        if row:
            row["parsed"].update(field_edits)
            if "street" in field_edits:
                parser = AddressParser()
                re_parsed = parser.parse_single_regex(
                    field_edits["street"],
                    row["parsed"].get("city", ""),
                    row["parsed"].get("zip", ""),
                )
                row["parsed_components"] = {
                    "street_prefix": re_parsed.street_prefix,
                    "street_name": re_parsed.street_name,
                    "house_number": re_parsed.house_number,
                    "location_info": re_parsed.location_info,
                    "country_code": re_parsed.country_code,
                }
            row["edited"] = True

    # Get stored config from the parsed result
    config = status.get("result", {}).get("config", {})

    job_store.update_status(job_id, "processing_validate")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_validate, job_id, parsed_rows,
        config.get("confidence", 90), config.get("street_confidence", 85),
        config.get("pin_valid", False), config.get("client_ip", "unknown"),
        body.retry_regex_rows,
    )

    return {"ok": True, "data": {"status": "processing_validate"}}
