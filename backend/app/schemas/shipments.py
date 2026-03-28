"""Pydantic schemas for Shipments endpoints (quotation + ship)."""
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
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


_CARRIER_ID_MAP = {
    CarrierName.MyDHL: 9536,
    CarrierName.UPSv2: 7743,
    CarrierName.FedExv2: 3699,
}


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

    @model_validator(mode="after")
    def validate_carrier_id_matches_name(self):
        expected = _CARRIER_ID_MAP.get(self.carrier_name)
        if expected and self.carrier_id != expected:
            raise ValueError(
                f"carrier_id {self.carrier_id} does not match {self.carrier_name.value} (expected {expected})"
            )
        return self


# --- Batch Ship schemas ---

class ShipBatchRequest(BaseModel):
    """Request body for batch shipment creation via the ship-batch webhook."""
    batch_key: str = Field(..., min_length=1, description="Unique key for idempotency. Same key within 24h returns cached result.")
    carrier_name: CarrierName
    carrier_id: int
    carrier_service: str = Field(..., min_length=1, description="Exact service name from GetRates.")
    from_address: ShipFromAddress
    shipments: list  # Pre-parsed shipment dicts from parse_shipments_excel or raw list
    content_description: str = "Goods"
    total_value: Optional[float] = Field(None, ge=0)
    insurance: float = Field(default=0, ge=0)
    cash_on_delivery: float = Field(default=0, ge=0)
    incoterm: str = Field(default="DAP", pattern=r"^(DAP|DDP|EXW)$")
    transaction_id_prefix: Optional[str] = Field(None, description="Prefix for per-row transaction IDs.")

    @model_validator(mode="after")
    def validate_carrier_id_matches_name(self):
        expected = _CARRIER_ID_MAP.get(self.carrier_name)
        if expected and self.carrier_id != expected:
            raise ValueError(
                f"carrier_id {self.carrier_id} does not match {self.carrier_name.value} (expected {expected})"
            )
        return self

    @field_validator("shipments")
    @classmethod
    def validate_shipments_not_empty(cls, v):
        if not v:
            raise ValueError("At least 1 shipment required")
        if len(v) > 500:
            raise ValueError("Maximum 500 shipments per batch")
        return v


class ShipBatchShipmentResult(BaseModel):
    """Per-shipment result from a batch."""
    row: Optional[int] = None
    id: Optional[str] = None
    status: str
    tracking_number: Optional[str] = None
    label_url: Optional[str] = None
    sp_order_id: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[dict] = None
    transaction_id: Optional[str] = None


class ShipBatchResult(BaseModel):
    """Result shape for a completed batch ship job."""
    batch_id: str
    total: int
    status: str  # "processing" | "completed"
    progress: dict  # {"queued": N, "shipped": N, "failed": N}
    shipments: list[ShipBatchShipmentResult] = []


# --- POD schemas ---

class PodRequest(BaseModel):
    """Request body for single POD lookup."""
    identifier: str = Field(..., min_length=1, max_length=100, description="Tracking number or transaction ID.")


class PodBatchRequest(BaseModel):
    """Request body for bulk POD lookup."""
    identifiers: list[str] = Field(..., min_length=1, max_length=500)

    @field_validator("identifiers")
    @classmethod
    def validate_identifiers(cls, v):
        for i, ident in enumerate(v):
            if not ident or not ident.strip():
                raise ValueError(f"Identifier at index {i} is empty")
            if len(ident) > 100:
                raise ValueError(f"Identifier at index {i} exceeds 100 chars")
        return [x.strip() for x in v]
