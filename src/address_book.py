"""
Address Book module for managing pickup addresses using Google Sheets.
"""

import uuid
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials


# Google Sheets configuration
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Column headers for the sheet
COLUMNS = ["id", "name", "company", "street", "zip", "city", "province", "reference", "is_default", "created_at", "updated_at"]


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

    def to_row(self) -> list:
        """Convert to a row for Google Sheets."""
        return [
            self.id,
            self.name,
            self.company,
            self.street,
            self.zip,
            self.city,
            self.province,
            self.reference,
            "TRUE" if self.is_default else "FALSE",
            self.created_at,
            self.updated_at
        ]

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

    @classmethod
    def from_row(cls, row: list) -> "Address":
        """Create Address from a Google Sheets row."""
        # Ensure row has enough elements
        while len(row) < len(COLUMNS):
            row.append("")

        return cls(
            id=str(row[0]) if row[0] else "",
            name=str(row[1]) if row[1] else "",
            company=str(row[2]) if row[2] else "",
            street=str(row[3]) if row[3] else "",
            zip=str(row[4]) if row[4] else "",
            city=str(row[5]) if row[5] else "",
            province=str(row[6]) if row[6] else "",
            reference=str(row[7]) if row[7] else "",
            is_default=str(row[8]).upper() == "TRUE" if row[8] else False,
            created_at=str(row[9]) if row[9] else "",
            updated_at=str(row[10]) if row[10] else ""
        )


def _get_gspread_client():
    """Get authenticated gspread client using Streamlit secrets."""
    try:
        # Get credentials from Streamlit secrets
        if "gcp_service_account" not in st.secrets:
            return None

        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception:
        return None


def _get_worksheet():
    """Get the addresses worksheet."""
    try:
        client = _get_gspread_client()
        if client is None:
            return None

        # Get spreadsheet ID from secrets
        if "google_sheets" not in st.secrets or "spreadsheet_id" not in st.secrets["google_sheets"]:
            return None

        spreadsheet_id = st.secrets["google_sheets"]["spreadsheet_id"]
        spreadsheet = client.open_by_key(spreadsheet_id)

        # Get or create the "Addresses" worksheet
        try:
            worksheet = spreadsheet.worksheet("Addresses")
        except gspread.WorksheetNotFound:
            # Create the worksheet with headers
            worksheet = spreadsheet.add_worksheet(title="Addresses", rows=100, cols=len(COLUMNS))
            worksheet.append_row(COLUMNS)

        return worksheet
    except Exception:
        return None


def _clear_cache():
    """Clear the addresses cache."""
    if 'addresses_cache' in st.session_state:
        del st.session_state['addresses_cache']


def load_addresses() -> list[Address]:
    """
    Load all addresses from Google Sheets.

    Returns:
        List of Address objects
    """
    # Check cache first
    if 'addresses_cache' in st.session_state:
        return st.session_state['addresses_cache']

    try:
        worksheet = _get_worksheet()
        if worksheet is None:
            return []

        # Get all records (skip header row)
        all_values = worksheet.get_all_values()
        if len(all_values) <= 1:  # Only header or empty
            return []

        addresses = []
        for row in all_values[1:]:  # Skip header
            if row and row[0]:  # Has an ID
                addresses.append(Address.from_row(row))

        # Cache the result
        st.session_state['addresses_cache'] = addresses
        return addresses
    except Exception:
        return []


def save_addresses(addresses: list[Address]) -> bool:
    """
    Save all addresses to Google Sheets (full replacement).

    Args:
        addresses: List of Address objects to save

    Returns:
        True if successful, False otherwise
    """
    try:
        worksheet = _get_worksheet()
        if worksheet is None:
            return False

        # Clear existing data (keep header)
        worksheet.clear()

        # Write header
        worksheet.append_row(COLUMNS)

        # Write all addresses
        for addr in addresses:
            worksheet.append_row(addr.to_row())

        # Clear cache
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


def is_sheets_configured() -> bool:
    """
    Check if Google Sheets is properly configured.

    Returns:
        True if configured, False otherwise
    """
    return (
        "gcp_service_account" in st.secrets and
        "google_sheets" in st.secrets and
        "spreadsheet_id" in st.secrets.get("google_sheets", {})
    )
