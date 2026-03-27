"""Pydantic schemas for Shipments endpoints (quotation + ship)."""
from enum import Enum
from pydantic import BaseModel, Field, field_validator
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


# --- Ship endpoint schemas ---

class CarrierName(str, Enum):
    MyDHL = "MyDHL"
    UPSv2 = "UPSv2"
    FedExv2 = "FedExv2"


class ShipAddress(BaseModel):
    name: str = Field(..., min_length=1)
    company: str = ""
    street1: str = Field(..., min_length=1)
    street2: str = ""
    city: str = Field(..., min_length=1)
    state: str = ""
    zip: str = Field(..., min_length=1)
    country: str = Field(..., min_length=2, max_length=2)
    phone: str = ""
    email: str = ""

    @field_validator("country")
    @classmethod
    def upper_country(cls, v):
        return v.upper()


class ShipFromAddress(ShipAddress):
    """Sender address — phone is required."""
    phone: str = Field(..., min_length=1)


class ShipParcel(BaseModel):
    length: float = Field(..., gt=0)
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    weight: float = Field(..., gt=0)


class ShipRequest(BaseModel):
    """Request body for creating a shipment via the Ship webhook."""
    carrier_name: CarrierName
    carrier_id: int
    carrier_service: str = Field(..., min_length=1, description="Exact service name from GetRates. NOT 'All Services'.")
    from_address: ShipFromAddress
    to_address: ShipAddress
    parcels: list[ShipParcel] = Field(..., min_length=1)
    content_description: str = "Goods"
    total_value: Optional[float] = Field(None, ge=0)
    insurance: float = Field(default=0, ge=0)
    cash_on_delivery: float = Field(default=0, ge=0)
    incoterm: str = Field(default="DAP", pattern=r"^(DAP|DDP|EXW)$")
    transaction_id: Optional[str] = None


class ShipResult(BaseModel):
    """Result shape for a completed ship job."""
    status: str  # "shipped" or "failed"
    sp_order_id: Optional[str] = None
    tracking_number: Optional[str] = None
    tracking_carrier: Optional[str] = None
    label_url: Optional[str] = None
    carrier_name: str
    carrier_service: str
    error_message: Optional[str] = None
