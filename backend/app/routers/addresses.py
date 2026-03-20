"""Address Book CRUD endpoints."""
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..core.address_book import (
    load_addresses, add_address, update_address, delete_address,
    get_address_by_id, set_default_address
)
from ..schemas.addresses import AddressCreate, AddressUpdate, AddressResponse

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get("/addresses")
@limiter.limit("100/hour")
async def list_addresses(request: Request):
    addresses = load_addresses()
    return {"ok": True, "data": [AddressResponse(
        id=a.id, name=a.name, company=a.company, contact_name=a.contact_name,
        street=a.street, zip=a.zip, city=a.city, province=a.province,
        reference=a.reference, is_default=a.is_default
    ).model_dump() for a in addresses]}


@router.post("/addresses")
@limiter.limit("100/hour")
async def create_address(request: Request, body: AddressCreate):
    result = add_address(
        name=body.name, company=body.company, contact_name=body.contact_name,
        street=body.street, zip_code=body.zip_code, city=body.city,
        province=body.province, reference=body.reference, is_default=body.is_default
    )
    if result is None:
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "DUPLICATE_NAME", "message": "Address name already exists"}
        })
    return {"ok": True, "data": {"id": result}}


@router.put("/addresses/{address_id}")
@limiter.limit("100/hour")
async def update_address_endpoint(request: Request, address_id: str, body: AddressUpdate):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "NO_FIELDS", "message": "No fields to update"}
        })
    success = update_address(address_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Address not found"}
        })
    return {"ok": True, "data": {"updated": True}}


@router.delete("/addresses/{address_id}")
@limiter.limit("100/hour")
async def delete_address_endpoint(request: Request, address_id: str):
    success = delete_address(address_id)
    if not success:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "DELETE_FAILED", "message": "Cannot delete (last address or not found)"}
        })
    return {"ok": True, "data": {"deleted": True}}


@router.put("/addresses/{address_id}/default")
@limiter.limit("100/hour")
async def set_default(request: Request, address_id: str):
    success = set_default_address(address_id)
    if not success:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "NOT_FOUND", "message": "Address not found"}
        })
    return {"ok": True, "data": {"default": True}}
