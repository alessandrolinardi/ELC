"""Address Book CRUD endpoints."""
import asyncio
from fastapi import APIRouter, HTTPException, Request

from ..limiter import limiter
from ..core.address_book import (
    load_addresses, add_address, update_address, delete_address,
    get_address_by_id, set_default_address
)
from ..schemas.addresses import AddressCreate, AddressUpdate, AddressResponse

router = APIRouter()


@router.get("/addresses")
@limiter.limit("100/hour")
async def list_addresses(request: Request):
    try:
        addresses = await asyncio.to_thread(load_addresses)
    except Exception:
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "LOAD_ERROR", "message": "Errore nel caricamento degli indirizzi"}
        })
    return {"ok": True, "data": [AddressResponse(
        id=a.id, name=a.name, company=a.company, contact_name=a.contact_name,
        street=a.street, zip=a.zip, city=a.city, province=a.province,
        phone=a.phone, reference=a.reference, is_default=a.is_default
    ).model_dump() for a in addresses]}


@router.post("/addresses", status_code=201)
@limiter.limit("100/hour")
async def create_address(request: Request, body: AddressCreate):
    try:
        result = await asyncio.to_thread(lambda: add_address(
            name=body.name, company=body.company, contact_name=body.contact_name,
            street=body.street, zip_code=body.zip_code, city=body.city,
            province=body.province, phone=body.phone, reference=body.reference,
            is_default=body.is_default
        ))
    except Exception as e:
        import logging
        logging.getLogger("addresses").exception("Address create failed: %s", e)
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "SAVE_ERROR", "message": f"Errore: {e}"}
        })
    return {"ok": True, "data": {"id": result}}


@router.put("/addresses/{address_id}")
@limiter.limit("100/hour")
async def update_address_endpoint(request: Request, address_id: str, body: AddressUpdate):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "NO_FIELDS", "message": "Nessun campo da aggiornare"}
        })
    addr = await asyncio.to_thread(get_address_by_id, address_id)
    if addr is None:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Indirizzo non trovato"}
        })
    try:
        await asyncio.to_thread(lambda: update_address(address_id, **updates))
    except Exception:
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "UPDATE_ERROR", "message": "Errore nell'aggiornamento dell'indirizzo"}
        })
    return {"ok": True, "data": {"updated": True}}


@router.delete("/addresses/{address_id}")
@limiter.limit("100/hour")
async def delete_address_endpoint(request: Request, address_id: str):
    addr = await asyncio.to_thread(get_address_by_id, address_id)
    if addr is None:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Indirizzo non trovato"}
        })
    try:
        await asyncio.to_thread(lambda: delete_address(address_id))
    except ValueError as e:
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "LAST_ADDRESS", "message": str(e)}
        })
    except Exception:
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "DELETE_ERROR", "message": "Errore nell'eliminazione dell'indirizzo"}
        })
    return {"ok": True, "data": {"deleted": True}}


@router.put("/addresses/{address_id}/default")
@limiter.limit("100/hour")
async def set_default(request: Request, address_id: str):
    addr = await asyncio.to_thread(get_address_by_id, address_id)
    if addr is None:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Indirizzo non trovato"}
        })
    try:
        await asyncio.to_thread(lambda: set_default_address(address_id))
    except Exception:
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "UPDATE_ERROR", "message": "Errore nell'impostazione dell'indirizzo predefinito"}
        })
    return {"ok": True, "data": {"default": True}}
