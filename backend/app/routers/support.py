"""Support request endpoint — fires Zapier webhook for Trello + Discord."""
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..config import get_settings
from ..limiter import limiter

router = APIRouter()

# Page path → Italian category label (auto-detected from referer/body)
PAGE_CATEGORIES = {
    "/pickup": "Ritiro",
    "/validator": "Validator",
    "/labels": "Label Sorter",
    "/quotation": "Quotazione",
    "/pod": "POD",
}


class SupportRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    urgent: bool = False
    page: str = ""  # Current page path, auto-detected by frontend


@router.post("/support")
@limiter.limit("10/hour")
async def submit_support_request(request: Request, body: SupportRequest):
    """Submit a support request to the team via Zapier webhook.

    Zapier routes to: Trello (always) + Discord (if urgent).
    Category is auto-detected from the page the user is on.
    """
    settings = get_settings()

    if not settings.support_webhook_url:
        raise HTTPException(status_code=503, detail={
            "ok": False, "error": {"code": "NOT_CONFIGURED", "message": "Supporto non configurato."}
        })

    category = PAGE_CATEGORIES.get(body.page, "Altro")

    payload = {
        "message": body.message.strip(),
        "category": category,
        "urgent": body.urgent,
        "page": body.page,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = requests.post(
            settings.support_webhook_url,
            json=payload,
            timeout=10,
        )
        if resp.status_code not in (200, 201, 202):
            raise HTTPException(status_code=502, detail={
                "ok": False, "error": {"code": "WEBHOOK_FAILED", "message": "Invio fallito. Riprova."}
            })
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "WEBHOOK_FAILED", "message": "Errore di connessione. Riprova."}
        })

    return {"ok": True, "data": {"sent": True, "category": category, "urgent": body.urgent}}
