"""Pydantic schemas for Freight Request endpoint."""
from pydantic import BaseModel, field_validator
from typing import Optional


class FreightRequestForm(BaseModel):
    """Sender address fields submitted alongside the freight file."""
    from_name: str
    from_company: str
    from_street1: str
    from_city: str
    from_state: str = ""
    from_zip: str
    from_country: str = "IT"
    from_phone: str = ""
    contact_email: str
    contact_phone: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("from_zip")
    @classmethod
    def validate_zip(cls, v):
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes_length(cls, v):
        if v is not None and len(v) > 500:
            raise ValueError("Le note non possono superare 500 caratteri")
        return v
