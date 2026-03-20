"""Pydantic schemas for Address Validator endpoints."""
from pydantic import BaseModel
from typing import Optional


class ValidatorResultRow(BaseModel):
    status: str  # verified | corrected | review
    city: str
    street: str
    original_zip: str
    suggested_zip: Optional[str] = None
    suggested_street: Optional[str] = None
    corrections: list[str] = []


class ValidatorJobResult(BaseModel):
    total_rows: int
    valid_count: int
    corrected_count: int
    review_count: int
    skipped_count: int
    street_verified_count: int
    street_corrected_count: int
    po_invalid_count: int
    results: list[ValidatorResultRow]
    files: dict[str, str]


class ValidatorJobStatus(BaseModel):
    status: str
    progress: Optional[dict] = None
    result: Optional[ValidatorJobResult] = None
    error: Optional[str] = None
