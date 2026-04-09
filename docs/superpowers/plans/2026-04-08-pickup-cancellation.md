# Pickup Cancellation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to cancel upcoming pickups from the storico, soft-deleting them with a "cancelled" status and notifying the team via Zapier.

**Architecture:** Two-step cancel flow — fetch + validate, then conditional UPDATE as race-condition safety net. Shared `_build_zapier_payload()` helper extracted from the inline creation payload, used by both creation and cancellation. New `<CancelPickupDialog>` component in the frontend.

**Tech Stack:** Python/FastAPI, Supabase (PostgREST client), React/TypeScript, React Query, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-08-pickup-cancellation-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/data/supabase_migrations/005_add_cancellation_fields.sql` | DB migration |
| Modify | `backend/app/schemas/pickup.py` | Add `CancelPickupRequest`, update `PickupRecord` |
| Modify | `backend/app/core/pickup_store.py` | Add `get_pickup`, `cancel_pickup`, `update_zapier_status`, fix timezone |
| Modify | `backend/app/core/pickup.py` | Extract `_build_zapier_payload`, add `cancel_pickup_flow`, `send_cancellation_notification` |
| Modify | `backend/app/routers/pickup.py` | Add `POST /{pickup_id}/cancel` route |
| Modify | `backend/tests/test_core/test_pickup.py` | All new backend tests |
| Modify | `frontend/src/lib/types.ts` | Add cancellation fields to `PickupRecord` |
| Modify | `frontend/src/api/client.ts` | Add `cancelPickup()` convenience wrapper |
| Create | `frontend/src/components/CancelPickupDialog.tsx` | Confirmation dialog component |
| Modify | `frontend/src/components/PickupHistory.tsx` | Cancel button, STATUS_LABELS, dimmed row |
| Modify | `frontend/src/hooks/usePickupHistory.ts` | Add `useCancelPickup` mutation hook |

---

### Task 1: Database Migration

**Files:**
- Create: `backend/data/supabase_migrations/005_add_cancellation_fields.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- Add cancellation tracking columns to elc_pickups
ALTER TABLE elc_pickups ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE elc_pickups ADD COLUMN IF NOT EXISTS cancellation_reason TEXT DEFAULT NULL;
ALTER TABLE elc_pickups ADD COLUMN IF NOT EXISTS zapier_notified BOOLEAN DEFAULT NULL;
```

- [ ] **Step 2: Run the migration against Supabase**

Run this in the Supabase SQL editor or via the CLI. All three columns are nullable with defaults — safe for a live table with existing data.

- [ ] **Step 3: Commit**

```bash
git add backend/data/supabase_migrations/005_add_cancellation_fields.sql
git commit -m "feat: add cancellation columns to elc_pickups (migration 005)"
```

---

### Task 2: Backend Schemas

**Files:**
- Modify: `backend/app/schemas/pickup.py`

- [ ] **Step 1: Add `CancelPickupRequest` and update `PickupRecord`**

At the end of `backend/app/schemas/pickup.py`, add the new schema. Also update `PickupRecord` with the three new fields.

Add to `PickupRecord` class (after line 81, before `created_at`):

```python
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    zapier_notified: Optional[bool] = None
```

Add new class after `PickupRecord`:

```python
class CancelPickupRequest(BaseModel):
    reason: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def validate_reason_length(cls, v):
        if v is not None and len(v) > 500:
            raise ValueError("Il motivo non può superare 500 caratteri")
        return v
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/pickup.py
git commit -m "feat: add CancelPickupRequest schema and update PickupRecord"
```

---

### Task 3: Persistence Layer — `pickup_store.py`

**Files:**
- Modify: `backend/app/core/pickup_store.py`
- Test: `backend/tests/test_core/test_pickup.py`

- [ ] **Step 1: Write failing tests for `get_pickup`**

These tests will mock the Supabase client. Add to `backend/tests/test_core/test_pickup.py`:

```python
from unittest.mock import patch, MagicMock
from app.core.pickup_store import get_pickup, cancel_pickup, update_zapier_status


class TestGetPickup:
    """get_pickup should fetch a single record by ID."""

    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_record_when_found(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [{"id": "abc-123", "carrier": "DHL", "pickup_status": None}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = get_pickup("abc-123")
        assert result == {"id": "abc-123", "carrier": "DHL", "pickup_status": None}
        mock_client.table.assert_called_with("elc_pickups")

    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_none_when_not_found(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = get_pickup("nonexistent")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestGetPickup -v`
Expected: FAIL — `ImportError: cannot import name 'get_pickup'`

- [ ] **Step 3: Implement `get_pickup`**

Add to `backend/app/core/pickup_store.py` after the `save_pickup` function:

```python
def get_pickup(pickup_id: str) -> dict | None:
    """Fetch a single pickup record by ID. Returns None if not found."""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        response = client.table(TABLE).select("*").eq("id", pickup_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.exception("Error fetching pickup %s: %s", pickup_id, e)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestGetPickup -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for `cancel_pickup`**

```python
class TestCancelPickup:
    """cancel_pickup should do atomic conditional update."""

    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_updated_record_on_success(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [{"id": "abc-123", "pickup_status": "cancelled", "cancelled_at": "2026-04-08T12:00:00Z"}]
        mock_client.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = mock_response

        result = cancel_pickup("abc-123", "cambio data")
        assert result is not None
        assert result["pickup_status"] == "cancelled"

    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_none_when_already_cancelled(self, mock_client_fn):
        """If neq condition fails (already cancelled), data is empty."""
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = mock_response

        result = cancel_pickup("abc-123", None)
        assert result is None

    @patch("app.core.pickup_store.get_supabase_client")
    def test_cancel_with_null_reason(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [{"id": "abc-123", "pickup_status": "cancelled"}]
        mock_client.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = mock_response

        result = cancel_pickup("abc-123", None)
        assert result is not None
        # Verify the update call included reason=None
        update_call = mock_client.table.return_value.update.call_args[0][0]
        assert update_call["cancellation_reason"] is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestCancelPickup -v`
Expected: FAIL — `ImportError: cannot import name 'cancel_pickup'`

- [ ] **Step 7: Implement `cancel_pickup` and `update_zapier_status`**

Add to `backend/app/core/pickup_store.py`:

```python
from datetime import datetime, timezone


def cancel_pickup(pickup_id: str, reason: str | None) -> dict | None:
    """Atomically cancel a pickup if not already cancelled.

    Uses conditional update (neq pickup_status cancelled) as concurrency safety net.
    Returns the updated record, or None if the condition failed (already cancelled).
    """
    try:
        client = get_supabase_client()
        if client is None:
            return None
        response = (
            client.table(TABLE)
            .update({
                "pickup_status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
                "cancellation_reason": reason,
            })
            .eq("id", pickup_id)
            .neq("pickup_status", "cancelled")
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        logger.exception("Error cancelling pickup %s: %s", pickup_id, e)
        return None


def update_zapier_status(pickup_id: str, notified: bool) -> None:
    """Persist zapier_notified flag after webhook attempt."""
    try:
        client = get_supabase_client()
        if client is None:
            return
        client.table(TABLE).update({"zapier_notified": notified}).eq("id", pickup_id).execute()
    except Exception as e:
        logger.exception("Error updating zapier status for pickup %s: %s", pickup_id, e)
```

Also update the import at the top of the file — add `datetime, timezone`:

```python
from datetime import date, datetime, timezone
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestCancelPickup -v`
Expected: PASS

- [ ] **Step 9: Fix timezone in `list_pickups`**

In `backend/app/core/pickup_store.py`, change line 41 from:

```python
        today_str = date.today().isoformat()
```

to:

```python
        from zoneinfo import ZoneInfo
        today_str = datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()
```

- [ ] **Step 10: Commit**

```bash
git add backend/app/core/pickup_store.py backend/tests/test_core/test_pickup.py
git commit -m "feat: add get_pickup, cancel_pickup, update_zapier_status + fix timezone"
```

---

### Task 4: Extract `_build_zapier_payload` + Add `event_type` to Creation

**Files:**
- Modify: `backend/app/core/pickup.py`
- Test: `backend/tests/test_core/test_pickup.py`

This is the most delicate refactor — extracting the inline payload dict (lines 200-287 of `pickup.py`) into a shared helper. The creation flow must remain identical.

- [ ] **Step 1: Write failing test for `_build_zapier_payload`**

Add to `backend/tests/test_core/test_pickup.py`:

```python
from app.core.pickup import _build_zapier_payload


class TestBuildZapierPayload:
    """_build_zapier_payload should reconstruct the full Zapier payload from a DB record."""

    SAMPLE_RECORD = {
        "id": "abc-123",
        "carrier": "DHL",
        "pickup_date": "2026-04-10",
        "time_start": "09:00:00",
        "time_end": "16:00:00",
        "company": "Acme Srl",
        "contact_name": "Mario Rossi",
        "address": "Via Roma 1",
        "zip_code": "20121",
        "city": "Milano",
        "province": "MI",
        "phone": "0212345678",
        "reference": "ORD-001",
        "num_packages": 3,
        "weight_per_package": 5.0,
        "length": 30.0,
        "width": 20.0,
        "height": 10.0,
        "use_pallet": False,
        "num_pallets": 0,
        "pallet_length": 0.0,
        "pallet_width": 0.0,
        "pallet_height": 0.0,
        "notes": "Fragile",
        "pickup_status": "booked",
        "pickup_id": None,
        "confirmation_id": None,
        "created_at": "2026-04-08T10:00:00Z",
    }

    def test_creation_payload_has_event_type(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["event_type"] == "creation"

    def test_cancellation_payload_has_event_type(self):
        record = {**self.SAMPLE_RECORD, "cancellation_reason": "cambio data", "cancelled_at": "2026-04-08T14:30:00Z"}
        payload = _build_zapier_payload(record, "cancellation")
        assert payload["event_type"] == "cancellation"
        assert payload["cancellation_reason"] == "cambio data"
        assert "cancelled_at" in payload
        assert payload["subject"].startswith("ANNULLAMENTO")

    def test_creation_payload_has_no_cancellation_fields(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert "cancellation_reason" not in payload
        assert "cancelled_at" not in payload

    def test_shipment_type_normal(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["shipment_type"] == "NORMAL"
        assert payload["total_weight"] == 15.0

    def test_shipment_type_freight(self):
        record = {**self.SAMPLE_RECORD, "num_packages": 10, "weight_per_package": 8.0}
        payload = _build_zapier_payload(record, "creation")
        assert payload["shipment_type"] == "FREIGHT"
        assert payload["total_weight"] == 80.0

    def test_direct_passthrough_fields(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["carrier"] == "DHL"
        assert payload["company"] == "Acme Srl"
        assert payload["contact_name"] == "Mario Rossi"
        assert payload["reference"] == "ORD-001"
        assert payload["phone"] == "0212345678"
        assert payload["zip_code"] == "20121"

    def test_derived_fields(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["pickup_date"] == "10/04/2026"
        assert payload["time_window"] == "09:00 - 16:00"
        assert payload["full_address"] == "Via Roma 1, 20121 Milano (MI)"
        assert payload["address_line1"] == "Acme Srl - Mario Rossi"
        assert payload["package_dimensions"] == "30.0 x 20.0 x 10.0 cm"
        assert payload["summary_packages"] == "3 colli x 5.0 kg = 15.0 kg totali"
        assert payload["has_notes"] is True

    def test_creation_includes_pickup_webhook(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert "pickup_webhook" in payload

    def test_cancellation_excludes_pickup_webhook(self):
        record = {**self.SAMPLE_RECORD, "cancellation_reason": None, "cancelled_at": "2026-04-08T14:30:00Z"}
        payload = _build_zapier_payload(record, "cancellation")
        assert "pickup_webhook" not in payload

    def test_both_event_types_share_base_fields(self):
        """Base fields should be identical regardless of event type."""
        record_cancel = {**self.SAMPLE_RECORD, "cancellation_reason": None, "cancelled_at": "2026-04-08T14:30:00Z"}
        creation = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        cancellation = _build_zapier_payload(record_cancel, "cancellation")
        # Compare base fields (excluding event-type-specific ones)
        skip_keys = {"event_type", "subject", "request_id", "timestamp", "cancellation_reason", "cancelled_at", "pickup_webhook"}
        for key in creation:
            if key not in skip_keys:
                assert creation[key] == cancellation[key], f"Field {key} differs"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestBuildZapierPayload -v`
Expected: FAIL — `ImportError: cannot import name '_build_zapier_payload'`

- [ ] **Step 3: Extract `_build_zapier_payload` from `send_pickup_request`**

In `backend/app/core/pickup.py`, add this new function before `send_pickup_request` (before line 146). It reconstructs the same payload that was previously inline in `send_pickup_request`, but from a dict record instead of individual parameters:

```python
def _build_zapier_payload(record: dict, event_type: str) -> dict:
    """Build the full Zapier webhook payload from a DB record.

    Used by both creation and cancellation flows. Recomputes all derived
    fields from the raw columns stored in elc_pickups.
    """
    from zoneinfo import ZoneInfo

    # Parse stored values
    carrier = record["carrier"]
    pickup_date_str = record["pickup_date"]  # ISO "2026-04-10"
    time_start_str = record["time_start"]     # ISO "09:00:00"
    time_end_str = record["time_end"]
    company = record["company"]
    contact_name = record.get("contact_name", "")
    address = record["address"]
    zip_code = record["zip_code"]
    city = record["city"]
    province = record.get("province", "")
    phone = record.get("phone", "")
    reference = record.get("reference", "")
    num_packages = record["num_packages"]
    weight_per_package = float(record["weight_per_package"])
    length = float(record["length"])
    width = float(record["width"])
    height = float(record["height"])
    use_pallet = record.get("use_pallet", False)
    num_pallets = record.get("num_pallets", 0)
    pallet_length = float(record.get("pallet_length", 0))
    pallet_width = float(record.get("pallet_width", 0))
    pallet_height = float(record.get("pallet_height", 0))
    notes = record.get("notes", "")

    # Derived values
    total_weight = num_packages * weight_per_package
    shipment_type = "FREIGHT" if total_weight > 70 else "NORMAL"
    package_volume = length * width * height / 1_000_000
    total_volume = package_volume * num_packages

    # Parse date for formatting
    parts = pickup_date_str.split("-")  # "2026-04-10"
    date_str = f"{parts[2]}/{parts[1]}/{parts[0]}"  # "10/04/2026"

    # Time formatting — strip seconds if present
    ts = time_start_str[:5]  # "09:00"
    te = time_end_str[:5]    # "16:00"

    # Timestamp in Europe/Rome
    rome = ZoneInfo("Europe/Rome")
    timestamp = datetime.now(rome).strftime("%d/%m/%Y %H:%M")

    # Subject
    if event_type == "cancellation":
        subject = f"ANNULLAMENTO - {carrier} - {date_str} - {shipment_type}"
    else:
        subject = f"{carrier} - {date_str} - {shipment_type}"

    # Dimensions strings
    package_dimensions_str = f"{length} x {width} x {height} cm"
    pallet_dimensions_str = f"{pallet_length} x {pallet_width} x {pallet_height} cm" if use_pallet else "-"

    payload = {
        # Dedup
        "request_id": str(uuid.uuid4()),

        # Meta
        "event_type": event_type,
        "subject": subject,
        "timestamp": timestamp,
        "shipment_type": shipment_type,

        # Carrier
        "carrier": carrier,

        # Date/Time
        "pickup_date": date_str,
        "time_start": ts,
        "time_end": te,
        "time_window": f"{ts} - {te}",

        # Address — individual
        "company": company,
        "contact_name": contact_name,
        "address": address,
        "zip_code": zip_code,
        "city": city,
        "province": province,
        "phone": phone,
        "reference": reference,
        # Address — formatted
        "full_address": f"{address}, {zip_code} {city} ({province})",
        "address_line1": f"{company} - {contact_name}" if contact_name else company,
        "address_line2": f"{address}, {zip_code} {city} ({province})",

        # Packages — individual
        "num_packages": num_packages,
        "weight_per_package": weight_per_package,
        "weight_per_package_str": f"{weight_per_package} kg",
        "package_length": length,
        "package_width": width,
        "package_height": height,
        # Packages — calculated
        "total_weight": total_weight,
        "total_weight_str": f"{total_weight:.1f} kg",
        "package_dimensions": package_dimensions_str,
        "package_volume_m3": round(package_volume, 3),
        "total_volume_m3": round(total_volume, 3),

        # Pallet
        "use_pallet": use_pallet,
        "use_pallet_str": "Si" if use_pallet else "No",
        "num_pallets": num_pallets if use_pallet else 0,
        "pallet_length": pallet_length if use_pallet else 0,
        "pallet_width": pallet_width if use_pallet else 0,
        "pallet_height": pallet_height if use_pallet else 0,
        "pallet_dimensions": pallet_dimensions_str,

        # Notes
        "notes": notes if notes else "",
        "has_notes": bool(notes),

        # Summary
        "summary_packages": f"{num_packages} colli x {weight_per_package} kg = {total_weight:.1f} kg totali",
        "summary_dimensions": f"Dimensioni collo: {package_dimensions_str}",
        "summary_pallet": f"{num_pallets} pallet ({pallet_dimensions_str})" if use_pallet else "Nessun pallet",
    }

    # Event-type-specific fields
    if event_type == "creation":
        # Parse time objects for pickup webhook builder
        t_start = time(*[int(x) for x in time_start_str.split(":")[:2]])
        t_end = time(*[int(x) for x in time_end_str.split(":")[:2]])
        d = date(*[int(x) for x in pickup_date_str.split("-")])

        payload["pickup_webhook"] = _build_pickup_webhook_payload(
            carrier=carrier, contact_name=contact_name, company=company,
            address=address, city=city, province=province, zip_code=zip_code,
            phone=phone, pickup_date=d, time_start=t_start, time_end=t_end,
            num_packages=num_packages, weight_per_package=weight_per_package,
            length=length, width=width, height=height, notes=notes,
            use_pallet=use_pallet, num_pallets=num_pallets,
            pallet_dimensions_str=pallet_dimensions_str,
        )
    elif event_type == "cancellation":
        payload["cancellation_reason"] = record.get("cancellation_reason")
        # Format cancelled_at in Europe/Rome
        cancelled_at_raw = record.get("cancelled_at", "")
        if cancelled_at_raw:
            try:
                dt = datetime.fromisoformat(cancelled_at_raw)
                payload["cancelled_at"] = dt.astimezone(rome).strftime("%d/%m/%Y %H:%M")
            except Exception:
                payload["cancelled_at"] = cancelled_at_raw
        else:
            payload["cancelled_at"] = timestamp  # fallback to now

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestBuildZapierPayload -v`
Expected: PASS

- [ ] **Step 5: Refactor `send_pickup_request` to use `_build_zapier_payload`**

Replace lines 177-287 in `send_pickup_request` (the calculation + payload dict) with a call to the helper. The function still receives individual parameters, so we build a record dict first:

Replace the body of `send_pickup_request` (from `# Calculate totals` through the `payload = {...}` block) with:

```python
    # Build a record dict matching DB column format for the shared helper
    record = {
        "carrier": carrier,
        "pickup_date": pickup_date.isoformat(),
        "time_start": time_start.isoformat(),
        "time_end": time_end.isoformat(),
        "company": company,
        "contact_name": contact_name,
        "address": address,
        "zip_code": zip_code,
        "city": city,
        "province": province,
        "phone": phone,
        "reference": reference,
        "num_packages": num_packages,
        "weight_per_package": weight_per_package,
        "length": length,
        "width": width,
        "height": height,
        "use_pallet": use_pallet,
        "num_pallets": num_pallets,
        "pallet_length": pallet_length,
        "pallet_width": pallet_width,
        "pallet_height": pallet_height,
        "notes": notes,
    }
    payload = _build_zapier_payload(record, "creation")
```

Keep everything from `# --- Send to Zapier ---` onward unchanged.

- [ ] **Step 6: Run ALL existing tests to verify no regression**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py -v`
Expected: ALL PASS — the refactor must not change any behavior.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/pickup.py backend/tests/test_core/test_pickup.py
git commit -m "feat: extract _build_zapier_payload helper, add event_type to creation"
```

---

### Task 5: Cancel Flow Business Logic

**Files:**
- Modify: `backend/app/core/pickup.py`
- Test: `backend/tests/test_core/test_pickup.py`

- [ ] **Step 1: Write failing tests for `cancel_pickup_flow`**

```python
from unittest.mock import patch, MagicMock
from datetime import date
from app.core.pickup import cancel_pickup_flow


class TestCancelPickupFlow:
    """cancel_pickup_flow orchestrates validation, cancellation, and notification."""

    UPCOMING_RECORD = {
        "id": "abc-123",
        "carrier": "DHL",
        "pickup_date": "2099-12-31",  # far future = always upcoming
        "time_start": "09:00:00",
        "time_end": "16:00:00",
        "company": "Acme Srl",
        "contact_name": "Mario Rossi",
        "address": "Via Roma 1",
        "zip_code": "20121",
        "city": "Milano",
        "province": "MI",
        "phone": "0212345678",
        "reference": "ORD-001",
        "num_packages": 3,
        "weight_per_package": 5.0,
        "length": 30.0,
        "width": 20.0,
        "height": 10.0,
        "use_pallet": False,
        "num_pallets": 0,
        "pallet_length": 0.0,
        "pallet_width": 0.0,
        "pallet_height": 0.0,
        "notes": "",
        "pickup_status": "booked",
        "cancelled_at": None,
        "cancellation_reason": None,
        "created_at": "2026-04-08T10:00:00Z",
    }

    @patch("app.core.pickup.update_zapier_status")
    @patch("app.core.pickup.requests.post")
    @patch("app.core.pickup.cancel_pickup")
    @patch("app.core.pickup.get_pickup")
    @patch("app.core.pickup.get_secret", return_value="https://hooks.zapier.com/test")
    def test_successful_cancellation(self, mock_secret, mock_get, mock_cancel, mock_post, mock_zapier_status):
        mock_get.return_value = self.UPCOMING_RECORD
        cancelled = {**self.UPCOMING_RECORD, "pickup_status": "cancelled", "cancelled_at": "2026-04-08T14:30:00Z"}
        mock_cancel.return_value = cancelled
        mock_post.return_value = MagicMock(status_code=200)

        result = cancel_pickup_flow("abc-123", "cambio data")
        assert result["ok"] is True
        assert result["zapier_notified"] is True
        mock_zapier_status.assert_called_once_with("abc-123", True)

    @patch("app.core.pickup.get_pickup")
    def test_not_found_raises_404(self, mock_get):
        mock_get.return_value = None
        result = cancel_pickup_flow("nonexistent", None)
        assert result["ok"] is False
        assert result["status_code"] == 404

    @patch("app.core.pickup.get_pickup")
    def test_already_cancelled_raises_409(self, mock_get):
        record = {**self.UPCOMING_RECORD, "pickup_status": "cancelled"}
        mock_get.return_value = record
        result = cancel_pickup_flow("abc-123", None)
        assert result["ok"] is False
        assert result["status_code"] == 409

    @patch("app.core.pickup.get_pickup")
    def test_past_pickup_raises_422(self, mock_get):
        record = {**self.UPCOMING_RECORD, "pickup_date": "2020-01-01"}
        mock_get.return_value = record
        result = cancel_pickup_flow("abc-123", None)
        assert result["ok"] is False
        assert result["status_code"] == 422

    @patch("app.core.pickup.get_pickup")
    def test_failed_status_can_be_cancelled(self, mock_get):
        """Pickups with status 'failed' should be cancellable."""
        record = {**self.UPCOMING_RECORD, "pickup_status": "failed"}
        mock_get.return_value = record
        with patch("app.core.pickup.cancel_pickup") as mock_cancel, \
             patch("app.core.pickup.requests.post") as mock_post, \
             patch("app.core.pickup.update_zapier_status"), \
             patch("app.core.pickup.get_secret", return_value="https://hooks.zapier.com/test"):
            mock_cancel.return_value = {**record, "pickup_status": "cancelled"}
            mock_post.return_value = MagicMock(status_code=200)
            result = cancel_pickup_flow("abc-123", None)
            assert result["ok"] is True

    @patch("app.core.pickup.update_zapier_status")
    @patch("app.core.pickup.requests.post", side_effect=Exception("connection error"))
    @patch("app.core.pickup.cancel_pickup")
    @patch("app.core.pickup.get_pickup")
    @patch("app.core.pickup.get_secret", return_value="https://hooks.zapier.com/test")
    def test_zapier_failure_still_succeeds(self, mock_secret, mock_get, mock_cancel, mock_post, mock_zapier_status):
        mock_get.return_value = self.UPCOMING_RECORD
        mock_cancel.return_value = {**self.UPCOMING_RECORD, "pickup_status": "cancelled"}

        result = cancel_pickup_flow("abc-123", None)
        assert result["ok"] is True
        assert result["zapier_notified"] is False
        mock_zapier_status.assert_called_once_with("abc-123", False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestCancelPickupFlow -v`
Expected: FAIL — `ImportError: cannot import name 'cancel_pickup_flow'`

- [ ] **Step 3: Implement `cancel_pickup_flow` and `send_cancellation_notification`**

Add to `backend/app/core/pickup.py`, at the end of the file:

```python
from .pickup_store import get_pickup, cancel_pickup, update_zapier_status


def send_cancellation_notification(pickup_record: dict, reason: str | None) -> bool:
    """Build cancellation Zapier payload and POST to webhook. Returns True if successful."""
    zapier_url = get_secret("zapier", "webhook_url")
    if not zapier_url:
        logger.warning("No Zapier webhook URL configured — cancellation notification skipped")
        return False

    payload = _build_zapier_payload(pickup_record, "cancellation")
    try:
        resp = requests.post(zapier_url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        logger.error("Zapier cancellation webhook HTTP %s", resp.status_code)
        return False
    except requests.exceptions.RequestException as e:
        logger.error("Zapier cancellation webhook error: %s", e)
        return False


def cancel_pickup_flow(pickup_id: str, reason: str | None) -> dict:
    """Orchestrate pickup cancellation: validate → cancel → notify.

    Returns a result dict with ok, message, zapier_notified, and optionally status_code for errors.
    """
    from zoneinfo import ZoneInfo

    # Step 1: Fetch and validate
    record = get_pickup(pickup_id)
    if record is None:
        return {"ok": False, "status_code": 404, "message": "Ritiro non trovato"}

    if record.get("pickup_status") == "cancelled":
        return {"ok": False, "status_code": 409, "message": "Pickup già annullato"}

    # Date check — Europe/Rome timezone
    rome = ZoneInfo("Europe/Rome")
    today_rome = datetime.now(rome).date()
    pickup_date = date.fromisoformat(record["pickup_date"])
    if pickup_date < today_rome:
        return {"ok": False, "status_code": 422, "message": "Non è possibile annullare un ritiro passato"}

    # Step 2: Atomic conditional update
    logger.info("Cancelling pickup %s (carrier=%s, date=%s, reason=%s)",
                pickup_id, record["carrier"], record["pickup_date"], reason)
    cancelled_record = cancel_pickup(pickup_id, reason)
    if cancelled_record is None:
        # Race condition — another request cancelled it first
        return {"ok": False, "status_code": 409, "message": "Pickup già annullato"}

    # Step 3: Notify via Zapier
    zapier_notified = send_cancellation_notification(cancelled_record, reason)

    # Step 4: Persist notification status
    update_zapier_status(pickup_id, zapier_notified)

    if not zapier_notified:
        logger.error("Zapier notification failed for pickup %s cancellation", pickup_id)

    return {
        "ok": True,
        "message": "Ritiro annullato" if zapier_notified else "Ritiro annullato, ma notifica non inviata",
        "zapier_notified": zapier_notified,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/test_core/test_pickup.py::TestCancelPickupFlow -v`
Expected: PASS

- [ ] **Step 5: Run ALL backend tests to check for regressions**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/pickup.py backend/tests/test_core/test_pickup.py
git commit -m "feat: add cancel_pickup_flow and send_cancellation_notification"
```

---

### Task 6: Router Endpoint

**Files:**
- Modify: `backend/app/routers/pickup.py`

- [ ] **Step 1: Add the cancel endpoint**

Add these imports at the top of `backend/app/routers/pickup.py`:

```python
from fastapi.responses import JSONResponse
from ..schemas.pickup import PickupRequest, CancelPickupRequest
from ..core.pickup import send_pickup_request, cancel_pickup_flow
```

(Replace the existing `from ..schemas.pickup import PickupRequest` and `from ..core.pickup import send_pickup_request` lines.)

Add this route **after** the existing `/pickup/history` route (to avoid `{pickup_id}` capturing literal paths):

```python
@router.post("/pickup/{pickup_id}/cancel")
@limiter.limit("30/hour")
async def cancel_pickup_request(request: Request, pickup_id: str, body: CancelPickupRequest):
    result = await asyncio.to_thread(cancel_pickup_flow, pickup_id, body.reason)

    if not result["ok"]:
        status_code = result.get("status_code", 500)
        return JSONResponse(
            status_code=status_code,
            content={"ok": False, "error": {"code": "CANCEL_ERROR", "message": result["message"]}},
        )

    return {
        "ok": True,
        "data": {
            "message": result["message"],
            "zapier_notified": result["zapier_notified"],
        },
    }
```

- [ ] **Step 2: Verify the server starts without errors**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -c "from backend.app.routers.pickup import router; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/pickup.py
git commit -m "feat: add POST /pickup/{pickup_id}/cancel endpoint"
```

---

### Task 7: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update `PickupRecord` type**

In `frontend/src/lib/types.ts`, add three fields to the `PickupRecord` interface after `confirmation_id` (line 251):

```typescript
  cancelled_at: string | null
  cancellation_reason: string | null
  zapier_notified: boolean | null
```

- [ ] **Step 2: Add `CancelPickupResponse` type**

In `frontend/src/lib/types.ts`, add after `PickupListResponse`:

```typescript
export interface CancelPickupResponse {
  message: string
  zapier_notified: boolean
}
```

- [ ] **Step 3: Add `cancelPickup` to API client**

In `frontend/src/api/client.ts`, add at the end after `createBrand`:

```typescript
export async function cancelPickup(
  pickupId: string,
  reason?: string | null
): Promise<CancelPickupResponse> {
  return api.post<CancelPickupResponse>(`/api/v1/pickup/${pickupId}/cancel`, { reason: reason ?? null })
}
```

Add the import at the top:

```typescript
import type { ConfirmRequest, CancelPickupResponse } from "@/lib/types"
```

(Replace the existing `import type { ConfirmRequest } from "@/lib/types"` line.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/api/client.ts
git commit -m "feat: add cancellation types and cancelPickup API function"
```

---

### Task 8: `useCancelPickup` Hook

**Files:**
- Modify: `frontend/src/hooks/usePickupHistory.ts`

- [ ] **Step 1: Add the mutation hook**

In `frontend/src/hooks/usePickupHistory.ts`, add after the existing `useInvalidatePickupHistory`:

```typescript
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query"
import { api } from "@/api/client"
import { cancelPickup } from "@/api/client"
import type { PickupListResponse, CancelPickupResponse } from "@/lib/types"
```

(Replace the existing imports at the top.)

Then add:

```typescript
/** Mutation hook for cancelling a pickup. Invalidates history cache on success. */
export function useCancelPickup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ pickupId, reason }: { pickupId: string; reason?: string | null }) =>
      cancelPickup(pickupId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [PICKUPS_KEY] })
    },
  })
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/usePickupHistory.ts
git commit -m "feat: add useCancelPickup mutation hook"
```

---

### Task 9: `CancelPickupDialog` Component

**Files:**
- Create: `frontend/src/components/CancelPickupDialog.tsx`

- [ ] **Step 1: Create the dialog component**

```typescript
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { formatDateIT } from "@/lib/utils"
import type { PickupRecord } from "@/lib/types"

interface CancelPickupDialogProps {
  pickup: PickupRecord
  isLoading: boolean
  onConfirm: (reason: string | null) => void
  onClose: () => void
}

export function CancelPickupDialog({ pickup, isLoading, onConfirm, onClose }: CancelPickupDialogProps) {
  const [reason, setReason] = useState("")

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Dialog */}
      <div className="relative bg-background border border-border rounded-xl shadow-lg px-6 py-5 w-full max-w-md mx-4">
        <h3 className="text-base font-semibold">Annulla ritiro</h3>
        <p className="text-sm text-muted-foreground mt-1">
          {pickup.carrier} — {formatDateIT(pickup.pickup_date)} — {pickup.company}
        </p>

        <div className="mt-4">
          <label className="block text-sm text-muted-foreground mb-1.5">
            Motivo (opzionale)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value.slice(0, 500))}
            placeholder="Es. cambio data, ordine annullato..."
            className="w-full border border-border rounded-lg px-3 py-2 text-sm resize-y min-h-[60px] bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
            disabled={isLoading}
          />
          <p className="text-xs text-muted-foreground mt-1 text-right">
            {reason.length}/500
          </p>
        </div>

        <div className="flex gap-2 justify-end mt-4">
          <Button variant="outline" size="sm" onClick={onClose} disabled={isLoading}>
            Indietro
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => onConfirm(reason.trim() || null)}
            disabled={isLoading}
          >
            {isLoading ? "Annullamento..." : "Conferma annullamento"}
          </Button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/CancelPickupDialog.tsx
git commit -m "feat: add CancelPickupDialog component"
```

---

### Task 10: Update `PickupHistory` — Cancel Button + STATUS_LABELS + Dimmed Row

**Files:**
- Modify: `frontend/src/components/PickupHistory.tsx`

- [ ] **Step 1: Add `cancelled` to `STATUS_LABELS`**

In `PickupHistory.tsx`, add to the `STATUS_LABELS` object (after the `rejected` entry on line 19):

```typescript
  cancelled: { label: "Annullato", color: "bg-slate-100 text-slate-700 border-slate-300" },
```

- [ ] **Step 2: Pass `filter` and cancel handler to `PickupRow`**

Update the `PickupHistory` component to manage cancel dialog state:

Add imports at the top:

```typescript
import { useCancelPickup } from "@/hooks/usePickupHistory"
import { CancelPickupDialog } from "@/components/CancelPickupDialog"
```

Inside the `PickupHistory` function, add state and the mutation:

```typescript
  const [cancelTarget, setCancelTarget] = useState<PickupRecord | null>(null)
  const cancelMutation = useCancelPickup()
```

Add the cancel handler:

```typescript
  const handleCancelConfirm = (reason: string | null) => {
    if (!cancelTarget) return
    cancelMutation.mutate(
      { pickupId: cancelTarget.id, reason },
      {
        onSuccess: () => setCancelTarget(null),
        onError: () => {}, // error shown via cancelMutation.error
      }
    )
  }
```

Update the `PickupRow` call inside the `<tbody>` to pass the filter and cancel callback:

```typescript
  <PickupRow
    key={p.id}
    pickup={p}
    isExpanded={expanded.has(p.id)}
    onToggle={() => toggleExpand(p.id)}
    showCancel={isUpcoming && p.pickup_status !== "cancelled"}
    onCancel={() => setCancelTarget(p)}
  />
```

Add the dialog render at the end of the component return, right before the closing `</div>`:

```typescript
      {cancelTarget && (
        <CancelPickupDialog
          pickup={cancelTarget}
          isLoading={cancelMutation.isPending}
          onConfirm={handleCancelConfirm}
          onClose={() => { setCancelTarget(null); cancelMutation.reset() }}
        />
      )}

      {/* Cancel error banner */}
      {cancelMutation.error && !cancelTarget && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3">
          <p className="text-sm text-red-800">
            {cancelMutation.error instanceof Error ? cancelMutation.error.message : "Errore durante l'annullamento"}
          </p>
        </div>
      )}
```

- [ ] **Step 3: Update `PickupRow` to support cancel button and dimmed styling**

Update the `PickupRow` function signature:

```typescript
function PickupRow({
  pickup: p,
  isExpanded,
  onToggle,
  showCancel,
  onCancel,
}: {
  pickup: PickupRecord
  isExpanded: boolean
  onToggle: () => void
  showCancel: boolean
  onCancel: () => void
}) {
```

Add dimmed styling to the row `<tr>`:

```typescript
      <tr
        onClick={onToggle}
        className={cn(
          "border-b border-border/50 cursor-pointer hover:bg-muted/30 transition-colors",
          p.pickup_status === "cancelled" && "opacity-60"
        )}
      >
```

Add a new `<td>` column for the cancel button (before the chevron column):

```typescript
        <td className="py-2.5">
          {showCancel ? (
            <button
              onClick={(e) => { e.stopPropagation(); onCancel() }}
              className="text-xs px-2.5 py-1 rounded-md bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 transition-colors"
            >
              Annulla
            </button>
          ) : p.pickup_status === "cancelled" ? (
            <span className="text-xs text-muted-foreground">—</span>
          ) : null}
        </td>
```

Update the table header in `PickupHistory` to add the new column (before the chevron `<th>`):

```typescript
                  <th className="pb-2 w-20"></th>
```

Update the expanded row `colSpan` from 6 to 7.

- [ ] **Step 4: Show cancellation reason in expanded details**

In the expanded row details section (right column), add after the notes display:

```typescript
                  {p.pickup_status === "cancelled" && p.cancellation_reason && (
                    <p className="text-muted-foreground mt-1">Motivo annullamento: {p.cancellation_reason}</p>
                  )}
```

- [ ] **Step 5: Verify the frontend builds without errors**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PickupHistory.tsx
git commit -m "feat: add cancel button, STATUS_LABELS, and dimmed row to storico"
```

---

### Task 11: End-to-End Verification

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/alessandrolinardi/Desktop/ELC && python -m pytest backend/tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run frontend build**

Run: `cd /Users/alessandrolinardi/Desktop/ELC/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Manual smoke test**

1. Start the backend: `cd /Users/alessandrolinardi/Desktop/ELC && python -m uvicorn backend.app.main:app --reload`
2. Start the frontend: `cd /Users/alessandrolinardi/Desktop/ELC/frontend && npm run dev`
3. Create a pickup request for tomorrow
4. Go to storico → Prossimi tab
5. Click "Annulla" on the new pickup
6. Confirm with a reason
7. Verify: row dims, badge shows "Annullato", button becomes "—"
8. Expand the row — verify cancellation reason is shown
9. Check Zapier received the cancellation webhook (if configured)

- [ ] **Step 4: Final commit (if any cleanup needed)**

```bash
git add -A
git commit -m "feat: pickup cancellation — complete feature"
```
