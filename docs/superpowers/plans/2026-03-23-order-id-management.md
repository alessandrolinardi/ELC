# Order ID Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize Order IDs to `{BRAND}-{PO}-{CAMPAIGN}-{SEQ}`, detect duplicates within and across files (3-month retention), auto-detect re-uploads and offer version bumps.

**Architecture:** Three new backend components — `order_id_manager.py` (format parsing/generation/validation), a `brands` CRUD router, and a `processed_orders` Supabase table for cross-file dedup. Phase 1 is extended to parse and normalize Order IDs alongside addresses. Frontend adds brand dropdown + campaign input to the upload form, and a duplicate warning dialog in the review step.

**Tech Stack:** FastAPI, Supabase (PostgreSQL), React + TypeScript, existing Claude AI parsing pipeline.

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/app/core/order_id_manager.py` | Parse, validate, normalize, generate Order IDs. Format: `{BRAND}-{PO}-{CAMPAIGN}-{SEQ}`. Version detection (`V2`, `V3`). Duplicate detection. |
| `backend/app/routers/brands.py` | CRUD endpoints for the brands list: `GET /api/v1/brands`, `POST /api/v1/brands` |
| `backend/tests/test_core/test_order_id_manager.py` | Unit tests for order ID parsing, normalization, version detection, duplicate detection |
| `backend/tests/test_routers/test_brands.py` | Endpoint tests for brands CRUD |

### Backend — Modified Files
| File | Changes |
|------|---------|
| `backend/app/routers/validator.py` | Extend `_process_parse` to call order ID validation. Extend `_process_validate` to write `processed_orders`. Add brand/campaign params to upload endpoint. |
| `backend/app/schemas/validator.py` | Add `brand`, `campaign` fields to upload/confirm schemas. Add order ID warning fields to parsed result. |
| `backend/app/main.py` | Register `brands` router |

### Frontend — Modified Files
| File | Changes |
|------|---------|
| `frontend/src/pages/AddressValidator.tsx` | Add brand dropdown + campaign input to upload form. Handle duplicate warnings in review step. |
| `frontend/src/lib/types.ts` | Add brand/campaign types, duplicate warning types |
| `frontend/src/api/client.ts` | Add `fetchBrands`, `createBrand` API wrappers |

### Supabase — New Tables
| Table | Purpose |
|-------|---------|
| `brands` | `name TEXT PRIMARY KEY, created_at TIMESTAMPTZ` |
| `processed_orders` | `order_number TEXT PRIMARY KEY, job_id TEXT, brand TEXT, campaign TEXT, po_number TEXT, processed_at TIMESTAMPTZ, expires_at TIMESTAMPTZ` |

---

## Task 1: Order ID Parser (`order_id_manager.py`)

**Files:**
- Create: `backend/app/core/order_id_manager.py`
- Test: `backend/tests/test_core/test_order_id_manager.py`

- [ ] **Step 1: Write failing tests for Order ID parsing**

```python
# backend/tests/test_core/test_order_id_manager.py
import pytest
from app.core.order_id_manager import parse_order_id, OrderIDComponents


class TestParseOrderID:
    def test_standard_format(self):
        result = parse_order_id("SBX-3501494822-GENNAIO TRADE VISIBILITY-1")
        assert result.brand == "SBX"
        assert result.po == "3501494822"
        assert result.campaign == "GENNAIO TRADE VISIBILITY"
        assert result.seq == 1
        assert result.version is None

    def test_with_version(self):
        result = parse_order_id("SBX-3501494822-GENNAIO TRADE VISIBILITY V2-1")
        assert result.campaign == "GENNAIO TRADE VISIBILITY"
        assert result.version == 2

    def test_with_v3(self):
        result = parse_order_id("SBX-3501494822-CAMPAIGN V3-42")
        assert result.version == 3
        assert result.seq == 42

    def test_unparseable_returns_none(self):
        result = parse_order_id("RANDOM GARBAGE")
        assert result is None

    def test_missing_po(self):
        result = parse_order_id("SBX--CAMPAIGN-1")
        assert result is None

    def test_empty_string(self):
        result = parse_order_id("")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/test_core/test_order_id_manager.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `order_id_manager.py` — parsing**

```python
# backend/app/core/order_id_manager.py
"""Order ID management: parsing, validation, normalization, dedup."""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderIDComponents:
    """Parsed components of an Order ID."""
    brand: str
    po: str
    campaign: str
    seq: int
    version: Optional[int] = None  # None = original, 2 = V2, 3 = V3...

    def format(self) -> str:
        """Reconstruct the canonical Order ID string."""
        campaign = self.campaign
        if self.version and self.version >= 2:
            campaign = f"{campaign} V{self.version}"
        return f"{self.brand}-{self.po}-{campaign}-{self.seq}"


# Pattern: BRAND-PO-CAMPAIGN[ VN]-SEQ
_ORDER_ID_RE = re.compile(
    r'^(?P<brand>[A-Za-z0-9]+)'
    r'-(?P<po>350\d{7})'
    r'-(?P<campaign>.+?)'
    r'(?:\s+V(?P<version>\d+))?'
    r'-(?P<seq>\d+)$'
)


def parse_order_id(raw: str) -> Optional[OrderIDComponents]:
    """Parse a raw Order ID string into components. Returns None if unparseable."""
    if not raw or not raw.strip():
        return None
    m = _ORDER_ID_RE.match(raw.strip())
    if not m:
        return None
    po = m.group("po")
    if not po:
        return None
    version_str = m.group("version")
    return OrderIDComponents(
        brand=m.group("brand").upper(),
        po=po,
        campaign=m.group("campaign").strip(),
        seq=int(m.group("seq")),
        version=int(version_str) if version_str else None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/test_core/test_order_id_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/order_id_manager.py backend/tests/test_core/test_order_id_manager.py
git commit -m "feat: add Order ID parser with format {BRAND}-{PO}-{CAMPAIGN}-{SEQ}"
```

---

## Task 2: Order ID Normalization and Generation

**Files:**
- Modify: `backend/app/core/order_id_manager.py`
- Test: `backend/tests/test_core/test_order_id_manager.py`

- [ ] **Step 1: Write failing tests for normalization and generation**

```python
# Add to test_order_id_manager.py

class TestNormalizeOrderID:
    def test_normalize_already_correct(self):
        result = normalize_order_id(
            "SBX-3501494822-GENNAIO TRADE VISIBILITY-1",
            expected_brand="SBX", expected_campaign="GENNAIO TRADE VISIBILITY"
        )
        assert result == "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"

    def test_normalize_wrong_brand(self):
        result = normalize_order_id(
            "WRONG-3501494822-CAMPAIGN-1",
            expected_brand="SBX", expected_campaign="CAMPAIGN"
        )
        assert result == "SBX-3501494822-CAMPAIGN-1"

    def test_normalize_preserves_version(self):
        result = normalize_order_id(
            "SBX-3501494822-CAMPAIGN V2-1",
            expected_brand="SBX", expected_campaign="CAMPAIGN"
        )
        assert "V2" in result

    def test_normalize_unparseable_returns_none(self):
        result = normalize_order_id("GARBAGE", expected_brand="SBX", expected_campaign="X")
        assert result is None


class TestGenerateOrderIDs:
    def test_generate_for_rows(self):
        po_numbers = ["3501494822", "3501494822", "3501494822"]
        results = generate_order_ids("SBX", po_numbers, "CAMPAIGN")
        assert results == [
            "SBX-3501494822-CAMPAIGN-1",
            "SBX-3501494822-CAMPAIGN-2",
            "SBX-3501494822-CAMPAIGN-3",
        ]

    def test_generate_with_version(self):
        results = generate_order_ids("SBX", ["3501494822"], "CAMPAIGN", version=2)
        assert results == ["SBX-3501494822-CAMPAIGN V2-1"]


class TestBumpVersion:
    def test_bump_none_to_v2(self):
        assert bump_version(None) == 2

    def test_bump_v2_to_v3(self):
        assert bump_version(2) == 3

    def test_bump_v5_to_v6(self):
        assert bump_version(5) == 6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/test_core/test_order_id_manager.py -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Implement normalization and generation**

Add to `order_id_manager.py`:

```python
def normalize_order_id(
    raw: str,
    expected_brand: str,
    expected_campaign: str,
) -> Optional[str]:
    """Normalize a raw Order ID to canonical format.
    Fixes brand/campaign if they don't match expected values.
    Returns None if the raw string is completely unparseable."""
    parsed = parse_order_id(raw)
    if not parsed:
        return None
    parsed.brand = expected_brand.upper()
    if not parsed.version:
        parsed.campaign = expected_campaign
    else:
        # Keep version, normalize base campaign
        parsed.campaign = expected_campaign
    return parsed.format()


def generate_order_ids(
    brand: str,
    po_numbers: list[str],
    campaign: str,
    version: Optional[int] = None,
) -> list[str]:
    """Generate canonical Order IDs for a list of rows."""
    results = []
    for i, po in enumerate(po_numbers, start=1):
        comp = OrderIDComponents(
            brand=brand.upper(),
            po=po,
            campaign=campaign,
            seq=i,
            version=version,
        )
        results.append(comp.format())
    return results


def bump_version(current_version: Optional[int]) -> int:
    """Get the next version number. None → 2, 2 → 3, etc."""
    return (current_version or 1) + 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/test_core/test_order_id_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/order_id_manager.py backend/tests/test_core/test_order_id_manager.py
git commit -m "feat: add Order ID normalization, generation, and version bump"
```

---

## Task 3: Duplicate Detection Functions

**Files:**
- Modify: `backend/app/core/order_id_manager.py`
- Test: `backend/tests/test_core/test_order_id_manager.py`

- [ ] **Step 1: Write failing tests for duplicate detection**

```python
# Add to test_order_id_manager.py

class TestWithinFileDuplicates:
    def test_no_duplicates(self):
        orders = ["SBX-350-A-1", "SBX-350-A-2", "SBX-350-A-3"]
        dupes = find_within_file_duplicates(orders)
        assert dupes == {}

    def test_exact_duplicates(self):
        orders = ["SBX-350-A-1", "SBX-350-A-2", "SBX-350-A-1"]
        dupes = find_within_file_duplicates(orders)
        assert "SBX-350-A-1" in dupes
        assert dupes["SBX-350-A-1"] == [0, 2]

    def test_empty_list(self):
        assert find_within_file_duplicates([]) == {}


class TestCrossFileDuplicates:
    def test_find_matches(self):
        """Uses a mock for Supabase — actual integration tested separately."""
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {"order_number": "SBX-350-A-1", "processed_at": "2026-03-01T10:00:00Z", "campaign": "A"}
        ]
        result = find_cross_file_duplicates(
            ["SBX-350-A-1", "SBX-350-A-2"], mock_client
        )
        assert len(result) == 1
        assert result["SBX-350-A-1"]["processed_at"] == "2026-03-01T10:00:00Z"

    def test_no_client_returns_empty(self):
        result = find_cross_file_duplicates(["SBX-350-A-1"], None)
        assert result == {}
```

- [ ] **Step 2: Run to verify fail, then implement**

Add to `order_id_manager.py`:

```python
def find_within_file_duplicates(order_numbers: list[str]) -> dict[str, list[int]]:
    """Find duplicate Order Numbers within a single file.
    Returns {order_number: [row_indices]} for duplicates only."""
    seen: dict[str, list[int]] = {}
    for i, on in enumerate(order_numbers):
        if not on:
            continue
        seen.setdefault(on, []).append(i)
    return {k: v for k, v in seen.items() if len(v) > 1}


def find_cross_file_duplicates(
    order_numbers: list[str],
    supabase_client,
) -> dict[str, dict]:
    """Check Order Numbers against processed_orders table.
    Returns {order_number: {processed_at, campaign, ...}} for matches."""
    if not supabase_client or not order_numbers:
        return {}
    try:
        # Filter out empties
        non_empty = [o for o in order_numbers if o]
        if not non_empty:
            return {}
        response = supabase_client.table("processed_orders").select(
            "order_number, processed_at, campaign, brand"
        ).in_("order_number", non_empty).execute()
        return {r["order_number"]: r for r in (response.data or [])}
    except Exception:
        return {}


def record_processed_orders(
    order_numbers: list[str],
    job_id: str,
    brand: str,
    campaign: str,
    po_number: str,
    supabase_client,
) -> int:
    """Write processed Order Numbers to Supabase for future dedup.
    Returns count of records written."""
    if not supabase_client or not order_numbers:
        return 0
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    records = [
        {
            "order_number": on,
            "job_id": job_id,
            "brand": brand,
            "campaign": campaign,
            "po_number": po_number,
            "processed_at": now.isoformat(),
            "expires_at": (now + timedelta(days=90)).isoformat(),
        }
        for on in order_numbers if on
    ]
    if not records:
        return 0
    try:
        supabase_client.table("processed_orders").upsert(
            records, on_conflict="order_number"
        ).execute()
        return len(records)
    except Exception:
        return 0
```

- [ ] **Step 3: Run tests, verify pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/test_core/test_order_id_manager.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/order_id_manager.py backend/tests/test_core/test_order_id_manager.py
git commit -m "feat: add within-file and cross-file duplicate detection"
```

---

## Task 4: Brands CRUD API

**Files:**
- Create: `backend/app/routers/brands.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routers/test_brands.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_routers/test_brands.py
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestBrandsAPI:
    def test_get_brands_returns_list(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
            {"name": "SBX", "created_at": "2026-01-01T00:00:00Z"},
            {"name": "DOUGLAS", "created_at": "2026-01-01T00:00:00Z"},
        ]
        with patch("app.routers.brands._get_supabase", return_value=mock_client):
            resp = client.get("/api/v1/brands")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_create_brand(self):
        mock_client = MagicMock()
        mock_client.table.return_value.upsert.return_value.execute.return_value.data = [
            {"name": "NEWBRAND"}
        ]
        with patch("app.routers.brands._get_supabase", return_value=mock_client):
            resp = client.post("/api/v1/brands", json={"name": "NEWBRAND"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "NEWBRAND"

    def test_create_brand_empty_name_rejected(self):
        resp = client.post("/api/v1/brands", json={"name": ""})
        assert resp.status_code == 400

    def test_get_brands_no_supabase(self):
        with patch("app.routers.brands._get_supabase", return_value=None):
            resp = client.get("/api/v1/brands")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
```

- [ ] **Step 2: Run to verify fail, then implement**

```python
# backend/app/routers/brands.py
"""Brands CRUD — manages the short list of brand names for Order IDs."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.config_compat import get_supabase_client

router = APIRouter()


def _get_supabase():
    return get_supabase_client()


class CreateBrandRequest(BaseModel):
    name: str


@router.get("/brands")
async def list_brands():
    client = _get_supabase()
    if not client:
        return {"ok": True, "data": []}
    try:
        response = client.table("brands").select("*").order("name").execute()
        return {"ok": True, "data": response.data or []}
    except Exception as e:
        return {"ok": True, "data": []}


@router.post("/brands")
async def create_brand(body: CreateBrandRequest):
    name = body.name.strip().upper()
    if not name:
        raise HTTPException(status_code=400, detail={
            "ok": False, "error": {"code": "EMPTY_NAME", "message": "Brand name cannot be empty"}
        })
    client = _get_supabase()
    if not client:
        raise HTTPException(status_code=503, detail={
            "ok": False, "error": {"code": "DB_UNAVAILABLE", "message": "Database unavailable"}
        })
    try:
        response = client.table("brands").upsert(
            {"name": name}, on_conflict="name"
        ).execute()
        return {"ok": True, "data": {"name": name}}
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "ok": False, "error": {"code": "DB_ERROR", "message": str(e)}
        })
```

- [ ] **Step 3: Register router in `main.py`**

Add to `backend/app/main.py` imports and router includes:
```python
from .routers import brands
app.include_router(brands.router, prefix="/api/v1", tags=["brands"])
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/test_routers/test_brands.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/brands.py backend/app/main.py backend/tests/test_routers/test_brands.py
git commit -m "feat: add brands CRUD API (GET + POST /api/v1/brands)"
```

---

## Task 5: Integrate Order ID Validation into Phase 1

**Files:**
- Modify: `backend/app/routers/validator.py`
- Modify: `backend/app/schemas/validator.py`

- [ ] **Step 1: Extend schemas**

Add to `backend/app/schemas/validator.py`:

```python
class OrderIDWarning(BaseModel):
    """Warning about an Order ID issue."""
    type: str  # "within_file_duplicate" | "cross_file_duplicate" | "format_error"
    message: str
    row_indices: list[int] = []
    processed_at: Optional[str] = None  # for cross-file duplicates


class OrderIDSummary(BaseModel):
    """Summary of Order ID validation in Phase 1 result."""
    total: int
    valid: int
    normalized: int
    format_errors: int
    within_file_duplicates: int
    cross_file_duplicates: int
    warnings: list[OrderIDWarning] = []
    detected_campaign: str = ""
    detected_version: Optional[int] = None
```

Add `brand` and `campaign` to the upload endpoint params, and `order_id_summary` to the parsed result.

- [ ] **Step 2: Extend `_process_parse` in validator.py**

After address parsing completes, add Order ID processing:

```python
# After building rows[], before saving result:
from ..core.order_id_manager import (
    parse_order_id, normalize_order_id, find_within_file_duplicates,
    find_cross_file_duplicates,
)
from ..core.config_compat import get_supabase_client as _get_supabase

# Extract Order Numbers from DataFrame
order_col = col_map.get('order_number')
order_numbers = []
if order_col:
    for idx, row in df.iterrows():
        raw = str(row.get(order_col, '')).strip()
        if raw.lower() == 'nan':
            raw = ''
        order_numbers.append(raw)

# Parse and validate
order_warnings = []
valid_count = 0
normalized_count = 0
format_errors = 0
detected_campaign = campaign  # from upload form

for i, raw_on in enumerate(order_numbers):
    if not raw_on:
        format_errors += 1
        continue
    parsed_on = parse_order_id(raw_on)
    if parsed_on:
        valid_count += 1
        if not detected_campaign and parsed_on.campaign:
            detected_campaign = parsed_on.campaign
    else:
        format_errors += 1

# Within-file duplicates
within_dupes = find_within_file_duplicates(order_numbers)
for on, indices in within_dupes.items():
    order_warnings.append({
        "type": "within_file_duplicate",
        "message": f"Ordine duplicato: {on} (righe {', '.join(str(i+1) for i in indices)})",
        "row_indices": indices,
    })

# Cross-file duplicates
cross_dupes = find_cross_file_duplicates(order_numbers, _get_supabase())
for on, info in cross_dupes.items():
    order_warnings.append({
        "type": "cross_file_duplicate",
        "message": f"Ordine già processato il {info.get('processed_at', '?')[:10]}",
        "row_indices": [i for i, o in enumerate(order_numbers) if o == on],
        "processed_at": info.get("processed_at"),
    })
```

Add `order_id_summary` to the result dict.

- [ ] **Step 3: Extend upload endpoint to accept brand/campaign**

Add `brand: str = Form("")` and `campaign: str = Form("")` to `create_validator_job` params, pass them through to `_process_parse`.

- [ ] **Step 4: Run existing tests to verify nothing breaks**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/ -k "not pdf_processor" -q`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/validator.py backend/app/schemas/validator.py
git commit -m "feat: integrate Order ID validation into Phase 1 parsing"
```

---

## Task 6: Write Processed Orders on Phase 2 Completion

**Files:**
- Modify: `backend/app/routers/validator.py`

- [ ] **Step 1: Extend `_process_validate` to record processed orders**

After Phase 2 completes successfully (after `job_store.update_status(job_id, "complete", ...)`):

```python
from ..core.order_id_manager import record_processed_orders

# Record processed orders for future dedup
if order_numbers:
    record_processed_orders(
        order_numbers=order_numbers,
        job_id=job_id,
        brand=config.get("brand", ""),
        campaign=config.get("campaign", ""),
        po_number=config.get("po_number", ""),
        supabase_client=_get_supabase(),
    )
```

The `order_numbers` list needs to be passed through the `config` dict in the parsed result, or reconstructed from the DataFrame's order column.

- [ ] **Step 2: Run tests, verify pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/ -k "not pdf_processor" -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/validator.py
git commit -m "feat: record processed orders to Supabase on Phase 2 completion"
```

---

## Task 7: Frontend — Brand Dropdown + Campaign Input

**Files:**
- Modify: `frontend/src/pages/AddressValidator.tsx`
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add API client functions**

Add to `frontend/src/api/client.ts`:

```typescript
export async function fetchBrands(): Promise<{ name: string }[]> {
  return api.get<{ name: string }[]>("/api/v1/brands")
}

export async function createBrand(name: string): Promise<{ name: string }> {
  return api.post<{ name: string }>("/api/v1/brands", { name })
}
```

- [ ] **Step 2: Add types**

Add to `frontend/src/lib/types.ts`:

```typescript
export interface OrderIDWarning {
  type: "within_file_duplicate" | "cross_file_duplicate" | "format_error"
  message: string
  row_indices: number[]
  processed_at?: string
}

export interface OrderIDSummary {
  total: number
  valid: number
  normalized: number
  format_errors: number
  within_file_duplicates: number
  cross_file_duplicates: number
  warnings: OrderIDWarning[]
  detected_campaign: string
  detected_version: number | null
}
```

Add `order_id_summary?: OrderIDSummary` to `ParsedJobResult`.

- [ ] **Step 3: Add brand/campaign to upload form in AddressValidator.tsx**

Add state:
```typescript
const [brand, setBrand] = useState("")
const [campaign, setCampaign] = useState("")
const [brands, setBrands] = useState<string[]>([])
const [newBrandInput, setNewBrandInput] = useState("")
const [showNewBrand, setShowNewBrand] = useState(false)
```

Add `useEffect` to fetch brands on mount:
```typescript
useEffect(() => {
  fetchBrands().then(data => setBrands(data.map(b => b.name))).catch(() => {})
}, [])
```

Add to upload form (before the "Avvia Validazione" button):
```tsx
<div className="grid grid-cols-2 gap-4">
  <div>
    <Label className="text-xs text-muted-foreground">Brand</Label>
    <select
      value={brand}
      onChange={(e) => {
        if (e.target.value === "__new__") { setShowNewBrand(true) }
        else { setBrand(e.target.value) }
      }}
      className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm"
    >
      <option value="">Seleziona brand...</option>
      {brands.map(b => <option key={b} value={b}>{b}</option>)}
      <option value="__new__">+ Aggiungi brand</option>
    </select>
  </div>
  <div>
    <Label className="text-xs text-muted-foreground">Campagna</Label>
    <Input
      value={campaign}
      onChange={(e) => setCampaign(e.target.value)}
      placeholder="es. GENNAIO TRADE VISIBILITY"
      className="mt-1"
    />
  </div>
</div>
```

Pass `brand` and `campaign` in the FormData:
```typescript
formData.append("brand", brand)
formData.append("campaign", campaign)
```

- [ ] **Step 4: Typecheck**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/frontend && npx tsc --noEmit`
Expected: Clean

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AddressValidator.tsx frontend/src/lib/types.ts frontend/src/api/client.ts
git commit -m "feat: add brand dropdown and campaign input to upload form"
```

---

## Task 8: Frontend — Duplicate Warning in Review Step

**Files:**
- Modify: `frontend/src/pages/AddressValidator.tsx`

- [ ] **Step 1: Show duplicate warnings after Phase 1**

In Step 1 (review), after `<ParseReviewTable>`, check for `order_id_summary.warnings`:

```tsx
{parsedResult?.order_id_summary?.warnings?.length > 0 && (
  <div className="rounded-lg bg-amber-50 border border-amber-200 px-5 py-4">
    <p className="text-sm font-semibold text-amber-800">
      {parsedResult.order_id_summary.cross_file_duplicates > 0
        ? "Ordini già processati trovati"
        : "Ordini duplicati nel file"}
    </p>
    {parsedResult.order_id_summary.warnings.map((w, i) => (
      <p key={i} className="text-sm text-amber-700 mt-1">{w.message}</p>
    ))}
    {parsedResult.order_id_summary.cross_file_duplicates > 0 && (
      <div className="mt-3">
        <p className="text-sm text-amber-800 font-medium">
          È un ri-caricamento per correggere errori?
        </p>
        <div className="flex gap-2 mt-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {/* set reupload flag, version bump */}}
            className="border-amber-400 text-amber-800 hover:bg-amber-100"
          >
            Sì, incrementa versione
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {/* proceed without version bump */}}
            className="text-muted-foreground"
          >
            No, procedi comunque
          </Button>
        </div>
      </div>
    )}
  </div>
)}
```

- [ ] **Step 2: Typecheck and verify**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/frontend && npx tsc --noEmit`
Expected: Clean

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/AddressValidator.tsx
git commit -m "feat: show duplicate warnings and re-upload prompt in review step"
```

---

## Task 9: Supabase Table Setup

**Files:**
- Create: `backend/data/supabase_migrations/003_order_id_tables.sql`

- [ ] **Step 1: Write migration SQL**

```sql
-- brands table
CREATE TABLE IF NOT EXISTS brands (
    name TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial brands
INSERT INTO brands (name) VALUES ('SBX'), ('DOUGLAS')
ON CONFLICT (name) DO NOTHING;

-- processed_orders table with 90-day TTL
CREATE TABLE IF NOT EXISTS processed_orders (
    order_number TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    brand TEXT,
    campaign TEXT,
    po_number TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '90 days')
);

CREATE INDEX IF NOT EXISTS idx_processed_orders_expires
    ON processed_orders (expires_at);

-- Optional: Supabase cron to clean expired records
-- SELECT cron.schedule('cleanup-processed-orders', '0 3 * * *',
--   $$DELETE FROM processed_orders WHERE expires_at < NOW()$$
-- );
```

- [ ] **Step 2: Run migration in Supabase dashboard**

Execute the SQL in the Supabase SQL Editor.

- [ ] **Step 3: Commit**

```bash
git add backend/data/supabase_migrations/003_order_id_tables.sql
git commit -m "feat: add Supabase migration for brands and processed_orders tables"
```

---

## Task 10: Integration Test — Full Flow

**Files:**
- Create: `backend/tests/test_core/test_order_id_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# backend/tests/test_core/test_order_id_integration.py
"""Integration test for the full Order ID flow."""
from app.core.order_id_manager import (
    parse_order_id, normalize_order_id, generate_order_ids,
    find_within_file_duplicates, bump_version,
)


class TestFullOrderIDFlow:
    def test_parse_normalize_roundtrip(self):
        raw = "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"
        parsed = parse_order_id(raw)
        normalized = normalize_order_id(raw, "SBX", "GENNAIO TRADE VISIBILITY")
        assert normalized == raw

    def test_reupload_version_bump_flow(self):
        # Original upload
        original = generate_order_ids("SBX", ["3501494822"] * 3, "CAMPAIGN")
        assert original[0] == "SBX-3501494822-CAMPAIGN-1"

        # Detect duplicate → user says "yes, re-upload"
        new_version = bump_version(None)  # original had no version
        reupload = generate_order_ids("SBX", ["3501494822"] * 3, "CAMPAIGN", version=new_version)
        assert reupload[0] == "SBX-3501494822-CAMPAIGN V2-1"
        assert reupload[0] != original[0]  # ShippyPro sees different ID

        # Parse V2 back
        parsed_v2 = parse_order_id(reupload[0])
        assert parsed_v2.version == 2
        assert parsed_v2.campaign == "CAMPAIGN"

    def test_within_file_duplicate_detection(self):
        orders = generate_order_ids("SBX", ["3501494822"] * 3, "CAMPAIGN")
        # Inject a duplicate
        orders.append(orders[0])
        dupes = find_within_file_duplicates(orders)
        assert orders[0] in dupes
        assert dupes[orders[0]] == [0, 3]
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/backend && python3 -m pytest tests/ -k "not pdf_processor" -q`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_core/test_order_id_integration.py
git commit -m "test: add Order ID integration tests for full flow"
```
