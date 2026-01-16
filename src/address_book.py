"""
Address Book module for managing pickup addresses using Supabase.
"""

import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

import streamlit as st
from supabase import create_client, Client


@dataclass
class Address:
    """Address data structure."""
    id: str
    name: str
    company: str
    street: str
    zip: str
    city: str
    province: str
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
            "street": self.street,
            "zip": self.zip,
            "city": self.city,
            "province": self.province,
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
            street=data.get("street", ""),
            zip=data.get("zip", ""),
            city=data.get("city", ""),
            province=data.get("province", ""),
            reference=data.get("reference", ""),
            is_default=data.get("is_default", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", "")
        )


def _get_supabase_client() -> Optional[Client]:
    """Get Supabase client using Streamlit secrets."""
    try:
        if "supabase" not in st.secrets:
            return None

        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]

        return create_client(url, key)
    except Exception:
        return None


def _clear_cache():
    """Clear the addresses cache."""
    if 'addresses_cache' in st.session_state:
        del st.session_state['addresses_cache']


def load_addresses() -> list[Address]:
    """
    Load all addresses from Supabase.

    Returns:
        List of Address objects
    """
    try:
        client = _get_supabase_client()
        if client is None:
            st.error("DEBUG: Supabase client is None - check secrets configuration")
            return []

        response = client.table("addresses").select("*").order("name").execute()

        if not response.data:
            st.warning(f"DEBUG: No data returned from Supabase. Response: {response}")
            return []

        addresses = [Address.from_dict(row) for row in response.data]
        return addresses
    except Exception as e:
        st.error(f"DEBUG: Error loading addresses: {e}")
        return []


def save_addresses(addresses: list[Address]) -> bool:
    """
    Save all addresses to Supabase (used for bulk operations).
    For single operations, use add/update/delete functions directly.

    Args:
        addresses: List of Address objects to save

    Returns:
        True if successful, False otherwise
    """
    try:
        client = _get_supabase_client()
        if client is None:
            return False

        # Delete all existing and insert new (for bulk replacement)
        client.table("addresses").delete().neq("id", "").execute()

        for addr in addresses:
            client.table("addresses").insert(addr.to_dict()).execute()

        _clear_cache()
        return True
    except Exception:
        return False


def get_address_by_id(address_id: str) -> Optional[Address]:
    """
    Get a specific address by ID.

    Args:
        address_id: The address ID to look for

    Returns:
        Address object if found, None otherwise
    """
    addresses = load_addresses()
    for addr in addresses:
        if addr.id == address_id:
            return addr
    return None


def get_default_address() -> Optional[Address]:
    """
    Get the default address.

    Returns:
        The default Address if one exists, None otherwise
    """
    addresses = load_addresses()
    for addr in addresses:
        if addr.is_default:
            return addr
    # If no default, return first address if any exist
    return addresses[0] if addresses else None


def add_address(
    name: str,
    company: str,
    street: str,
    zip_code: str,
    city: str,
    province: str = "",
    reference: str = "",
    is_default: bool = False
) -> Optional[str]:
    """
    Add a new address to the address book.

    Args:
        name: Display name for the address
        company: Company name
        street: Street address
        zip_code: ZIP/postal code
        city: City name
        province: Province code (optional)
        reference: Reference/phone (optional)
        is_default: Whether this should be the default address

    Returns:
        The new address ID if successful, None otherwise
    """
    try:
        client = _get_supabase_client()
        if client is None:
            return None

        addresses = load_addresses()

        # Check for duplicate name
        for addr in addresses:
            if addr.name.lower() == name.lower():
                return None  # Duplicate name

        # Generate new ID
        new_id = f"addr_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat() + "Z"

        # If setting as default, clear other defaults
        if is_default:
            client.table("addresses").update({"is_default": False}).eq("is_default", True).execute()

        # If this is the first address, make it default
        if not addresses:
            is_default = True

        new_address = Address(
            id=new_id,
            name=name,
            company=company,
            street=street,
            zip=zip_code,
            city=city,
            province=province,
            reference=reference,
            is_default=is_default,
            created_at=now,
            updated_at=now
        )

        client.table("addresses").insert(new_address.to_dict()).execute()
        _clear_cache()

        return new_id
    except Exception:
        return None


def update_address(address_id: str, **kwargs) -> bool:
    """
    Update an existing address.

    Args:
        address_id: The ID of the address to update
        **kwargs: Fields to update

    Returns:
        True if successful, False otherwise
    """
    try:
        client = _get_supabase_client()
        if client is None:
            return False

        addresses = load_addresses()

        # Find the address
        target = None
        for addr in addresses:
            if addr.id == address_id:
                target = addr
                break

        if target is None:
            return False

        # Check for duplicate name if name is being changed
        new_name = kwargs.get("name")
        if new_name:
            for addr in addresses:
                if addr.id != address_id and addr.name.lower() == new_name.lower():
                    return False  # Duplicate name

        # Handle default flag
        if kwargs.get("is_default", False):
            client.table("addresses").update({"is_default": False}).eq("is_default", True).execute()

        # Add updated_at
        kwargs["updated_at"] = datetime.now().isoformat() + "Z"

        # Remove fields that shouldn't be updated
        kwargs.pop("id", None)
        kwargs.pop("created_at", None)

        client.table("addresses").update(kwargs).eq("id", address_id).execute()
        _clear_cache()

        return True
    except Exception:
        return False


def delete_address(address_id: str) -> bool:
    """
    Delete an address from the address book.

    Args:
        address_id: The ID of the address to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        client = _get_supabase_client()
        if client is None:
            return False

        addresses = load_addresses()

        # Don't allow deletion if it's the last address
        if len(addresses) <= 1:
            return False

        # Check if it's the default address
        was_default = False
        for addr in addresses:
            if addr.id == address_id:
                was_default = addr.is_default
                break

        # Delete the address
        client.table("addresses").delete().eq("id", address_id).execute()

        # If deleted address was default, make first remaining address default
        if was_default:
            remaining = [a for a in addresses if a.id != address_id]
            if remaining:
                client.table("addresses").update({"is_default": True}).eq("id", remaining[0].id).execute()

        _clear_cache()
        return True
    except Exception:
        return False


def set_default_address(address_id: str) -> bool:
    """
    Set an address as the default.

    Args:
        address_id: The ID of the address to set as default

    Returns:
        True if successful, False otherwise
    """
    try:
        client = _get_supabase_client()
        if client is None:
            return False

        # Clear all defaults
        client.table("addresses").update({"is_default": False}).eq("is_default", True).execute()

        # Set new default
        client.table("addresses").update({"is_default": True}).eq("id", address_id).execute()

        _clear_cache()
        return True
    except Exception:
        return False


def get_address_display_name(address: Address) -> str:
    """
    Get a display string for an address.

    Args:
        address: The Address object

    Returns:
        Formatted display string
    """
    prefix = "⭐ " if address.is_default else "📍 "
    suffix = " (predefinito)" if address.is_default else ""
    return f"{prefix}{address.name}{suffix}"


def get_address_summary(address: Address) -> str:
    """
    Get a summary string for an address.

    Args:
        address: The Address object

    Returns:
        Formatted summary string
    """
    province_str = f" ({address.province})" if address.province else ""
    return f"{address.street}, {address.zip} {address.city}{province_str}"


def is_sheets_configured() -> bool:
    """
    Check if Supabase is properly configured.
    (Kept name for backwards compatibility with app.py)

    Returns:
        True if configured, False otherwise
    """
    return (
        "supabase" in st.secrets and
        "url" in st.secrets.get("supabase", {}) and
        "key" in st.secrets.get("supabase", {})
    )
