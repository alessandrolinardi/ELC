"""Pickup Request endpoint."""
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..schemas.pickup import PickupRequest
from ..core.pickup import send_pickup_request

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post("/pickup/request")
@limiter.limit("30/hour")
async def create_pickup_request(request: Request, body: PickupRequest):
    success, message = send_pickup_request(
        carrier=body.carrier,
        pickup_date=body.pickup_date,
        time_start=body.time_start,
        time_end=body.time_end,
        company=body.company,
        contact_name=body.contact_name,
        address=body.address,
        zip_code=body.zip_code,
        city=body.city,
        province=body.province,
        reference=body.reference,
        num_packages=body.num_packages,
        weight_per_package=body.weight_per_package,
        length=body.length,
        width=body.width,
        height=body.height,
        use_pallet=body.use_pallet,
        num_pallets=body.num_pallets,
        pallet_length=body.pallet_length,
        pallet_width=body.pallet_width,
        pallet_height=body.pallet_height,
        notes=body.notes,
    )
    if not success:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "ZAPIER_ERROR", "message": message}
        })
    return {"ok": True, "data": {"message": message}}
