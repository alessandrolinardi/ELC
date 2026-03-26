"""Shared utilities for the address validation pipeline."""
import pandas as pd


# Canonical column name aliases — single source of truth
COLUMN_MAPPINGS = {
    'name': ['name', 'nome', 'customer name', 'recipient', 'destinatario'],
    'street': ['street 1', 'street1', 'street', 'address', 'indirizzo', 'via'],
    'street2': ['street 2', 'street2', 'address 2', 'indirizzo 2'],
    'city': ['city', 'citt\u00e0', 'citta'],
    'state': ['state', 'province', 'provincia', 'regione'],
    'zip': ['zip', 'cap', 'postal code', 'postcode', 'zip code', 'postal'],
    'country': ['country', 'paese', 'nazione'],
    'phone': ['phone', 'telefono', 'tel', 'phone number', 'telephone'],
    'cash_on_delivery': ['cash on delivery', 'cod', 'contrassegno', 'cash_on_delivery'],
    'order_number': ['order number', 'order', 'ordine', 'numero ordine', 'po', 'purchase order'],
    'company': ['company', 'azienda', 'societ\u00e0', 'societa'],
    'email': ['email', 'e-mail', 'mail'],
    'weight': ['weight', 'peso', 'kg'],
    'length': ['length', 'lunghezza'],
    'width': ['width', 'larghezza'],
    'height': ['height', 'altezza'],
    'parcels': ['parcels', 'parcel count', 'colli', 'packages', 'number of parcels'],
    'content_description': ['content description', 'contentdescription', 'contents', 'descrizione', 'contenuto', 'description'],
}


def map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map DataFrame columns to canonical field names.

    Returns a dict like {"street": "Street 1", "city": "City", "zip": "Zip"}
    mapping canonical field names to actual column names found in the DataFrame.

    Two-pass matching: exact matches first (all fields), then startsWith
    only for unresolved fields on unclaimed columns.
    """
    col_map = {}
    columns_lower = {c.lower().strip(): c for c in df.columns}
    claimed: set[str] = set()  # lowercased column names already matched

    # Pass 1: exact match (case-insensitive) for all fields
    for field, possible_names in COLUMN_MAPPINGS.items():
        for name in possible_names:
            if name in columns_lower and name not in claimed:
                col_map[field] = columns_lower[name]
                claimed.add(name)
                break

    # Pass 2: startsWith fallback for unresolved fields, skip claimed columns
    for field, possible_names in COLUMN_MAPPINGS.items():
        if field in col_map:
            continue
        for name in possible_names:
            alias = name.lower()
            for col_lower, col_original in columns_lower.items():
                if col_lower not in claimed and col_lower.startswith(alias):
                    col_map[field] = col_original
                    claimed.add(col_lower)
                    break
            if field in col_map:
                break

    return col_map


def sanitize_cell(value: str) -> str:
    """Prevent Excel formula injection by escaping dangerous prefixes."""
    if value and value.strip() and value.strip()[0] in ('=', '+', '-', '@', '\t', '\r', '\n'):
        return "'" + value
    return value
