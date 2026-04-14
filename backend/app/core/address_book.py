"""
Address Book module for managing pickup addresses using Supabase.
"""

import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from .logging_config import get_logger
from .config_compat import get_supabase_client

logger = get_logger(__name__)

TABLE = "elc_addresses"


@dataclass
class Address:
    """Address data structure."""
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
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for Supabase."""
        return {
            "id": self.id,
            "name": self.name,
            "company": self.company,
            "contact_name": self.contact_name,
            "street": self.street,
            "zip": self.zip,
            "city": self.city,
            "province": self.province,
            "phone": self.phone,
            "reference": self.reference,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Address":
        """Create Address from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            company=data.get("company", ""),
            contact_name=data.get("contact_name", ""),
            street=data.get("street", ""),
            zip=data.get("zip", ""),
            city=data.get("city", ""),
            province=data.get("province", ""),
            phone=data.get("phone", ""),
            reference=data.get("reference", ""),
            is_default=data.get("is_default", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )


def _get_client():
    """Get Supabase client. Raises RuntimeError if unavailable."""
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client unavailable")
    return client


def load_addresses() -> list[Address]:
    """Load all addresses from Supabase. Raises on failure."""
    client = _get_client()
    response = client.table(TABLE).select("*").order("name").execute()
    if not response.data:
        return []
    return [Address.from_dict(row) for row in response.data]


def get_address_by_id(address_id: str) -> Optional[Address]:
    """Get a specific address by ID."""
    for addr in load_addresses():
        if addr.id == address_id:
            return addr
    return None


def get_default_address() -> Optional[Address]:
    """Get the default address, or first address if no default."""
    addresses = load_addresses()
    for addr in addresses:
        if addr.is_default:
            return addr
    return addresses[0] if addresses else None


def add_address(
    name: str,
    company: str,
    street: str,
    zip_code: str,
    city: str,
    province: str = "",
    phone: str = "",
    reference: str = "",
    contact_name: str = "",
    is_default: bool = False
) -> str:
    """Add a new address. Returns the new address ID. Raises on failure."""
    client = _get_client()
    addresses = load_addresses()

    new_id = f"addr_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat() + "Z"

    # If setting as default, clear other defaults
    if is_default:
        client.table(TABLE).update({"is_default": False}).eq("is_default", True).execute()

    # If this is the first address, make it default
    if not addresses:
        is_default = True

    new_address = Address(
        id=new_id,
        name=name,
        company=company,
        contact_name=contact_name,
        street=street,
        zip=zip_code,
        city=city,
        province=province,
        phone=phone,
        reference=reference,
        is_default=is_default,
        created_at=now,
        updated_at=now
    )

    client.table(TABLE).insert(new_address.to_dict()).execute()
    logger.info("Address created: %s (%s)", new_id, name)
    return new_id


def update_address(address_id: str, **kwargs) -> None:
    """Update an existing address. Raises on failure."""
    client = _get_client()

    kwargs["updated_at"] = datetime.now().isoformat() + "Z"
    kwargs.pop("id", None)
    kwargs.pop("created_at", None)

    # Handle default flag
    if kwargs.get("is_default", False):
        client.table(TABLE).update({"is_default": False}).eq("is_default", True).execute()

    client.table(TABLE).update(kwargs).eq("id", address_id).execute()
    logger.info("Address updated: %s", address_id)


def delete_address(address_id: str) -> None:
    """Delete an address. Raises on failure."""
    client = _get_client()
    addresses = load_addresses()

    if len(addresses) <= 1:
        raise ValueError("Non puoi eliminare l'ultimo indirizzo")

    was_default = any(a.id == address_id and a.is_default for a in addresses)

    client.table(TABLE).delete().eq("id", address_id).execute()
    logger.info("Address deleted: %s", address_id)

    # If deleted address was default, make first remaining default
    if was_default:
        remaining = [a for a in addresses if a.id != address_id]
        if remaining:
            client.table(TABLE).update({"is_default": True}).eq("id", remaining[0].id).execute()


def set_default_address(address_id: str) -> None:
    """Set an address as default. Raises on failure."""
    client = _get_client()
    client.table(TABLE).update({"is_default": False}).eq("is_default", True).execute()
    client.table(TABLE).update({"is_default": True}).eq("id", address_id).execute()
    logger.info("Default address set: %s", address_id)
