"""Label Sorter endpoints."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from ..config import get_settings
from ..services.job_store import job_store
from ..core.pdf_processor import PDFProcessor
from ..core.excel_parser import ExcelParser, ExcelParserError
from ..core.matcher import Matcher
from ..core.sorter import Sorter, SortMethod
from ..core.label_report import generate_csv_report
from ..core.security import validate_excel_content, sanitize_filename

router = APIRouter()


def _process_labels(job_id: str, pdf_bytes: bytes, excel_bytes: bytes, excel_filename: str, sort_method: str):
    """Run label processing in background thread."""
    settings = get_settings()
    try:
        pdf_processor = PDFProcessor()
        excel_parser = ExcelParser()

        # Process PDF
        pdf_data = pdf_processor.process_pdf(pdf_bytes)
        if pdf_data.total_pages > settings.max_pdf_pages:
            job_store.update_status(job_id, "failed", error=f"Too many pages ({pdf_data.total_pages}). Max: {settings.max_pdf_pages}")
            return

        # Parse Excel
        excel_data = excel_parser.parse_excel(excel_bytes, excel_filename)

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
async def create_label_job(
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

    # Merge PDFs if multiple
    import fitz
    if len(pdf_files) == 1:
        await pdf_files[0].seek(0)
        pdf_bytes = await pdf_files[0].read()
    else:
        merged = fitz.open()
        for f in pdf_files:
            await f.seek(0)
            content = await f.read()
            doc = fitz.open(stream=content, filetype="pdf")
            merged.insert_pdf(doc)
            doc.close()
        pdf_bytes = merged.tobytes()
        merged.close()

    # Create job and run in background
    job_id = job_store.create_job("labels")
    excel_filename = sanitize_filename(excel_file.filename or "upload.xlsx")
    asyncio.get_event_loop().run_in_executor(
        None, _process_labels, job_id, pdf_bytes, excel_content, excel_filename, sort_method
    )

    return {"ok": True, "data": {"job_id": job_id}}
