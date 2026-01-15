"""
Address Book module for managing pickup addresses.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict


# Path to the addresses JSON file
ADDRESSES_FILE = Path(__file__).parent.parent / "data" / "addresses.json"


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
        """Convert to dictionary."""
        return asdict(self)

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


def _ensure_file_exists() -> None:
    """Ensure the addresses file exists with default structure."""
    if not ADDRESSES_FILE.exists():
        ADDRESSES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ADDRESSES_FILE, "w", encoding="utf-8") as f:
            json.dump({"addresses": []}, f, indent=2)


def load_addresses() -> list[Address]:
    """
    Load all addresses from the JSON file.

    Returns:
        List of Address objects
    """
    _ensure_file_exists()
    try:
        with open(ADDRESSES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [Address.from_dict(addr) for addr in data.get("addresses", [])]
    except (json.JSONDecodeError, IOError):
        return []


def save_addresses(addresses: list[Address]) -> bool:
    """
    Save addresses to the JSON file.

    Args:
        addresses: List of Address objects to save

    Returns:
        True if successful, False otherwise
    """
    _ensure_file_exists()
    try:
        data = {"addresses": [addr.to_dict() for addr in addresses]}
        with open(ADDRESSES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except IOError:
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
        for addr in addresses:
            addr.is_default = False

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

    addresses.append(new_address)

    if save_addresses(addresses):
        return new_id
    return None


def update_address(address_id: str, **kwargs) -> bool:
    """
    Update an existing address.

    Args:
        address_id: The ID of the address to update
        **kwargs: Fields to update (name, company, street, zip, city, province, reference, is_default)

    Returns:
        True if successful, False otherwise
    """
    addresses = load_addresses()

    # Find the address
    target_idx = None
    for i, addr in enumerate(addresses):
        if addr.id == address_id:
            target_idx = i
            break

    if target_idx is None:
        return False

    # Check for duplicate name if name is being changed
    new_name = kwargs.get("name")
    if new_name:
        for i, addr in enumerate(addresses):
            if i != target_idx and addr.name.lower() == new_name.lower():
                return False  # Duplicate name

    # Handle default flag
    if kwargs.get("is_default", False):
        for addr in addresses:
            addr.is_default = False

    # Update fields
    target = addresses[target_idx]
    for key, value in kwargs.items():
        if hasattr(target, key) and key not in ("id", "created_at"):
            setattr(target, key, value)

    target.updated_at = datetime.now().isoformat() + "Z"

    return save_addresses(addresses)


def delete_address(address_id: str) -> bool:
    """
    Delete an address from the address book.

    Args:
        address_id: The ID of the address to delete

    Returns:
        True if successful, False otherwise
    """
    addresses = load_addresses()

    # Don't allow deletion if it's the last address
    if len(addresses) <= 1:
        return False

    # Find and remove the address
    was_default = False
    new_addresses = []
    for addr in addresses:
        if addr.id == address_id:
            was_default = addr.is_default
        else:
            new_addresses.append(addr)

    if len(new_addresses) == len(addresses):
        return False  # Address not found

    # If deleted address was default, make first remaining address default
    if was_default and new_addresses:
        new_addresses[0].is_default = True

    return save_addresses(new_addresses)


def set_default_address(address_id: str) -> bool:
    """
    Set an address as the default.

    Args:
        address_id: The ID of the address to set as default

    Returns:
        True if successful, False otherwise
    """
    addresses = load_addresses()

    found = False
    for addr in addresses:
        if addr.id == address_id:
            addr.is_default = True
            found = True
        else:
            addr.is_default = False

    if not found:
        return False

    return save_addresses(addresses)


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
