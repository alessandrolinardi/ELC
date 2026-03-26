"""Pydantic schemas for Shipments Quotation endpoints."""
from pydantic import BaseModel, field_validator
from typing import Optional


class ShipmentsQuotationForm(BaseModel):
    """Sender address fields submitted alongside the Excel file."""
    from_name: str
    from_company: str = ""
    from_street1: str
    from_city: str
    from_state: str = ""
    from_zip: str
    from_country: str = "IT"
    from_phone: str
    from_email: str = ""

    @field_validator("from_zip")
    @classmethod
    def validate_zip(cls, v):
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v
