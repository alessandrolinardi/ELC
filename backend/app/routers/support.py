"""Support ticket endpoint — Crisp message:sent → Zapier → Trello card."""
import asyncio
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import get_settings
from ..limiter import limiter

router = APIRouter()

PAGE_CATEGORIES = {
    "/pickup": "Ritiro",
    "/validator": "Validator",
    "/labels": "Label Sorter",
    "/quotation": "Quotazione",
    "/pod": "POD",
}


class TicketRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    page: str = Field(default="", max_length=100)


@router.post("/support/ticket")
@limiter.limit("10/hour")
async def create_ticket(request: Request, body: TicketRequest):
    """Create a Trello card via Zapier when a user sends their first Crisp message.

    Called by the useCrispTicket frontend hook on the first message:sent event
    per page session. Fires a Zapier catch hook that creates a Trello card.
    """
    settings = get_settings()

    if not settings.support_zapier_url:
        raise HTTPException(status_code=503, detail={
            "ok": False, "error": {"code": "NOT_CONFIGURED", "message": "Supporto non configurato."}
        })

    category = PAGE_CATEGORIES.get(body.page, "Altro")

    payload = {
        "message": body.message.strip(),
        "page": body.page,
        "category": category,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    def _fire():
        resp = requests.post(settings.support_zapier_url, json=payload, timeout=10)
        if resp.status_code not in (200, 201, 202):
            raise RuntimeError(f"HTTP {resp.status_code}")

    try:
        await asyncio.get_running_loop().run_in_executor(None, _fire)
    except RuntimeError:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "WEBHOOK_FAILED", "message": "Invio fallito. Riprova."}
        })
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "WEBHOOK_FAILED", "message": "Errore di connessione. Riprova."}
        })

    return {"ok": True, "data": {"sent": True, "category": category}}
