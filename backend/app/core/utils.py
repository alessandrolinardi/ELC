"""Shared utilities for the address validation pipeline."""
import pandas as pd


# Canonical column name aliases — single source of truth
COLUMN_MAPPINGS = {
    'name': ['name', 'nome', 'customer name', 'recipient', 'destinatario'],
    'street': ['street 1', 'street1', 'street', 'address', 'indirizzo', 'via'],
    'street2': ['street 2', 'street2', 'address 2', 'indirizzo 2'],
    'city': ['city', 'città', 'citta'],
    'state': ['state', 'province', 'provincia', 'regione'],
    'zip': ['zip', 'cap', 'postal code', 'postcode', 'zip code', 'postal'],
    'country': ['country', 'paese', 'nazione'],
    'phone': ['phone', 'telefono', 'tel', 'phone number', 'telephone'],
    'cash_on_delivery': ['cash on delivery', 'cod', 'contrassegno', 'cash_on_delivery'],
    'order_number': ['order number', 'order', 'ordine', 'numero ordine', 'po', 'purchase order'],
    'company': ['company', 'azienda', 'società', 'societa'],
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

    Matching strategy: exact match first (case-insensitive), then startsWith fallback.
    """
    col_map = {}
    columns_lower = {c.lower().strip(): c for c in df.columns}

    for field, possible_names in COLUMN_MAPPINGS.items():
        # 1. Exact match (case-insensitive)
        for name in possible_names:
            if name in columns_lower:
                col_map[field] = columns_lower[name]
                break
        else:
            # 2. startsWith fallback
            for name in possible_names:
                for col_lower, col_original in columns_lower.items():
                    if col_lower.startswith(name):
                        col_map[field] = col_original
                        break
                if field in col_map:
                    break

    return col_map


def sanitize_cell(value: str) -> str:
    """Prevent Excel formula injection by escaping dangerous prefixes."""
    if value and value.strip() and value.strip()[0] in ('=', '+', '-', '@', '\t', '\r', '\n'):
        return "'" + value
    return value
