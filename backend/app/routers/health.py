"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"ok": True, "data": {"version": "3.0.0"}}
