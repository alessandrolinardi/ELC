"""Order ID management: parsing, normalization, generation, and duplicate detection.

Order ID format: {BRAND}-{PO}-{CAMPAIGN[ VN]}-{SEQ}
Example: SBX-3501494822-GENNAIO TRADE VISIBILITY-1
Versioned: SBX-3501494822-GENNAIO TRADE VISIBILITY V2-1
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

TABLE = "elc_processed_orders"

# PO numbers are exactly 10 digits starting with 350
_PO_PATTERN = re.compile(r"^350\d{7}$")

# Matches: {BRAND}-{PO}-{CAMPAIGN[ VN]}-{SEQ}
# Captures version suffix (e.g. " V2") only at the END of the campaign segment.
_ORDER_ID_RE = re.compile(
    r"^([^-]+)"           # group 1: brand (no hyphens)
    r"-"
    r"(350\d{7})"         # group 2: PO (exactly 350 + 7 digits)
    r"-"
    r"(.+?)"              # group 3: campaign (non-greedy)
    r"(?:\s+V(\d+))?"     # group 4: optional version number (e.g. " V2")
    r"-"
    r"(\d+)"              # group 5: seq
    r"$"
)


@dataclass
class OrderIDComponents:
    """Structured representation of a parsed Order ID."""
    brand: str
    po: str
    campaign: str
    seq: int
    version: Optional[int]  # None = original, 2 = V2, 3 = V3, etc.

    def format(self) -> str:
        """Reconstruct the canonical Order ID string."""
        if self.version is not None and self.version >= 2:
            campaign_str = f"{self.campaign} V{self.version}"
        else:
            campaign_str = self.campaign
        return f"{self.brand}-{self.po}-{campaign_str}-{self.seq}"


# ---------------------------------------------------------------------------
# Task 1: Parsing
# ---------------------------------------------------------------------------

def parse_order_id(raw: str) -> Optional[OrderIDComponents]:
    """Parse a raw Order ID string into its components.

    Format: {BRAND}-{PO}-{CAMPAIGN[ VN]}-{SEQ}
    PO must match 350\\d{7}.

    Returns None if the string cannot be parsed.
    """
    if not raw:
        return None

    m = _ORDER_ID_RE.match(raw.strip())
    if not m:
        return None

    brand, po, campaign, version_str, seq_str = m.groups()

    # Validate PO (redundant given regex, but explicit)
    if not _PO_PATTERN.match(po):
        return None

    version = int(version_str) if version_str is not None else None
    seq = int(seq_str)

    return OrderIDComponents(
        brand=brand,
        po=po,
        campaign=campaign,
        seq=seq,
        version=version,
    )


# ---------------------------------------------------------------------------
# Task 2: Normalization and Generation
# ---------------------------------------------------------------------------

def normalize_order_id(
    raw: str,
    expected_brand: str,
    expected_campaign: str,
) -> Optional[str]:
    """Parse raw, replace brand and campaign with expected values, return formatted.

    Preserves version and seq. Returns None if the raw string is unparseable.
    """
    components = parse_order_id(raw)
    if components is None:
        return None

    components.brand = expected_brand
    components.campaign = expected_campaign
    return components.format()


def generate_order_ids(
    brand: str,
    po_numbers: list[str],
    campaign: str,
    version: Optional[int] = None,
) -> list[str]:
    """Generate canonical Order IDs for a list of rows.

    Each row gets a sequential number starting at 1.
    po_numbers is a parallel list \u2014 one PO per row.

    Returns a list of formatted Order ID strings in the same order.
    """
    result: list[str] = []
    for i, po in enumerate(po_numbers, start=1):
        components = OrderIDComponents(
            brand=brand,
            po=po,
            campaign=campaign,
            seq=i,
            version=version,
        )
        result.append(components.format())
    return result


def bump_version(current_version: Optional[int]) -> int:
    """Return the next version number.

    None  \u2192 2
    2     \u2192 3
    N     \u2192 N+1
    """
    if current_version is None:
        return 2
    return current_version + 1


# ---------------------------------------------------------------------------
# Task 3: Duplicate Detection
# ---------------------------------------------------------------------------

def find_within_file_duplicates(
    order_numbers: list[str],
) -> dict[str, list[int]]:
    """Find duplicate Order Numbers within the provided list.

    Returns a dict mapping each duplicated order number to the list of
    0-based row indices where it appears. Entries that appear only once
    are excluded from the result.
    """
    seen: dict[str, list[int]] = {}
    for idx, number in enumerate(order_numbers):
        if not number:
            continue
        seen.setdefault(number, []).append(idx)

    return {num: indices for num, indices in seen.items() if len(indices) > 1}


def find_cross_file_duplicates(
    order_numbers: list[str],
    supabase_client,
) -> dict[str, dict]:
    """Check order_numbers against the processed_orders Supabase table.

    Returns a dict mapping each matching order number to its stored record
    (processed_at, campaign, job_id, \u2026).
    Returns {} if supabase_client is None, order_numbers is empty, or on error.
    """
    if supabase_client is None or not order_numbers:
        return {}

    # Filter out empty strings to avoid spurious matches
    filtered = [n for n in order_numbers if n]
    if not filtered:
        return {}

    try:
        response = (
            supabase_client
            .table(TABLE)
            .select("*")
            .in_("order_number", filtered)
            .execute()
        )
        rows = response.data or []
        return {row["order_number"]: row for row in rows}
    except Exception as exc:
        logger.warning("find_cross_file_duplicates error: %s", exc)
        return {}


def record_processed_orders(
    order_numbers: list[str],
    job_id: str,
    brand: str,
    campaign: str,
    po_number: str,
    supabase_client,
) -> int:
    """Upsert order_numbers into the processed_orders table with a 90-day TTL.

    Returns the number of records written, or 0 on failure / no client.
    """
    if supabase_client is None or not order_numbers:
        return 0

    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(days=90)

    records = [
        {
            "order_number": num,
            "job_id": job_id,
            "brand": brand,
            "campaign": campaign,
            "po_number": po_number,
            "processed_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        for num in order_numbers
        if num  # skip empty strings
    ]

    if not records:
        return 0

    try:
        response = (
            supabase_client
            .table(TABLE)
            .upsert(records)
            .execute()
        )
        written = len(response.data) if response.data else 0
        return written
    except Exception as exc:
        logger.warning("record_processed_orders error: %s", exc)
        return 0
