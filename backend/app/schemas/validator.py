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


# --- Two-phase flow schemas ---

class ParsedRowOriginal(BaseModel):
    street: str
    city: str
    zip: str


class ParsedRowComponents(BaseModel):
    street_prefix: str = ""
    street_name: str = ""
    house_number: str = ""
    location_info: str = ""
    country_code: str = "IT"


class ParsedRow(BaseModel):
    index: int
    original: ParsedRowOriginal
    parsed: ParsedRowOriginal  # reassembled for display
    parsed_components: ParsedRowComponents
    method: str  # "ai" or "regex"
    changed: bool
    changes: list[str] = []
    edited: bool = False


class ParsingSummary(BaseModel):
    total: int
    ai_parsed: int
    regex_fallback: int
    ai_modified: int
    unchanged: int


class ParsedJobResult(BaseModel):
    parsing_summary: ParsingSummary
    rows: list[ParsedRow]


class ConfirmRequest(BaseModel):
    edits: dict[str, dict[str, str]] = {}
    retry_regex_rows: bool = False
