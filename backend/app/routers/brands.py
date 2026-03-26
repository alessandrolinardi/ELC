"""Brands CRUD \u2014 manages the short list of brand names for Order IDs."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..core.config_compat import get_supabase_client

router = APIRouter()

TABLE = "elc_brands"

def _get_supabase():
    return get_supabase_client()

class CreateBrandRequest(BaseModel):
    name: str

@router.get("/brands")
async def list_brands():
    client = _get_supabase()
    if not client:
        return {"ok": True, "data": []}
    try:
        response = client.table(TABLE).select("*").order("name").execute()
        return {"ok": True, "data": response.data or []}
    except Exception:
        return {"ok": True, "data": []}

@router.post("/brands")
async def create_brand(body: CreateBrandRequest):
    name = body.name.strip().upper()
    if not name:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "EMPTY_NAME", "message": "Brand name cannot be empty"}
        })
    client = _get_supabase()
    if not client:
        raise HTTPException(status_code=503, detail={
            "ok": False, "error": {"code": "DB_UNAVAILABLE", "message": "Database unavailable"}
        })
    try:
        client.table(TABLE).upsert({"name": name}, on_conflict="name").execute()
        return {"ok": True, "data": {"name": name}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "DB_ERROR", "message": str(e)}
        })
