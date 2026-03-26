"""Pickup persistence — stores successful pickup requests in Supabase."""
from typing import Optional
from datetime import date

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

        today_str = date.today().isoformat()

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
