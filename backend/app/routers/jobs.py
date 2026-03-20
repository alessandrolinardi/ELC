"""Job status and file download endpoints."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.job_store import job_store

router = APIRouter()


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": {"code": "JOB_NOT_FOUND",
                    "message": "Job expired or server restarted. Please re-run."}}
        )
    return {"ok": True, "data": status}


@router.get("/jobs/{job_id}/files/{filename}")
async def download_file(job_id: str, filename: str):
    path = job_store.get_file_path(job_id, filename)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": {"code": "FILE_NOT_FOUND",
                    "message": "File not found or job expired."}}
        )

    # Determine media type
    media_types = {
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    suffix = path.suffix.lower()
    media_type = media_types.get(suffix, "application/octet-stream")

    try:
        return FileResponse(path, media_type=media_type, filename=filename)
    except (FileNotFoundError, OSError):
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": {"code": "FILE_NOT_FOUND",
                    "message": "File expired during download."}}
        )
