"""Pydantic schemas for Pickup Request endpoints."""
from pydantic import BaseModel, field_validator, model_validator
from datetime import date, time
from typing import Optional, List


class PickupRequest(BaseModel):
    carrier: str
    pickup_date: date
    time_start: time
    time_end: time
    company: str
    contact_name: str = ""
    address: str
    zip_code: str
    city: str
    province: str = ""
    phone: str = ""
    reference: str = ""
    num_packages: int
    weight_per_package: float
    length: float
    width: float
    height: float
    use_pallet: bool = False
    num_pallets: int = 0
    pallet_length: float = 0.0
    pallet_width: float = 0.0
    pallet_height: float = 0.0
    notes: str = ""

    @field_validator("carrier")
    @classmethod
    def validate_carrier(cls, v):
        if v not in ("FedEx", "DHL", "UPS"):
            raise ValueError("Carrier must be FedEx, DHL, or UPS")
        return v

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        v = v.strip()
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v

    @model_validator(mode="after")
    def validate_time_window(self):
        if self.time_end <= self.time_start:
            raise ValueError("L'orario di fine deve essere successivo all'orario di inizio")
        return self


class PickupRecord(BaseModel):
    """A stored pickup record from Supabase."""
    id: str
    carrier: str
    pickup_date: str
    time_start: str
    time_end: str
    company: str
    contact_name: str
    address: str
    zip_code: str
    city: str
    province: str
    phone: str
    reference: str
    num_packages: int
    weight_per_package: float
    length: float
    width: float
    height: float
    use_pallet: bool
    num_pallets: int
    pallet_length: float
    pallet_width: float
    pallet_height: float
    notes: str
    pickup_status: Optional[str] = None
    pickup_id: Optional[str] = None
    confirmation_id: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    zapier_notified: Optional[bool] = None
    created_at: str


class CancelPickupRequest(BaseModel):
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def validate_reason_length(cls, v):
        if v is not None and len(v) > 500:
            raise ValueError("Il motivo non può superare 500 caratteri")
        return v


class PickupListResponse(BaseModel):
    """Response for the pickup history endpoint."""
    pickups: List[PickupRecord]
    total: int
    limit: int
    offset: int
