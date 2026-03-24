"""Address Validator endpoints."""
import asyncio
import io
import math
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

import pandas as pd

from ..config import get_settings
from ..services.job_store import job_store
from ..core.zip_validator import ZipValidator
from ..core.address_parser import AddressParser
from ..core.models import ParsedAddress
from ..core.utils import map_columns, sanitize_cell
from ..core.security import (
    check_rate_limit, record_usage, validate_excel_content,
    sanitize_filename, record_failed_attempt
)
from ..schemas.validator import ConfirmRequest, ApplyCorrectionsRequest
from ..core.order_id_manager import (
    parse_order_id, find_within_file_duplicates, find_cross_file_duplicates,
    record_processed_orders,
)
from ..core.config_compat import get_supabase_client as _get_supabase_for_dedup

router = APIRouter()

# Shared regex-only parser for re-parsing user edits (no API key needed)
_regex_parser = AddressParser()

# ZIP-like column names (lowercase) — read as string to preserve leading zeros
_ZIP_COLUMN_NAMES = {'zip', 'cap', 'postal code', 'postcode', 'zip code'}


def _read_excel_preserve_zip(source, **kwargs) -> pd.DataFrame:
    """Read Excel, keeping ZIP columns as strings to preserve leading zeros."""
    # First pass: read header only to find ZIP column
    df_head = pd.read_excel(source, nrows=0, **kwargs)
    str_cols = {
        col: str for col in df_head.columns
        if col.lower().strip() in _ZIP_COLUMN_NAMES
    }
    # Re-read with ZIP columns forced to string
    if hasattr(source, 'seek'):
        source.seek(0)
    return pd.read_excel(source, dtype=str_cols, **kwargs)


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
    brand: str = "",
    campaign: str = "",
):
    """Run AI address parsing in background thread (Phase 1)."""
    settings = get_settings()
    try:
        # Parse Excel (preserve ZIP leading zeros)
        df = _read_excel_preserve_zip(io.BytesIO(excel_bytes))
        df = df.reset_index(drop=True)

        if len(df) == 0:
            job_store.update_status(job_id, "failed", error="Il file non contiene righe di dati")
            return

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

        if 'city' not in col_map or 'zip' not in col_map:
            job_store.update_status(job_id, "failed",
                error=f"Colonne obbligatorie mancanti (City/ZIP). Colonne trovate: {list(df.columns)}")
            return

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

        def _normalize_for_diff(s: str) -> str:
            """Normalize street for meaningful-change detection.
            Strips punctuation and collapses whitespace so 'Via Roma,1' == 'Via Roma 1'."""
            import re as _re
            s = s.strip().lower()
            s = _re.sub(r'[,.\-\'\"()/]', ' ', s)
            s = _re.sub(r'\s+', ' ', s).strip()
            return s

        for i, (parsed_addr, raw) in enumerate(zip(parsed_addresses, raw_addresses)):
            original_street = raw["street"]
            parsed_street = parsed_addr.full_street
            changed = _normalize_for_diff(original_street) != _normalize_for_diff(parsed_street)

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

        # --- Order ID processing ---
        order_col = col_map.get('order_number')
        order_numbers: list[str] = []
        for idx, row in df.iterrows():
            raw_val = row.get(order_col) if order_col else None
            if raw_val is None or (isinstance(raw_val, float) and math.isnan(raw_val)):
                order_numbers.append("")
            else:
                order_numbers.append(str(raw_val).strip())

        order_id_warnings = []
        valid_count = 0
        format_errors = 0
        format_error_indices: list[int] = []
        detected_campaign = ""
        detected_version = None

        detected_po = ""

        for i, raw_oid in enumerate(order_numbers):
            parsed_oid = parse_order_id(raw_oid)
            if parsed_oid is None:
                if raw_oid:
                    format_errors += 1
                    format_error_indices.append(i)
            else:
                valid_count += 1
                if not detected_po and parsed_oid.po:
                    detected_po = parsed_oid.po
                if not detected_campaign and parsed_oid.campaign:
                    detected_campaign = parsed_oid.campaign
                if detected_version is None and parsed_oid.version is not None:
                    detected_version = parsed_oid.version

        if format_error_indices:
            order_id_warnings.append({
                "type": "format_error",
                "message": f"{format_errors} row{'s have' if format_errors != 1 else ' has'} invalid Order ID format",
                "row_indices": format_error_indices,
                "processed_at": None,
            })

        within_dupes = find_within_file_duplicates(order_numbers)
        for oid, indices in within_dupes.items():
            order_id_warnings.append({
                "type": "within_file_duplicate",
                "message": f"Order ID {oid!r} appears {len(indices)} times in this file",
                "row_indices": indices,
                "processed_at": None,
            })

        cross_dupes = find_cross_file_duplicates(order_numbers, _get_supabase_for_dedup())
        for oid, record in cross_dupes.items():
            order_id_warnings.append({
                "type": "cross_file_duplicate",
                "message": f"Order ID {oid!r} was already processed",
                "row_indices": [],
                "processed_at": record.get("processed_at"),
            })

        order_id_summary = {
            "total": len(order_numbers),
            "valid": valid_count,
            "normalized": 0,
            "format_errors": format_errors,
            "within_file_duplicates": len(within_dupes),
            "cross_file_duplicates": len(cross_dupes),
            "warnings": order_id_warnings,
            "detected_campaign": detected_campaign,
            "detected_version": detected_version,
            "detected_po": detected_po,
        }

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
            "order_id_summary": order_id_summary,
            "config": {
                "confidence": confidence,
                "street_confidence": street_confidence,
                "pin_valid": pin_valid,
                "client_ip": client_ip,
                "brand": brand,
                "campaign": campaign,
                "order_numbers": order_numbers,
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
    brand: str = "",
    campaign: str = "",
    order_numbers: list | None = None,
    po_override: str = "",
):
    """Run Google validation in background thread (Phase 2)."""
    settings = get_settings()
    try:
        # Retry regex rows if requested
        has_retry = False
        if retry_regex:
            regex_rows = [r for r in parsed_rows if r["method"] == "regex" and not r.get("edited")]
            if regex_rows:
                has_retry = True
                job_store.update_progress(job_id, 0, 100, "Nuovo tentativo AI...")
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
                job_store.update_progress(job_id, 10, 100, "Re-parsing complete")

        # Load original Excel — reset index to ensure 0-based alignment
        excel_path = job_store.get_file_path(job_id, "original.xlsx")
        if not excel_path:
            job_store.update_status(job_id, "failed", error="Original Excel file not found")
            return
        df = _read_excel_preserve_zip(excel_path).reset_index(drop=True)

        # Apply confirmed/edited values to the DataFrame so Google API
        # receives the AI-fixed + user-edited data, not the raw originals.
        col_map = map_columns(df)
        street_col = col_map.get("street")
        city_col = col_map.get("city")
        zip_col = col_map.get("zip")

        for row in parsed_rows:
            idx = row["index"]
            if idx < len(df):
                parsed_data = row["parsed"]
                if street_col and "street" in parsed_data:
                    df.at[idx, street_col] = parsed_data["street"]
                if city_col and "city" in parsed_data:
                    df.at[idx, city_col] = parsed_data["city"]
                if zip_col and "zip" in parsed_data:
                    # Convert to match column dtype (ZIP may be int64 in Excel)
                    zip_val = parsed_data["zip"]
                    if df[zip_col].dtype in ('int64', 'float64'):
                        try:
                            zip_val = int(float(zip_val))
                        except (ValueError, TypeError):
                            pass
                    df.at[idx, zip_col] = zip_val

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
                parse_method=row.get("method", "unknown"),
            ))

        # Run Google validation (Phase 2)
        validator = ZipValidator(
            confidence_threshold=confidence,
            street_confidence_threshold=street_confidence,
            google_api_key=settings.google_address_validation_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        # Scale validation progress: 10-100% if retry happened, 0-100% otherwise
        progress_base = 10 if has_retry else 0
        progress_range = 100 - progress_base

        def progress_callback(current, total, message):
            if total > 0:
                scaled = progress_base + int(current / total * progress_range)
            else:
                scaled = progress_base
            job_store.update_progress(job_id, scaled, 100, message)

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
        for i, r in enumerate(report.results):
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

            # Carry forward parse method from Phase 1
            parse_method = "unknown"
            if i < len(parsed_rows):
                parse_method = parsed_rows[i].get("method", "unknown")

            row_results.append({
                "status": status,
                "city": r.city or "",
                "street": r.street or "",
                "original_zip": r.original_zip or "",
                "suggested_zip": r.suggested_zip,
                "suggested_street": r.suggested_street,
                "corrections": corrections,
                "parse_method": parse_method,
            })

        # Record processed orders BEFORE marking complete (so dedup data
        # is persisted even if the status update were to fail, and a
        # "complete" job always has its orders recorded).
        _order_numbers = order_numbers or []
        if _order_numbers:
            # Use user-provided PO override, or extract from first parseable Order ID
            _po = po_override
            if not _po:
                for _on in _order_numbers:
                    _parsed = parse_order_id(_on)
                    if _parsed:
                        _po = _parsed.po
                        break
            record_processed_orders(
                order_numbers=_order_numbers,
                job_id=job_id,
                brand=brand,
                campaign=campaign,
                po_number=_po or "",
                supabase_client=_get_supabase_for_dedup(),
            )

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
    brand: str = Form(""),
    campaign: str = Form(""),
):
    settings = get_settings()

    # File size check
    content = await excel_file.read()
    if len(content) / (1024 * 1024) > settings.max_file_size_mb:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"File exceeds {settings.max_file_size_mb}MB"}
        })

    # Quick-check: reject empty files before creating a job
    try:
        quick_df = _read_excel_preserve_zip(io.BytesIO(content))
        if len(quick_df) == 0:
            raise HTTPException(status_code=400, detail={
                "ok": False, "error": {"code": "EMPTY_FILE", "message": "Il file non contiene righe di dati"}
            })
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "INVALID_FILE", "message": "Unable to read Excel file"}
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
        brand, campaign,
    )

    return {"ok": True, "data": {"job_id": job_id}}


@router.post("/jobs/{job_id}/confirm")
async def confirm_validation(job_id: str, body: ConfirmRequest):
    # Atomic state transition — prevents double-confirm
    if not job_store.transition_status(job_id, "parsed", "processing_validate"):
        status = job_store.get_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail={
                "ok": False, "error": {"code": "JOB_NOT_FOUND", "message": "Job not found or expired"}
            })
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "INVALID_STATE",
            "message": f"Job is in state '{status['status']}', expected 'parsed'"}
        })

    # Now safe — status is "processing_validate", no other confirm can pass
    status = job_store.get_status(job_id)  # deep copy, safe to mutate
    parsed_rows = status["result"]["rows"]

    # Apply user edits
    for idx_str, field_edits in body.edits.items():
        idx = int(idx_str)
        row = next((r for r in parsed_rows if r["index"] == idx), None)
        if row:
            row["parsed"].update(field_edits)
            if "street" in field_edits or "city" in field_edits or "zip" in field_edits:
                existing_country = row.get("parsed_components", {}).get("country_code", "IT")
                re_parsed = _regex_parser.parse_single_regex(
                    row["parsed"].get("street", ""),
                    row["parsed"].get("city", ""),
                    row["parsed"].get("zip", ""),
                    default_country=existing_country,
                )
                row["parsed_components"] = {
                    "street_prefix": re_parsed.street_prefix,
                    "street_name": re_parsed.street_name,
                    "house_number": re_parsed.house_number,
                    "location_info": re_parsed.location_info,
                    "country_code": re_parsed.country_code,
                }
                row["method"] = "user_edit"
            row["edited"] = True

    # Get stored config from the parsed result
    config = status.get("result", {}).get("config", {})
    campaign = body.campaign_override or config.get("campaign", "")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_validate, job_id, parsed_rows,
        config.get("confidence", 90), config.get("street_confidence", 85),
        config.get("pin_valid", False), config.get("client_ip", "unknown"),
        body.retry_regex_rows,
        config.get("brand", ""), campaign,
        config.get("order_numbers", []),
        body.po_override or "",
    )

    return {"ok": True, "data": {"status": "processing_validate"}}


@router.post("/jobs/{job_id}/apply-corrections")
async def apply_corrections(job_id: str, body: ApplyCorrectionsRequest):
    """Apply user corrections to the corrected Excel file.

    Called after Phase 2 when user has reviewed results and made edits
    to 'Da verificare' rows before downloading.
    """
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "JOB_NOT_FOUND", "message": "Job not found or expired"}
        })
    if status["status"] != "complete":
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "INVALID_STATE",
            "message": f"Job is in state '{status['status']}', expected 'complete'"}
        })

    if not body.corrections:
        return {"ok": True, "data": {"applied": 0}}

    # Load the corrected Excel
    corrected_path = job_store.get_file_path(job_id, "corrected.xlsx")
    if not corrected_path:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "FILE_NOT_FOUND", "message": "Corrected file not found"}
        })

    df = _read_excel_preserve_zip(corrected_path)

    col_map = map_columns(df)
    street_col = col_map.get("street")
    city_col = col_map.get("city")
    zip_col = col_map.get("zip")

    applied = 0
    for idx_str, fields in body.corrections.items():
        idx = int(idx_str)
        if idx < 0 or idx >= len(df):
            continue
        if "street" in fields and street_col:
            df.at[idx, street_col] = sanitize_cell(fields["street"])
        if "city" in fields and city_col:
            df.at[idx, city_col] = sanitize_cell(fields["city"])
        if "zip" in fields and zip_col:
            zip_val = fields["zip"]
            if df[zip_col].dtype in ('int64', 'float64'):
                try:
                    zip_val = int(float(zip_val))
                except (ValueError, TypeError):
                    pass
            df.at[idx, zip_col] = zip_val
        applied += 1

    # Write back
    output = io.BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    job_store.save_file(job_id, "corrected.xlsx", output.getvalue())

    return {"ok": True, "data": {"applied": applied}}
