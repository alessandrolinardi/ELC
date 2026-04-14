"""Pydantic schemas for Address Book CRUD endpoints."""
from pydantic import BaseModel, field_validator
from typing import Optional


class AddressCreate(BaseModel):
    name: str
    company: str
    contact_name: str = ""
    street: str
    zip_code: str
    city: str
    province: str = ""
    phone: str = ""
    reference: str = ""
    is_default: bool = False

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        v = v.strip()
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v


class AddressUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    contact_name: Optional[str] = None
    street: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    phone: Optional[str] = None
    reference: Optional[str] = None

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if v is not None:
            v = v.strip()
            if not v.isdigit() or len(v) != 5:
                raise ValueError("CAP must be 5 digits")
        return v


class AddressResponse(BaseModel):
    id: str
    name: str
    company: str
    contact_name: str
    street: str
    zip: str
    city: str
    province: str
    phone: str
    reference: str
    is_default: bool
