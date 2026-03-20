"""Pydantic schemas for Label Sorter endpoints."""
from pydantic import BaseModel
from typing import Optional


class LabelJobResult(BaseModel):
    total_pages: int
    matched: int
    unmatched: int
    match_rate: float
    unmatched_details: list[dict]
    files: dict[str, str]


class LabelJobStatus(BaseModel):
    status: str  # processing | complete | failed
    progress: Optional[dict] = None
    result: Optional[LabelJobResult] = None
    error: Optional[str] = None
