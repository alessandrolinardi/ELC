"""Pydantic schemas for Pickup Request endpoints."""
from pydantic import BaseModel, field_validator, model_validator
from datetime import date, time


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
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v

    @model_validator(mode="after")
    def validate_time_window(self):
        if self.time_end <= self.time_start:
            raise ValueError("L'orario di fine deve essere successivo all'orario di inizio")
        return self
