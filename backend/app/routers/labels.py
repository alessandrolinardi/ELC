"""Label Sorter endpoints."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..config import get_settings
from ..services.job_store import job_store
from ..core.pdf_processor import PDFProcessor
from ..core.excel_parser import ExcelParser, ExcelParserError
from ..core.matcher import Matcher
from ..core.sorter import Sorter, SortMethod
from ..core.label_report import generate_csv_report
from ..core.security import validate_excel_content, sanitize_filename

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


def _process_labels(job_id: str, pdf_file_bytes_list: list[bytes], excel_bytes: bytes, excel_filename: str, sort_method: str):
    """Run label processing in background thread."""
    settings = get_settings()
    try:
        # Merge PDFs if multiple (done here to avoid blocking event loop)
        import fitz
        if len(pdf_file_bytes_list) == 1:
            pdf_bytes = pdf_file_bytes_list[0]
        else:
            merged = fitz.open()
            for content in pdf_file_bytes_list:
                doc = fitz.open(stream=content, filetype="pdf")
                merged.insert_pdf(doc)
                doc.close()
            pdf_bytes = merged.tobytes()
            merged.close()

        pdf_processor = PDFProcessor()
        excel_parser = ExcelParser()

        # Process PDF
        pdf_data = pdf_processor.process_pdf(pdf_bytes)
        if pdf_data.total_pages > settings.max_pdf_pages:
            job_store.update_status(job_id, "failed", error=f"Too many pages ({pdf_data.total_pages}). Max: {settings.max_pdf_pages}")
            return

        # Parse Excel
        excel_data = excel_parser.parse_excel(excel_bytes, excel_filename)

        # Validate raw Excel content
        import pandas as pd, io
        df = pd.read_excel(io.BytesIO(excel_bytes))
        content_valid, content_error = validate_excel_content(df)
        if not content_valid:
            job_store.update_status(job_id, "failed", error=f"Invalid content: {content_error}")
            return

        # Match
        matcher = Matcher(pdf_data, excel_data)
        match_report = matcher.match_all()

        # Sort
        method = SortMethod.EXCEL_ORDER if sort_method == "excel_order" else SortMethod.ORDER_ID_NUMERIC
        sorter = Sorter(match_report, excel_data)
        sorted_result = sorter.sort(method)

        # Reorder PDF
        reordered_pdf = pdf_processor.reorder_pdf(pdf_bytes, sorted_result.page_order)

        # Generate CSV report
        csv_report = generate_csv_report(match_report)

        # Save files
        job_store.save_file(job_id, "reordered.pdf", reordered_pdf)
        job_store.save_file(job_id, "unmatched.csv", csv_report.encode("utf-8"))

        # Build unmatched details
        unmatched_details = []
        for r in match_report.unmatched:
            unmatched_details.append({
                "page": r.page_number,
                "tracking": r.tracking or "(non estratto)",
                "carrier": r.carrier or "-",
                "reason": r.unmatched_reason.value if r.unmatched_reason else "Sconosciuto",
            })

        # Complete
        job_store.update_status(job_id, "complete", result={
            "total_pages": pdf_data.total_pages,
            "matched": len(match_report.matched),
            "unmatched": len(match_report.unmatched),
            "match_rate": match_report.match_rate,
            "unmatched_details": unmatched_details,
            "files": {
                "pdf": f"/api/v1/jobs/{job_id}/files/reordered.pdf",
                "csv": f"/api/v1/jobs/{job_id}/files/unmatched.csv",
            },
        })
    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))


@router.post("/jobs/labels")
@limiter.limit("20/hour")
async def create_label_job(
    request: Request,
    pdf_files: list[UploadFile] = File(...),
    excel_file: UploadFile = File(...),
    sort_method: str = Form("order_id_numeric"),
):
    settings = get_settings()

    # Validate file sizes
    total_pdf_size = 0
    for f in pdf_files:
        content = await f.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > settings.max_file_size_mb:
            raise HTTPException(status_code=413, detail={
                "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"PDF '{f.filename}' exceeds {settings.max_file_size_mb}MB"}
            })
        total_pdf_size += size_mb
        await f.seek(0)

    if total_pdf_size > settings.max_file_size_mb * 2:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"Total PDF size ({total_pdf_size:.1f}MB) exceeds limit"}
        })

    excel_content = await excel_file.read()
    if len(excel_content) / (1024 * 1024) > settings.max_file_size_mb:
        raise HTTPException(status_code=413, detail={
            "ok": False, "error": {"code": "FILE_TOO_LARGE", "message": f"Excel file exceeds {settings.max_file_size_mb}MB"}
        })

    # Validate sort_method
    if sort_method not in ("excel_order", "order_id_numeric"):
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "INVALID_SORT_METHOD",
            "message": f"sort_method must be 'excel_order' or 'order_id_numeric', got '{sort_method}'"}
        })

    # Read all PDF file bytes (async reads are fine here)
    pdf_file_bytes_list = []
    for f in pdf_files:
        await f.seek(0)
        pdf_file_bytes_list.append(await f.read())

    # Create job and run in background (PDF merge happens in background thread)
    job_id = job_store.create_job("labels")
    excel_filename = sanitize_filename(excel_file.filename or "upload.xlsx")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_labels, job_id, pdf_file_bytes_list, excel_content, excel_filename, sort_method
    )

    return {"ok": True, "data": {"job_id": job_id}}
