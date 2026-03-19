# Address Validator Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace regex-based address parsing with Claude AI and switch from Geocoding API to Google Address Validation API, then deploy to Render.

**Architecture:** Claude batch-parses addresses into structured fields (ParsedAddress), Google Address Validation API validates each address and returns per-component verdicts, our code interprets verdicts with custom overrides for Italian edge cases. Regex functions kept as fallback. Deployed on Render with Streamlit Cloud redirect.

**Tech Stack:** Python 3.11, Streamlit, Anthropic SDK (claude-sonnet-4-6), Google Address Validation API, Supabase, openpyxl, Render

**Spec:** `docs/superpowers/specs/2026-03-17-address-validator-redesign.md`

---

## File Structure

### New files to create:
- `src/config.py` — Centralized secrets access (get_secret + get_supabase_client), replaces 3 duplicate implementations
- `src/address_parser.py` — Claude-powered address parsing (AddressParser class, ParsedAddress dataclass, verification, regex fallback)
- `src/address_validator.py` — Google Address Validation API client (ValidationOutcome dataclass, verdict interpretation)
- `data/italian_zip_provinces.json` — Province-to-ZIP prefix mapping extracted from hardcoded dict
- `data/address_parsing_tests.json` — Test harness for Claude parsing edge cases
- `render.yaml` — Render Blueprint for deployment
- `tests/test_address_parser.py` — Tests for Claude parsing + regex fallback
- `tests/test_address_validator.py` — Tests for verdict interpretation + ZIP cross-check
- `tests/test_config.py` — Tests for secrets access

### Files to modify:
- `src/zip_validator.py` — Remove ~800 lines (old APIs, regex parsing, confidence scoring), keep _map_columns, _validate_zip_province, _extract_house_number (fallback), generate_corrected_excel, generate_review_report, PO/phone/COD logic
- `src/address_book.py` — Switch to `get_secret()` from `src/config.py`
- `src/security.py` — Switch to `get_secret()` from `src/config.py`
- `app.py` — Remove `fix_suggested_street`, update ZIP validator page to use new pipeline, switch to `get_secret()` for Google API key lookup
- `requirements.txt` — Add `anthropic` package

### Files unchanged:
- `src/excel_parser.py`, `src/matcher.py`, `src/sorter.py`, `src/pdf_processor.py`, `src/logging_config.py`
- `data/valid_po_numbers.json`
- `tests/test_excel_parser.py`, `tests/test_pdf_processor.py`

---

## Chunk 1: Foundation (config + data models + data files)

### Task 1: Create centralized config module

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import os
import pytest


def test_get_secret_from_env_var():
    """get_secret falls back to env vars when Streamlit secrets unavailable."""
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    from src.config import get_secret
    result = get_secret("supabase", "url")
    assert result == "https://test.supabase.co"
    del os.environ["SUPABASE_URL"]


def test_get_secret_returns_none_for_unknown():
    """get_secret returns None for unmapped keys."""
    from src.config import get_secret
    result = get_secret("unknown", "key")
    assert result is None


def test_get_supabase_client_returns_none_without_config():
    """get_supabase_client returns None when secrets are missing."""
    from src.config import get_supabase_client
    # With no env vars or Streamlit secrets, should return None
    for key in ["SUPABASE_URL", "SUPABASE_KEY"]:
        os.environ.pop(key, None)
    result = get_supabase_client()
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/ELC && python -m pytest tests/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/config.py
"""
Centralized configuration and secrets access.
Works with both Streamlit secrets (local dev) and environment variables (Render).
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SECRET_MAP = {
    ("supabase", "url"): "SUPABASE_URL",
    ("supabase", "key"): "SUPABASE_KEY",
    ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
    ("google", "api_key"): "GOOGLE_ADDRESS_VALIDATION_API_KEY",
    ("zapier", "webhook_url"): "ZAPIER_WEBHOOK_URL",
    ("app", "bypass_pin"): "BYPASS_PIN",
}

_supabase_client = None


def get_secret(section: str, key: str) -> Optional[str]:
    """Get secret from Streamlit secrets or environment variables."""
    # Try Streamlit secrets first (for local dev)
    try:
        import streamlit as st
        return st.secrets[section][key]
    except (KeyError, FileNotFoundError, ImportError, AttributeError):
        pass

    # Fall back to env vars via explicit mapping (Render)
    env_key = SECRET_MAP.get((section, key))
    if env_key:
        return os.environ.get(env_key)
    return None


def get_supabase_client():
    """Get shared Supabase client. Returns None if not configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    try:
        from supabase import create_client
        url = get_secret("supabase", "url")
        key = get_secret("supabase", "key")
        if not url or not key:
            return None
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/ELC && python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add centralized config module for secrets access"
```

---

### Task 2: Create data model classes

**Files:**
- Create: `src/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from src.models import ParsedAddress, ValidationOutcome


def test_parsed_address_street_with_number():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="11/A",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_with_number == "Via Roma 11/A"


def test_parsed_address_street_without_number():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="11/A",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_without_number == "Via Roma"


def test_parsed_address_full_street_with_location():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="1",
        location_info="C.C. Le Grange",
        country_code="IT",
        confidence="high"
    )
    assert addr.full_street == "C.C. Le Grange Via Roma 1"


def test_parsed_address_empty_house_number():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_with_number == "Via Roma"
    assert addr.street_without_number == "Via Roma"


def test_parsed_address_snc():
    addr = ParsedAddress(
        street_prefix="Via",
        street_name="Roma",
        house_number="SNC",
        location_info="",
        country_code="IT",
        confidence="high"
    )
    assert addr.street_with_number == "Via Roma SNC"


def test_validation_outcome_defaults():
    outcome = ValidationOutcome(
        status="valid",
        action="ACCEPT",
        input_zip="20121",
        output_zip="20121",
        zip_confirmed=True,
        zip_corrected=False,
        input_street="Via Roma 10",
        output_street="Via Roma",
        street_confirmed=True,
        street_corrected=False,
        silent_correction=False,
        house_number="10",
        granularity="PREMISE",
        address_complete=True,
        reasons=[],
        formatted_address="Via Roma, 10, 20121 Milano MI, Italia",
        location_info=""
    )
    assert outcome.status == "valid"
    assert outcome.zip_corrected is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /tmp/ELC && python -m pytest tests/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/models.py
"""Data models for the address validation pipeline."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedAddress:
    """Structured address parsed by Claude or regex fallback."""
    street_prefix: str       # "Via", "Piazza", "Corso", etc.
    street_name: str         # "Roma", "4 Novembre", "25 Aprile"
    house_number: str        # "11/A", "SNC", "", "KM 5"
    location_info: str       # "C.C. Le Grange", ""
    country_code: str        # "IT", "DE", "FR"
    confidence: str          # "high", "medium", "low"

    @property
    def street_with_number(self) -> str:
        """Street WITH house number — sent to Address Validation API."""
        parts = [self.street_prefix, self.street_name, self.house_number]
        return " ".join(p for p in parts if p)

    @property
    def street_without_number(self) -> str:
        """Street name only — used for comparison with API results."""
        parts = [self.street_prefix, self.street_name]
        return " ".join(p for p in parts if p)

    @property
    def full_street(self) -> str:
        """Full original street including location info — for display."""
        parts = [self.location_info, self.street_prefix, self.street_name, self.house_number]
        return " ".join(p for p in parts if p)


@dataclass
class ValidationOutcome:
    """Result of validating a single address via Google Address Validation API."""
    # Verdict
    status: str              # "valid", "corrected", "review"
    action: str              # raw API possibleNextAction: ACCEPT/CONFIRM/FIX

    # ZIP
    input_zip: str
    output_zip: str          # from API response
    zip_confirmed: bool
    zip_corrected: bool      # input_zip != output_zip

    # Street
    input_street: str        # original street from Excel
    output_street: str       # corrected street from API
    street_confirmed: bool
    street_corrected: bool   # detected via input-vs-output comparison
    silent_correction: bool  # API changed street but didn't flag it

    # House number
    house_number: str        # from ParsedAddress, never touched

    # Details
    granularity: str         # PREMISE, ROUTE, OTHER
    address_complete: bool
    reasons: list[str] = field(default_factory=list)
    formatted_address: str = ""

    # Location info
    location_info: str = ""


@dataclass
class ParsingMetrics:
    """Observability metrics for Claude address parsing."""
    claude_parsed: int = 0
    claude_failed_verify: int = 0
    regex_fallback: int = 0
    batch_failures: int = 0
    prompt_version: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /tmp/ELC && python -m pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: add ParsedAddress and ValidationOutcome data models"
```

---

### Task 3: Extract Italian ZIP provinces to JSON data file

**Files:**
- Create: `data/italian_zip_provinces.json`
- Modify: `src/zip_validator.py` — replace hardcoded `ITALIAN_PROVINCE_ZIP` dict with JSON file loader

- [ ] **Step 1: Extract the current hardcoded dict to JSON**

Create `data/italian_zip_provinces.json` by converting the `ITALIAN_PROVINCE_ZIP` dict from `src/zip_validator.py:111-160`:

```json
{
  "description": "Italian province codes to ZIP prefix mapping. Province code -> list of valid ZIP prefixes (first 2 digits).",
  "last_updated": "2026-03-17",
  "provinces": {
    "TO": ["10"], "VC": ["13"], "NO": ["28"], "CN": ["12"], "AT": ["14"],
    "AL": ["15"], "BI": ["13"], "VB": ["28"],
    "AO": ["11"],
    "VA": ["21"], "CO": ["22"], "SO": ["23"], "MI": ["20"], "BG": ["24"],
    "BS": ["25"], "PV": ["27"], "CR": ["26"], "MN": ["46"], "LC": ["23"],
    "LO": ["26"], "MB": ["20"],
    "BZ": ["39"], "TN": ["38"],
    "VR": ["37"], "VI": ["36"], "BL": ["32"], "TV": ["31"], "VE": ["30"],
    "PD": ["35"], "RO": ["45"],
    "UD": ["33"], "GO": ["34"], "TS": ["34"], "PN": ["33"],
    "IM": ["18"], "SV": ["17"], "GE": ["16"], "SP": ["19"],
    "PC": ["29"], "PR": ["43"], "RE": ["42"], "MO": ["41"], "BO": ["40"],
    "FE": ["44"], "RA": ["48"], "FC": ["47"], "RN": ["47"],
    "MS": ["54"], "LU": ["55"], "PT": ["51"], "FI": ["50"], "LI": ["57"],
    "PI": ["56"], "AR": ["52"], "SI": ["53"], "GR": ["58"], "PO": ["59"],
    "PG": ["06"], "TR": ["05"],
    "PU": ["61"], "AN": ["60"], "MC": ["62"], "AP": ["63"], "FM": ["63"],
    "VT": ["01"], "RI": ["02"], "RM": ["00"], "LT": ["04"], "FR": ["03"],
    "AQ": ["67"], "TE": ["64"], "PE": ["65"], "CH": ["66"],
    "CB": ["86"], "IS": ["86"],
    "CE": ["81"], "BN": ["82"], "NA": ["80"], "AV": ["83"], "SA": ["84"],
    "FG": ["71"], "BA": ["70"], "TA": ["74"], "BR": ["72"], "LE": ["73"],
    "BT": ["76"],
    "PZ": ["85"], "MT": ["75"],
    "CS": ["87"], "CZ": ["88"], "RC": ["89"], "KR": ["88"], "VV": ["89"],
    "TP": ["91"], "PA": ["90"], "ME": ["98"], "AG": ["92"], "CL": ["93"],
    "EN": ["94"], "CT": ["95"], "RG": ["97"], "SR": ["96"],
    "SS": ["07"], "NU": ["08"], "CA": ["09"], "OR": ["09"], "SU": ["09"]
  }
}
```

- [ ] **Step 2: Update `_validate_zip_province` to load from JSON**

In `src/zip_validator.py`, replace the `ITALIAN_PROVINCE_ZIP` class attribute and modify `_validate_zip_province` to load from file:

```python
# At module level or in __init__, replace the hardcoded dict with:
def _load_province_zip_mapping(self) -> dict:
    """Load province-to-ZIP mapping from JSON file."""
    zip_file = Path(__file__).parent.parent / "data" / "italian_zip_provinces.json"
    try:
        if zip_file.exists():
            with open(zip_file, 'r') as f:
                data = json.load(f)
                return data.get('provinces', {})
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not load ZIP provinces: {e}")
    return {}
```

Remove the hardcoded `ITALIAN_PROVINCE_ZIP` dict (~50 lines) and add `self._province_zip = self._load_province_zip_mapping()` in `__init__`. Update `_validate_zip_province` to use `self._province_zip` instead of `self.ITALIAN_PROVINCE_ZIP`.

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd /tmp/ELC && python -m pytest tests/ -v`
Expected: PASS (existing tests still pass)

- [ ] **Step 4: Commit**

```bash
git add data/italian_zip_provinces.json src/zip_validator.py
git commit -m "refactor: extract Italian ZIP provinces to JSON data file"
```

---

### Task 4: Add anthropic to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add anthropic package**

Add to `requirements.txt`:
```
anthropic>=0.40.0
```

- [ ] **Step 2: Install and verify**

Run: `cd /tmp/ELC && pip install -r requirements.txt`
Expected: anthropic installs successfully

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add anthropic SDK to requirements"
```

---

## Chunk 2: Claude Address Parser

### Task 5: Create address parser with regex fallback

**Files:**
- Create: `src/address_parser.py`
- Test: `tests/test_address_parser.py`

- [ ] **Step 1: Write failing tests for regex fallback (the baseline)**

The regex fallback uses the existing `_extract_house_number` logic to create a `ParsedAddress`. Test this first since it doesn't need Claude API.

```python
# tests/test_address_parser.py
import pytest
from src.address_parser import AddressParser
from src.models import ParsedAddress


class TestRegexFallback:
    """Test regex-based address parsing (Tier 2/3 fallback)."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)  # No Claude, regex only

    def test_simple_address(self):
        result = self.parser.parse_single_regex("Via Roma 10", "Milano", "20121")
        assert result.street_prefix == "Via"
        assert result.street_name == "Roma"
        assert result.house_number == "10"
        assert result.country_code == "IT"

    def test_fractional_house_number(self):
        result = self.parser.parse_single_regex("Via Roma 11/A", "Milano", "20121")
        assert result.house_number == "11/A"

    def test_no_house_number(self):
        result = self.parser.parse_single_regex("Via Roma", "Milano", "20121")
        assert result.house_number == ""
        assert result.street_name == "Roma"

    def test_snc(self):
        result = self.parser.parse_single_regex("Via Roma SNC", "Roma", "00187")
        assert result.house_number == "SNC"

    def test_location_prefix(self):
        result = self.parser.parse_single_regex(
            "C.C. Le Grange Via Roma 1", "Torino", "10100"
        )
        assert result.location_info == "C.C. Le Grange"
        assert result.street_prefix == "Via"
        assert result.street_name == "Roma"
        assert result.house_number == "1"

    def test_country_detection_italian(self):
        result = self.parser.parse_single_regex("Via Roma 10", "Milano", "20121")
        assert result.country_code == "IT"


class TestVerification:
    """Test that parsed addresses reconstruct to original."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)

    def test_verification_passes_for_simple(self):
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        assert self.parser.verify_parsing("Via Roma 10", parsed) is True

    def test_verification_fails_for_wrong_parse(self):
        parsed = ParsedAddress("Via", "Totally Wrong", "10", "", "IT", "high")
        assert self.parser.verify_parsing("Via Roma 10", parsed) is False

    def test_verification_allows_abbreviation_difference(self):
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        # Original had "V." abbreviated, parsed expanded to "Via"
        assert self.parser.verify_parsing("V. Roma 10", parsed) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ELC && python -m pytest tests/test_address_parser.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write implementation — regex parsing + verification**

```python
# src/address_parser.py
"""
Address parser using Claude AI with regex fallback.
Parses raw address strings into structured ParsedAddress fields.
"""
import re
import json
import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import ParsedAddress, ParsingMetrics

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

# Reuse existing patterns from zip_validator.py
STREET_PREFIXES = [
    'via', 'viale', 'piazza', 'piazzale', 'corso', 'largo', 'vicolo',
    'strada', 'contrada', 'borgata', 'traversa', 'salita', 'discesa',
    'lungomare', 'lungotevere', 'lungarno', 'circonvallazione',
    'strada statale', 'strada provinciale', 'strada regionale',
]

LOCATION_PREFIXES = [
    'centro commerciale', 'c.c.', 'cc ', 'c/c',
    'centro direzionale', 'c.d.', 'cd ',
    'centro servizi', 'c.s.',
    'parco commerciale', 'p.c.',
    'galleria commerciale',
    'outlet',
    'retail park',
]

PARSE_TOOL = {
    "name": "parsed_addresses",
    "description": "Parse raw addresses into structured components",
    "input_schema": {
        "type": "object",
        "properties": {
            "addresses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "street_prefix": {"type": "string"},
                        "street_name": {"type": "string"},
                        "house_number": {"type": "string"},
                        "location_info": {"type": "string"},
                        "country_code": {"type": "string"},
                        "confidence": {"enum": ["high", "medium", "low"]}
                    },
                    "required": ["index", "street_prefix", "street_name",
                                 "house_number", "country_code", "confidence"]
                }
            }
        },
        "required": ["addresses"]
    }
}

SYSTEM_PROMPT = """You are an Italian address parser. For each address, extract structured components.

Rules:
- street_prefix: The street type (Via, Piazza, Corso, Viale, Largo, Vicolo, Strada, etc.)
- street_name: The street name WITHOUT the house number
- house_number: The civic number at the END of the address (e.g., "10", "11/A", "SNC", "KM 5") or empty string if none
- location_info: Commercial location prefix (C.C., Centro Commerciale, etc.) or empty string
- country_code: 2-letter ISO code detected from ZIP format, city name, and street language

Critical rules for Italian addresses:
- Numbers that are part of street NAMES (dates, historical references) are NOT house numbers:
  "Via 4 Novembre 7" → street_name="4 Novembre", house_number="7"
  "Via 25 Aprile 3" → street_name="25 Aprile", house_number="3"
  "Via XX Settembre 15" → street_name="XX Settembre", house_number="15"
- "SNC" means "senza numero civico" (no house number) — treat as house_number="SNC"
- "KM 5" at the end is a house_number (kilometer marker)
- Location prefixes come BEFORE the street: "C.C. Le Grange Via Roma 1"
  → location_info="C.C. Le Grange", street_prefix="Via", street_name="Roma", house_number="1"
- Abbreviations: "V."="Via", "P.zza"="Piazza", "C.so"="Corso", "V.le"="Viale", "L.go"="Largo"
  Expand them in street_prefix.
- Country detection: Italian ZIPs are 5 digits (00xxx-99xxx), Italian streets start with Via/Piazza/Corso etc.
  Default to "IT" if uncertain.
"""


class AddressParser:
    """Parse addresses using Claude AI with regex fallback."""

    BATCH_SIZE = 50

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = None
        if api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except Exception as e:
                logger.warning(f"Could not init Anthropic client: {e}")
        self.metrics = ParsingMetrics(prompt_version=PROMPT_VERSION)

    def parse_all(self, addresses: list[dict]) -> list[ParsedAddress]:
        """
        Parse all addresses. Uses Claude if available, regex fallback otherwise.

        Args:
            addresses: List of {"street": str, "city": str, "zip": str}

        Returns:
            List of ParsedAddress, one per input address
        """
        if not self.client:
            logger.info("Claude not available, using regex fallback for all addresses")
            return self._parse_all_regex(addresses)

        results = [None] * len(addresses)

        # Split into batches
        batches = []
        for i in range(0, len(addresses), self.BATCH_SIZE):
            batch = addresses[i:i + self.BATCH_SIZE]
            batches.append((i, batch))

        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for start_idx, batch in batches:
                future = executor.submit(self._parse_batch_claude, batch, start_idx)
                futures[future] = (start_idx, batch)

            for future in as_completed(futures):
                start_idx, batch = futures[future]
                try:
                    batch_results = future.result()
                    for i, parsed in enumerate(batch_results):
                        results[start_idx + i] = parsed
                except Exception as e:
                    logger.error(f"Batch starting at {start_idx} failed: {e}")
                    self.metrics.batch_failures += 1
                    # Regex fallback for failed batch
                    for i, addr in enumerate(batch):
                        results[start_idx + i] = self.parse_single_regex(
                            addr["street"], addr["city"], addr["zip"]
                        )
                        self.metrics.regex_fallback += 1

        # Fill any remaining None slots with regex
        for i, result in enumerate(results):
            if result is None:
                addr = addresses[i]
                results[i] = self.parse_single_regex(
                    addr["street"], addr["city"], addr["zip"]
                )
                self.metrics.regex_fallback += 1

        return results

    def _parse_batch_claude(self, batch: list[dict], start_idx: int) -> list[ParsedAddress]:
        """Parse a batch of addresses using Claude."""
        # Build user message with numbered addresses
        lines = []
        for i, addr in enumerate(batch):
            lines.append(f"{start_idx + i}: street=\"{addr['street']}\", city=\"{addr['city']}\", zip=\"{addr['zip']}\"")
        user_msg = "Parse these addresses:\n" + "\n".join(lines)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[PARSE_TOOL],
            tool_choice={"type": "tool", "name": "parsed_addresses"},
            messages=[{"role": "user", "content": user_msg}]
        )

        # Extract tool use result
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if not tool_block:
            raise ValueError("Claude did not return tool_use response")

        parsed_data = tool_block.input.get("addresses", [])

        # Convert to ParsedAddress objects, verify each, fallback if needed
        results = [None] * len(batch)
        parsed_by_index = {item["index"]: item for item in parsed_data}

        for i, addr in enumerate(batch):
            global_idx = start_idx + i
            item = parsed_by_index.get(global_idx)

            if item:
                parsed = ParsedAddress(
                    street_prefix=item.get("street_prefix", ""),
                    street_name=item.get("street_name", ""),
                    house_number=item.get("house_number", ""),
                    location_info=item.get("location_info", ""),
                    country_code=item.get("country_code", "IT"),
                    confidence=item.get("confidence", "medium"),
                )

                if self.verify_parsing(addr["street"], parsed):
                    results[i] = parsed
                    self.metrics.claude_parsed += 1
                else:
                    logger.warning(f"Verification failed for idx {global_idx}: {addr['street']}")
                    self.metrics.claude_failed_verify += 1
                    results[i] = self.parse_single_regex(
                        addr["street"], addr["city"], addr["zip"]
                    )
                    self.metrics.regex_fallback += 1
            else:
                # Claude didn't return this address
                results[i] = self.parse_single_regex(
                    addr["street"], addr["city"], addr["zip"]
                )
                self.metrics.regex_fallback += 1

        return results

    def _parse_all_regex(self, addresses: list[dict]) -> list[ParsedAddress]:
        """Parse all addresses using regex (no Claude)."""
        results = []
        for addr in addresses:
            parsed = self.parse_single_regex(addr["street"], addr["city"], addr["zip"])
            self.metrics.regex_fallback += 1
            results.append(parsed)
        return results

    def parse_single_regex(self, street: str, city: str, zip_code: str) -> ParsedAddress:
        """Parse a single address using regex patterns."""
        original = street.strip() if street else ""

        # Extract location prefix (C.C., Centro Commerciale, etc.)
        location_info = ""
        clean_street = original
        street_lower = original.lower()

        for prefix in LOCATION_PREFIXES:
            if street_lower.startswith(prefix):
                # Find where the actual street begins
                for sp in STREET_PREFIXES:
                    match = re.search(rf'\b{sp}\.?\s+', street_lower)
                    if match:
                        location_info = original[:match.start()].strip()
                        clean_street = original[match.start():].strip()
                        break
                break

        # Extract street prefix
        street_prefix = ""
        street_name = clean_street
        clean_lower = clean_street.lower()

        for prefix in STREET_PREFIXES:
            if clean_lower.startswith(prefix + ' ') or clean_lower.startswith(prefix + '.'):
                street_prefix = clean_street[:len(prefix)].strip()
                street_name = clean_street[len(prefix):].strip(' .')
                break

        # Extract house number from end
        house_number = ""
        # Check for SNC first
        if street_name.upper().endswith(' SNC') or street_name.upper() == 'SNC':
            snc_idx = street_name.upper().rfind('SNC')
            house_number = "SNC"
            street_name = street_name[:snc_idx].strip()
        else:
            # Match house numbers at the end: "10", "11/A", "123bis", "KM 5"
            km_match = re.search(r'\s+(KM\s+\d+)\s*$', street_name, re.IGNORECASE)
            if km_match:
                house_number = km_match.group(1)
                street_name = street_name[:km_match.start()].strip()
            else:
                num_match = re.search(r'\s+(\d+[/\-]?\w*(?:\s+\d+[/\-]?\w*)*)\s*$', street_name)
                if num_match:
                    house_number = num_match.group(1)
                    street_name = street_name[:num_match.start()].strip()

        # Detect country from ZIP format
        country_code = "IT"  # default
        zip_clean = re.sub(r'[^A-Z0-9]', '', str(zip_code).upper().strip())
        if re.match(r'^[A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2}$', zip_clean):
            country_code = "GB"
        elif re.match(r'^\d{4}[A-Z]{2}$', zip_clean):
            country_code = "NL"

        return ParsedAddress(
            street_prefix=street_prefix,
            street_name=street_name,
            house_number=house_number,
            location_info=location_info,
            country_code=country_code,
            confidence="medium"  # regex is always medium confidence
        )

    def verify_parsing(self, original: str, parsed: ParsedAddress) -> bool:
        """Verify that parsed components reconstruct to the original."""
        if not original:
            return True

        reconstructed = parsed.full_street
        norm_original = self._normalize(original)
        norm_reconstructed = self._normalize(reconstructed)

        original_words = set(norm_original.split())
        reconstructed_words = set(norm_reconstructed.split())

        missing = original_words - reconstructed_words
        return len(missing) <= 1

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ""
        import unicodedata
        s = text.lower().strip()
        s = ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )
        s = re.sub(r'[,.\-\'\"()/]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ELC && python -m pytest tests/test_address_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/address_parser.py tests/test_address_parser.py
git commit -m "feat: add Claude address parser with regex fallback"
```

---

### Task 6: Create address parsing test harness data

**Files:**
- Create: `data/address_parsing_tests.json`

- [ ] **Step 1: Create the test data file**

```json
[
    {"input": "Via Roma 10", "city": "Milano", "zip": "20121",
     "expected": {"street_prefix": "Via", "street_name": "Roma", "house_number": "10"}},
    {"input": "Via Roma 11/A", "city": "Milano", "zip": "20121",
     "expected": {"street_prefix": "Via", "street_name": "Roma", "house_number": "11/A"}},
    {"input": "Via Roma SNC", "city": "Roma", "zip": "00187",
     "expected": {"street_prefix": "Via", "street_name": "Roma", "house_number": "SNC"}},
    {"input": "Via Roma", "city": "Milano", "zip": "20121",
     "expected": {"street_prefix": "Via", "street_name": "Roma", "house_number": ""}},
    {"input": "Via 4 Novembre 7", "city": "Milano", "zip": "20121",
     "expected": {"street_prefix": "Via", "street_name": "4 Novembre", "house_number": "7"}},
    {"input": "Via 25 Aprile 3", "city": "Milano", "zip": "20121",
     "expected": {"street_prefix": "Via", "street_name": "25 Aprile", "house_number": "3"}},
    {"input": "Via XX Settembre 15", "city": "Genova", "zip": "16121",
     "expected": {"street_prefix": "Via", "street_name": "XX Settembre", "house_number": "15"}},
    {"input": "Piazza Duomo 1", "city": "Milano", "zip": "20122",
     "expected": {"street_prefix": "Piazza", "street_name": "Duomo", "house_number": "1"}},
    {"input": "Corso Vittorio Emanuele II 120", "city": "Torino", "zip": "10121",
     "expected": {"street_prefix": "Corso", "street_name": "Vittorio Emanuele II", "house_number": "120"}},
    {"input": "C.C. Le Grange Via Roma 1", "city": "Torino", "zip": "10100",
     "expected": {"street_prefix": "Via", "street_name": "Roma", "house_number": "1", "location_info": "C.C. Le Grange"}},
    {"input": "Centro Commerciale Il Miglio Via Casilina 1", "city": "Roma", "zip": "00100",
     "expected": {"street_prefix": "Via", "street_name": "Casilina", "house_number": "1", "location_info": "Centro Commerciale Il Miglio"}},
    {"input": "Strada Statale 16 KM 5", "city": "Bari", "zip": "70100",
     "expected": {"street_prefix": "Strada Statale", "street_name": "16", "house_number": "KM 5"}},
    {"input": "V. Roma 10", "city": "Milano", "zip": "20121",
     "expected": {"street_prefix": "V.", "street_name": "Roma", "house_number": "10"}},
    {"input": "P.zza Garibaldi 5", "city": "Napoli", "zip": "80100",
     "expected": {"street_prefix": "P.zza", "street_name": "Garibaldi", "house_number": "5"}},
    {"input": "Largo Augusto 3", "city": "Milano", "zip": "20122",
     "expected": {"street_prefix": "Largo", "street_name": "Augusto", "house_number": "3"}},
    {"input": "Vicolo Stretto 2", "city": "Siena", "zip": "53100",
     "expected": {"street_prefix": "Vicolo", "street_name": "Stretto", "house_number": "2"}},
    {"input": "Via del Corso 10", "city": "Roma", "zip": "00187",
     "expected": {"street_prefix": "Via", "street_name": "del Corso", "house_number": "10"}},
    {"input": "Via Roma 21 21", "city": "Torino", "zip": "10100",
     "expected": {"street_prefix": "Via", "street_name": "Roma", "house_number": "21 21"}},
    {"input": "Baker Street 221B", "city": "London", "zip": "NW1 6XE",
     "expected": {"country_code": "GB"}}
]
```

- [ ] **Step 2: Commit**

```bash
git add data/address_parsing_tests.json
git commit -m "feat: add address parsing test harness data"
```

---

## Chunk 3: Google Address Validation API + Verdict Interpretation

### Task 7: Create address validator with verdict interpretation

**Files:**
- Create: `src/address_validator.py`
- Test: `tests/test_address_validator.py`

- [ ] **Step 1: Write failing tests for verdict interpretation**

Use the 12 real API test responses as fixtures:

```python
# tests/test_address_validator.py
import pytest
from src.address_validator import AddressValidator
from src.models import ParsedAddress, ValidationOutcome

# Fixtures based on real API test results
VERDICT_ACCEPT_CLEAN = {
    "possibleNextAction": "ACCEPT",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
}

ADDRESS_ACCEPT_CLEAN = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Via Roma"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "street_number", "componentName": {"text": "10"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20121"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "formattedAddress": "Via Roma, 10, 20121 Milano MI, Italia",
}

# Test 6: Silent correction Via → Piazza
VERDICT_SILENT_CORRECTION = {
    "possibleNextAction": "ACCEPT",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
    "hasInferredComponents": True,
}

ADDRESS_SILENT_CORRECTION = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Piazza Ventiquattro Maggio"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "street_number", "componentName": {"text": "5"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20123"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "administrative_area_level_3", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED", "inferred": True},
    ],
    "formattedAddress": "Piazza Ventiquattro Maggio, 5, 20123 Milano MI, Italia",
}

# Test 7: Fake street → FIX
VERDICT_FAKE_STREET = {
    "possibleNextAction": "FIX",
    "validationGranularity": "OTHER",
    "addressComplete": True,
    "hasUnconfirmedComponents": True,
    "hasInferredComponents": True,
}

ADDRESS_FAKE_STREET = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "via inventata"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
        {"componentType": "street_number", "componentName": {"text": "99"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
        {"componentType": "postal_code", "componentName": {"text": "20121"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "formattedAddress": "via inventata, 99, 20121 Milano MI, Italia",
}

# Missing street_number only → should downgrade FIX to valid
VERDICT_MISSING_HOUSE_NUM = {
    "possibleNextAction": "FIX",
    "validationGranularity": "ROUTE",
    "hasInferredComponents": True,
}

ADDRESS_MISSING_HOUSE_NUM = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Piazza 24 Maggio"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20123"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "missingComponentTypes": ["street_number"],
    "formattedAddress": "Piazza 24 Maggio, 20123 Milano MI, Italia",
}


class TestVerdictInterpretation:

    def setup_method(self):
        self.validator = AddressValidator(api_key="fake")

    def test_accept_clean_is_valid(self):
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_ACCEPT_CLEAN, ADDRESS_ACCEPT_CLEAN, parsed, "20121", "Milano"
        )
        assert outcome.status == "valid"

    def test_silent_correction_detected(self):
        parsed = ParsedAddress("Via", "24 Maggio", "5", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_SILENT_CORRECTION, ADDRESS_SILENT_CORRECTION, parsed, "20123", "Milano"
        )
        assert outcome.status == "corrected"
        assert outcome.silent_correction is True

    def test_fake_street_is_review(self):
        parsed = ParsedAddress("Via", "inventata", "99", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_FAKE_STREET, ADDRESS_FAKE_STREET, parsed, "20121", "Milano"
        )
        assert outcome.status == "review"

    def test_missing_house_number_downgrades_fix(self):
        """FIX triggered only by missing street_number should not be review."""
        parsed = ParsedAddress("Via", "24 Maggio", "", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_MISSING_HOUSE_NUM, ADDRESS_MISSING_HOUSE_NUM, parsed, "20123", "Milano"
        )
        assert outcome.status != "review"

    def test_zip_change_detected(self):
        verdict = {**VERDICT_ACCEPT_CLEAN}
        address = {
            **ADDRESS_ACCEPT_CLEAN,
            "addressComponents": [
                {"componentType": "postal_code", "componentName": {"text": "20123"}, "confirmationLevel": "CONFIRMED", "replaced": True},
                {"componentType": "route", "componentName": {"text": "Via Roma"}, "confirmationLevel": "CONFIRMED"},
                {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
            ]
        }
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            verdict, address, parsed, "20100", "Milano"
        )
        assert outcome.zip_corrected is True
        assert outcome.output_zip == "20123"


class TestZipProvinceCheck:

    def setup_method(self):
        self.validator = AddressValidator(api_key="fake")

    def test_valid_zip_for_province(self):
        valid, msg = self.validator.validate_zip_province("20121", "MI")
        assert valid is True

    def test_invalid_zip_for_province(self):
        valid, msg = self.validator.validate_zip_province("10100", "MI")
        assert valid is False

    def test_unknown_province_passes(self):
        valid, msg = self.validator.validate_zip_province("20121", "XX")
        assert valid is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /tmp/ELC && python -m pytest tests/test_address_validator.py -v`
Expected: FAIL

- [ ] **Step 3: Write implementation**

```python
# src/address_validator.py
"""
Google Address Validation API client and verdict interpretation.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import requests

from .models import ParsedAddress, ValidationOutcome
from .config import get_secret

logger = logging.getLogger(__name__)

IGNORABLE_MISSING = {"street_number", "subpremise", "administrative_area_level_3"}


class AddressValidator:
    """Validates addresses using Google Address Validation API."""

    API_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_secret("google", "api_key")
        self.session = requests.Session()
        self._province_zip = self._load_province_zip_mapping()

    def _load_province_zip_mapping(self) -> dict:
        """Load province-to-ZIP mapping from JSON file."""
        zip_file = Path(__file__).parent.parent / "data" / "italian_zip_provinces.json"
        try:
            if zip_file.exists():
                with open(zip_file, 'r') as f:
                    data = json.load(f)
                    return data.get('provinces', {})
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load ZIP provinces: {e}")
        return {}

    def validate_address(self, parsed: ParsedAddress, city: str,
                          zip_code: str, state: str = "") -> Optional[dict]:
        """Call Google Address Validation API for a single address."""
        if not self.api_key:
            return None

        payload = {
            "address": {
                "regionCode": parsed.country_code,
                "locality": city,
                "postalCode": zip_code,
                "addressLines": [parsed.street_with_number],
                "administrativeArea": state,
            }
        }

        try:
            response = self.session.post(
                self.API_URL,
                params={"key": self.api_key},
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.warning("Google API timeout")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                status = e.response.status_code
                if status == 429:
                    logger.warning("Google API rate limited (RESOURCE_EXHAUSTED)")
                else:
                    logger.warning(f"Google API HTTP error: {status}")
            return None
        except Exception as e:
            logger.error(f"Google API error: {e}")
            return None

    def interpret_verdict(self, verdict: dict, address: dict,
                           parsed: ParsedAddress, input_zip: str,
                           input_city: str) -> ValidationOutcome:
        """Interpret API verdict into ValidationOutcome."""
        action = verdict.get("possibleNextAction", "")
        granularity = verdict.get("validationGranularity", "")
        missing = address.get("missingComponentTypes", [])
        components = address.get("addressComponents", [])
        reasons = []

        # --- Step 1: Override FIX for missing house number ---
        critical_missing = [m for m in missing if m not in IGNORABLE_MISSING]

        if action == "FIX" and not critical_missing:
            has_suspicious = any(
                c.get("confirmationLevel") == "UNCONFIRMED_AND_SUSPICIOUS"
                for c in components
            )
            has_unresolved = bool(address.get("unresolvedTokens"))

            if has_suspicious or has_unresolved or granularity == "OTHER":
                action = "FIX"
            else:
                action = "CONFIRM"

        # --- Step 2: Detect silent corrections ---
        route_comp = next(
            (c for c in components if c["componentType"] == "route"), None
        )

        silent_correction = False
        output_street = ""
        street_confirmed = False
        if route_comp:
            output_street = route_comp["componentName"]["text"]
            street_confirmed = route_comp.get("confirmationLevel") == "CONFIRMED"
            original_street = parsed.street_without_number
            if output_street.lower().strip() != original_street.lower().strip():
                silent_correction = True

        # --- Step 3: Detect locality mismatch ---
        api_admin3 = next(
            (c["componentName"]["text"] for c in components
             if c["componentType"] == "administrative_area_level_3"), None
        )
        locality_mismatch = False
        if api_admin3 and input_city:
            if api_admin3.lower().strip() != input_city.lower().strip():
                locality_mismatch = True
                reasons.append(f"Address matched to {api_admin3}, not {input_city}")

        # --- Step 4: Detect ZIP changes ---
        output_zip = next(
            (c["componentName"]["text"] for c in components
             if c["componentType"] == "postal_code"), ""
        )
        zip_confirmed = any(
            c.get("componentType") == "postal_code"
            and c.get("confirmationLevel") == "CONFIRMED"
            for c in components
        )
        zip_unconfirmed = any(
            c.get("componentType") == "postal_code"
            and c.get("confirmationLevel") == "UNCONFIRMED_BUT_PLAUSIBLE"
            for c in components
        )
        zip_changed = bool(output_zip) and output_zip != input_zip

        if zip_changed:
            reasons.append(f"ZIP changed: {input_zip} → {output_zip}")

        # --- Step 5: Determine status ---
        if action == "FIX":
            status = "review"
        elif locality_mismatch and zip_unconfirmed:
            status = "review"
        elif action == "CONFIRM" or silent_correction or zip_changed:
            if (verdict.get("hasReplacedComponents")
                or verdict.get("hasSpellCorrectedComponents")
                or silent_correction
                or zip_changed):
                status = "corrected"
                if silent_correction:
                    reasons.append(f"Street corrected: {parsed.street_without_number} → {output_street}")
                if verdict.get("hasSpellCorrectedComponents"):
                    reasons.append("Spelling corrected")
                if verdict.get("hasReplacedComponents"):
                    reasons.append("Components replaced")
            elif verdict.get("hasInferredComponents"):
                status = "corrected"
                reasons.append("Missing components inferred")
            else:
                status = "valid"
        else:  # ACCEPT
            if silent_correction or zip_changed:
                status = "corrected"
                if silent_correction:
                    reasons.append(f"Street corrected: {parsed.street_without_number} → {output_street}")
            elif verdict.get("hasSpellCorrectedComponents"):
                status = "corrected"
                reasons.append("Spelling corrected")
            elif locality_mismatch:
                status = "valid"
            else:
                status = "valid"

        # Extract location info from API (point_of_interest)
        api_location = next(
            (c["componentName"]["text"] for c in components
             if c["componentType"] == "point_of_interest"), ""
        )
        location_info = api_location or parsed.location_info

        return ValidationOutcome(
            status=status,
            action=verdict.get("possibleNextAction", ""),
            input_zip=input_zip,
            output_zip=output_zip,
            zip_confirmed=zip_confirmed,
            zip_corrected=zip_changed,
            input_street=parsed.street_with_number,
            output_street=output_street,
            street_confirmed=street_confirmed,
            street_corrected=silent_correction or any(
                c.get("spellCorrected") or c.get("replaced")
                for c in components if c["componentType"] == "route"
            ),
            silent_correction=silent_correction,
            house_number=parsed.house_number,
            granularity=granularity,
            address_complete=verdict.get("addressComplete", False),
            reasons=reasons,
            formatted_address=address.get("formattedAddress", ""),
            location_info=location_info,
        )

    def validate_zip_province(self, zip_code: str, province: str) -> tuple[bool, str]:
        """Validate if ZIP code matches the Italian province."""
        if not province or not zip_code or len(zip_code) != 5:
            return True, ""

        province_upper = province.upper().strip()
        zip_prefix = zip_code[:2]

        if province_upper in self._province_zip:
            valid_prefixes = self._province_zip[province_upper]
            if zip_prefix in valid_prefixes:
                return True, f"ZIP matches province {province_upper}"
            else:
                return False, f"ZIP {zip_code} doesn't match province {province_upper} (expected {valid_prefixes[0]}xxx)"

        return True, ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /tmp/ELC && python -m pytest tests/test_address_validator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/address_validator.py tests/test_address_validator.py
git commit -m "feat: add Google Address Validation API client with verdict interpretation"
```

---

## Chunk 4: Pipeline Integration (rewire zip_validator.py + app.py)

### Task 8: Rewire ZipValidator to use new pipeline

**Files:**
- Modify: `src/zip_validator.py` — major rewrite: remove old methods, integrate AddressParser + AddressValidator
- Modify: `src/address_book.py` — switch to `get_secret()`
- Modify: `src/security.py` — switch to `get_secret()`

This is the largest task. The approach:
1. Update `__init__` to create AddressParser and AddressValidator
2. Rewrite `process_dataframe` to use the new two-step flow
3. Remove old methods (~800 lines)
4. Update `generate_corrected_excel` and `generate_review_report` (remove safeguards, fix ZIP formatting)
5. Update address_book.py and security.py to use get_secret()

- [ ] **Step 1: Update ZipValidator.__init__**

Replace the old init (Photon/Nominatim/Google tracking, city cache, etc.) with:

```python
def __init__(self, confidence_threshold: int = 90, street_confidence_threshold: int = 85,
             google_api_key: Optional[str] = None, anthropic_api_key: Optional[str] = None):
    self.confidence_threshold = confidence_threshold
    self.street_confidence_threshold = street_confidence_threshold
    self.address_parser = AddressParser(api_key=anthropic_api_key)
    self.address_validator = AddressValidator(api_key=google_api_key)
    self._valid_po_numbers = self._load_valid_po_numbers()
    self._supabase_client = get_supabase_client()
    self._cache_hits = 0
    self._cache_misses = 0
```

- [ ] **Step 2: Rewrite process_dataframe**

Replace the for loop body with the new two-step flow from spec Section 8a. Keep the PO validation, phone, COD logic exactly as-is. The key change is replacing `self.validate_address()` with `self.address_validator.validate_address()` + `self.address_validator.interpret_verdict()`.

ZIP padding moves after Claude parsing (only for IT addresses).

Progress callback uses the two-phase approach from spec Section 7c.

- [ ] **Step 3: Delete old methods**

Remove these methods from ZipValidator:
- `_query_photon`, `_query_nominatim`, `_query_address`, `_query_google`
- `_search_streets_in_city`, `_search_similar_streets`
- `_string_similarity`, `_normalize_street`
- `_extract_location_prefix`, `_extract_street_name`, `preprocess_dataframe`
- `_build_street_suggestion`
- `detect_country_code`
- `_clean_zip_code`, `_count_different_digits`, `_is_transposition`, `_is_adjacent_swap`
- `_is_valid_italian_zip_format`, `_looks_like_valid_italian_street`
- `validate_address` (old), `validate_zip`
- `ITALIAN_CAP_RANGES`, `ITALIAN_PROVINCE_ZIP` (hardcoded), `STREET_PREFIXES`, `LOCATION_PREFIXES`
- Photon tracking state (`_photon_available`, `_photon_empty_count`, `_city_cache`)

Keep:
- `_map_columns`, `_extract_house_number` (regex fallback), `_validate_zip_province` (updated to use JSON)
- `_load_valid_po_numbers`, `extract_po_from_string`, `validate_po_number`
- `generate_corrected_excel` (simplified), `generate_review_report` (simplified)
- Cache methods (updated with new columns)
- `DEFAULT_PHONE`

- [ ] **Step 4: Update generate_corrected_excel**

Remove the house number safeguard (lines 2152-2161). The suggested street already has the correct house number from ParsedAddress.

Update ZIP output formatting with the robust `int(float(str(raw))).zfill(5)` + `cell.number_format = '@'` approach.

Add formula injection sanitization.

- [ ] **Step 5: Update generate_review_report**

Remove the house number safeguard (lines 2233-2239).

Add formula injection sanitization.

- [ ] **Step 6: Update address_book.py to use get_secret()**

Replace `_get_supabase_client()` with import from `src.config`:

```python
from .config import get_supabase_client
```

Remove the local `_get_supabase_client()` function. Update all calls.

- [ ] **Step 7: Update security.py to use get_secret()**

Same pattern as address_book.py. Replace local `_get_supabase_client()` with import.

- [ ] **Step 8: Run all tests**

Run: `cd /tmp/ELC && python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/zip_validator.py src/address_book.py src/security.py
git commit -m "refactor: rewire ZipValidator to use Claude + Address Validation API"
```

---

### Task 9: Update app.py

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Remove fix_suggested_street function**

Delete the `fix_suggested_street()` function (lines 50-82).

- [ ] **Step 2: Update zip_validator_page**

- Replace Google API key lookup (lines 783-832) with `get_secret("google", "api_key")`
- Add Anthropic API key: `anthropic_api_key = get_secret("anthropic", "api_key")`
- Pass both keys to ZipValidator constructor
- Remove the `country_filter` DataFrame filtering (Claude handles country detection)
- Update the preview table to use new ValidationOutcome fields
- Replace `fix_suggested_street(r.street, r.suggested_street)` with direct `r.suggested_street`
- Replace `pin_valid = pin_input == "6472"` with `pin_valid = pin_input == get_secret("app", "bypass_pin")`

- [ ] **Step 3: Update imports**

Add:
```python
from src.config import get_secret
```

- [ ] **Step 4: Manual test**

Run: `cd /tmp/ELC && streamlit run app.py`
Verify the Address Validator page loads without errors.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "refactor: update app.py for new validation pipeline"
```

---

## Chunk 5: Deployment (Render + Streamlit redirect)

### Task 10: Create render.yaml and deploy

**Files:**
- Create: `render.yaml`

- [ ] **Step 1: Create render.yaml**

```yaml
services:
  - type: web
    name: elc-tools
    runtime: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: >-
      streamlit run app.py
      --server.port $PORT
      --server.address 0.0.0.0
      --server.headless true
      --server.enableCORS false
      --server.enableXsrfProtection true
    healthCheckPath: /_stcore/health
    autoDeploy: true
    envVars:
      - key: PYTHON_VERSION
        value: "3.11"
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: GOOGLE_ADDRESS_VALIDATION_API_KEY
        sync: false
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_KEY
        sync: false
      - key: ZAPIER_WEBHOOK_URL
        sync: false
      - key: BYPASS_PIN
        sync: false
```

- [ ] **Step 2: Commit and push**

```bash
git add render.yaml
git commit -m "chore: add Render Blueprint for deployment"
git push origin main
```

- [ ] **Step 3: Deploy on Render**

1. Go to Render dashboard → **New** → **Blueprint**
2. Connect `alessandrolinardi/ELC` GitHub repo
3. Render reads `render.yaml` and creates the service
4. Go to **Environment** tab → set all env var values
5. Wait for deploy to complete
6. Verify at `https://elc-tools.onrender.com`

---

### Task 11: Create Streamlit Cloud redirect

**Files:**
- Create: `streamlit-redirect` branch with redirect-only `app.py`

- [ ] **Step 1: Create redirect branch**

```bash
git checkout -b streamlit-redirect
```

- [ ] **Step 2: Replace app.py with redirect**

```python
# app.py (entire file on this branch)
import streamlit as st

RENDER_URL = "https://elc-tools.onrender.com"

st.set_page_config(page_title="ELC Tools - Redirecting...", page_icon="📦")

st.markdown(
    f'<meta http-equiv="refresh" content="3;url={RENDER_URL}">',
    unsafe_allow_html=True
)

st.markdown(f"""
# 📦 ELC Tools si è trasferito!

L'applicazione è stata spostata a un nuovo indirizzo.

Verrai reindirizzato automaticamente tra 3 secondi...

**Nuovo link:** [{RENDER_URL}]({RENDER_URL})

Aggiorna i tuoi segnalibri.
""")
```

- [ ] **Step 3: Commit and push**

```bash
git add app.py
git commit -m "chore: redirect Streamlit Cloud to Render"
git push origin streamlit-redirect
```

- [ ] **Step 4: Update Streamlit Cloud**

Point Streamlit Cloud to deploy from the `streamlit-redirect` branch.

- [ ] **Step 5: Switch back to main**

```bash
git checkout main
```

---

## Task Dependency Summary

```
Task 1 (config) ──┐
Task 2 (models) ──┤
Task 3 (ZIP JSON) ┤──→ Task 5 (parser) ──→ Task 7 (validator) ──→ Task 8 (rewire) ──→ Task 9 (app.py) ──→ Task 10 (render) ──→ Task 11 (redirect)
Task 4 (requirements) ┘
Task 6 (test data) ──────────────────────────────────────────────┘
```

Tasks 1-4 can run in parallel. Task 5 depends on 1-4. Task 7 depends on 5. Tasks 8-11 are sequential.
