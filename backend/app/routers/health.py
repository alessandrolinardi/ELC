"""Health check endpoint."""
from fastapi import APIRouter

from ..config import APP_VERSION

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"ok": True, "data": {"version": APP_VERSION}}
