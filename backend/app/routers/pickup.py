"""Pickup Request endpoint."""
import asyncio
from fastapi import APIRouter, HTTPException, Request

from ..limiter import limiter
from ..schemas.pickup import PickupRequest
from ..core.pickup import send_pickup_request

router = APIRouter()


@router.post("/pickup/request")
@limiter.limit("30/hour")
async def create_pickup_request(request: Request, body: PickupRequest):
    success, message, pickup_response = await asyncio.to_thread(send_pickup_request,
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
        phone=body.phone,
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
            "ok": False, "error": {"code": "WEBHOOK_ERROR", "message": message}
        })

    data = {"message": message}
    if pickup_response:
        data["pickup_status"] = pickup_response.get("status")
        data["pickup_id"] = str(pickup_response["id"]) if pickup_response.get("id") else None
        data["confirmation_id"] = str(pickup_response["confirmation_id"]) if pickup_response.get("confirmation_id") else None
        if pickup_response.get("error_message"):
            data["error_detail"] = pickup_response["error_message"]
    return {"ok": True, "data": data}
