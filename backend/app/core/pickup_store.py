"""Pickup persistence — stores successful pickup requests in Supabase."""
from typing import Optional
from datetime import date, datetime, timezone

from .logging_config import get_logger
from .config_compat import get_supabase_client

logger = get_logger(__name__)

TABLE = "elc_pickups"


def save_pickup(pickup_data: dict) -> Optional[str]:
    """Insert a pickup record into Supabase. Returns UUID if successful."""
    try:
        client = get_supabase_client()
        if client is None:
            logger.error("Supabase client is None — cannot save pickup")
            return None

        response = client.table(TABLE).insert(pickup_data).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["id"]
        return None
    except Exception as e:
        logger.exception("Error saving pickup: %s", e)
        return None


def list_pickups(
    upcoming: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List pickups filtered by upcoming or past based on pickup_date."""
    try:
        client = get_supabase_client()
        if client is None:
            return [], 0

        from zoneinfo import ZoneInfo
        today_str = datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()

        query = client.table(TABLE).select("*", count="exact")
        if upcoming:
            query = query.gte("pickup_date", today_str)
        else:
            query = query.lt("pickup_date", today_str)

        query = query.order("pickup_date", desc=True).order("created_at", desc=True)
        query = query.range(offset, offset + limit - 1)

        response = query.execute()
        total = response.count if response.count is not None else len(response.data or [])
        return response.data or [], total
    except Exception as e:
        logger.exception("Error listing pickups: %s", e)
        return [], 0


def get_pickup(pickup_id: str) -> dict | None:
    """Fetch a single pickup record by ID. Returns None if not found.
    Raises PickupStoreError on infrastructure failures.
    """
    client = get_supabase_client()
    if client is None:
        raise PickupStoreError("Supabase client unavailable")
    try:
        response = client.table(TABLE).select("*").eq("id", pickup_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.exception("Error fetching pickup %s: %s", pickup_id, e)
        raise PickupStoreError(f"Failed to fetch pickup: {e}") from e


class PickupStoreError(Exception):
    """Raised when a Supabase operation fails due to infrastructure errors."""
    pass


def cancel_pickup(pickup_id: str, reason: str | None) -> dict | None:
    """Cancel a pickup by updating its status.

    Uses .is_("pickup_status", "cancelled") negative check as a concurrency safety net.
    PostgREST's .neq() excludes NULL values (SQL NULL != 'x' is NULL, not TRUE),
    so we use .not_.eq() which handles NULLs correctly via IS DISTINCT FROM semantics.
    Returns the updated record, or None if already cancelled (race condition).
    Raises PickupStoreError on infrastructure failures.
    """
    client = get_supabase_client()
    if client is None:
        raise PickupStoreError("Supabase client unavailable")
    try:
        response = (
            client.table(TABLE)
            .update({
                "pickup_status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancellation_reason": reason,
            })
            .eq("id", pickup_id)
            .not_.eq("pickup_status", "cancelled")
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.exception("Error cancelling pickup %s: %s", pickup_id, e)
        raise PickupStoreError(f"Failed to cancel pickup: {e}") from e


def update_zapier_status(pickup_id: str, notified: bool) -> None:
    """Persist zapier_notified flag after webhook attempt."""
    try:
        client = get_supabase_client()
        if client is None:
            return
        client.table(TABLE).update({"zapier_notified": notified}).eq("id", pickup_id).execute()
    except Exception as e:
        logger.exception("Error updating zapier status for pickup %s: %s", pickup_id, e)
