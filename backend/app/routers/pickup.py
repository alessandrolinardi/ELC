"""Pickup Request endpoints."""
import asyncio
from fastapi import APIRouter, HTTPException, Query, Request

from ..limiter import limiter
from ..schemas.pickup import PickupRequest
from ..core.pickup import send_pickup_request
from ..core.pickup_store import save_pickup, list_pickups

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
    pickup_status = None
    pickup_id = None
    confirmation_id = None
    if pickup_response:
        pickup_status = pickup_response.get("status")
        pickup_id = str(pickup_response["id"]) if pickup_response.get("id") else None
        confirmation_id = str(pickup_response["confirmation_id"]) if pickup_response.get("confirmation_id") else None
        data["pickup_status"] = pickup_status
        data["pickup_id"] = pickup_id
        data["confirmation_id"] = confirmation_id
        if pickup_response.get("error_message"):
            data["error_detail"] = pickup_response["error_message"]

    # Persist to Supabase (best-effort)
    pickup_record = {
        "carrier": body.carrier,
        "pickup_date": body.pickup_date.isoformat(),
        "time_start": body.time_start.isoformat(),
        "time_end": body.time_end.isoformat(),
        "company": body.company,
        "contact_name": body.contact_name,
        "address": body.address,
        "zip_code": body.zip_code,
        "city": body.city,
        "province": body.province,
        "phone": body.phone,
        "reference": body.reference,
        "num_packages": body.num_packages,
        "weight_per_package": float(body.weight_per_package),
        "length": float(body.length),
        "width": float(body.width),
        "height": float(body.height),
        "use_pallet": body.use_pallet,
        "num_pallets": body.num_pallets,
        "pallet_length": float(body.pallet_length),
        "pallet_width": float(body.pallet_width),
        "pallet_height": float(body.pallet_height),
        "notes": body.notes,
        "pickup_status": pickup_status,
        "pickup_id": pickup_id,
        "confirmation_id": confirmation_id,
    }
    await asyncio.to_thread(save_pickup, pickup_record)

    return {"ok": True, "data": data}


@router.get("/pickup/history")
@limiter.limit("100/hour")
async def get_pickup_history(
    request: Request,
    upcoming: bool = Query(True, description="True = upcoming pickups, False = past/archive"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    pickups, total = await asyncio.to_thread(list_pickups, upcoming=upcoming, limit=limit, offset=offset)
    return {
        "ok": True,
        "data": {
            "pickups": pickups,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }
