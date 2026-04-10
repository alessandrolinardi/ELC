# Freight Request — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Richiesta freight" tab to the quotazione page that lets users upload a shipment file and submit it to the team via Zapier, with the file stored in Supabase Storage.

**Architecture:** New `FreightRequestTab` component in the frontend, thin `freight.py` router + core in the backend. File uploads to Supabase Storage, signed download URL sent in JSON payload to Zapier. Both tabs stay mounted via CSS `hidden` to preserve auto-quote state.

**Tech Stack:** Python/FastAPI, Supabase Storage, React/TypeScript, React Query, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-10-freight-request-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/schemas/freight.py` | `FreightRequestForm` Pydantic model |
| Create | `backend/app/core/freight.py` | Upload to Storage, build payload, send to Zapier |
| Create | `backend/app/routers/freight.py` | `POST /freight/request` endpoint |
| Modify | `backend/app/main.py:91-100` | Register freight router |
| Create | `backend/tests/test_core/test_freight.py` | Backend unit tests |
| Modify | `frontend/src/lib/types.ts` | Add `FreightRequestResponse` |
| Modify | `frontend/src/api/client.ts` | Add `submitFreightRequest` function |
| Create | `frontend/src/components/FreightRequestTab.tsx` | Freight form component |
| Modify | `frontend/src/pages/ShipmentsQuotation.tsx` | Add tab layout, mount both tabs |

---

### Task 1: Backend Schema

**Files:**
- Create: `backend/app/schemas/freight.py`

- [ ] **Step 1: Create the schema file**

```python
"""Pydantic schemas for Freight Request endpoint."""
from pydantic import BaseModel, field_validator
from typing import Optional


class FreightRequestForm(BaseModel):
    """Sender address fields submitted alongside the freight file."""
    from_name: str
    from_company: str
    from_street1: str
    from_city: str
    from_state: str = ""
    from_zip: str
    from_country: str = "IT"
    from_phone: str = ""
    notes: Optional[str] = None

    @field_validator("from_zip")
    @classmethod
    def validate_zip(cls, v):
        if not v.isdigit() or len(v) != 5:
            raise ValueError("CAP must be 5 digits")
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes_length(cls, v):
        if v is not None and len(v) > 500:
            raise ValueError("Le note non possono superare 500 caratteri")
        return v
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/freight.py
git commit -m "feat: add FreightRequestForm schema"
```

---

### Task 2: Core Business Logic — Supabase Storage + Zapier

**Files:**
- Create: `backend/app/core/freight.py`
- Create: `backend/tests/test_core/test_freight.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_core/test_freight.py`:

```python
"""Tests for app.core.freight — upload_freight_file, send_freight_request."""
import uuid
from unittest.mock import patch, MagicMock

from app.core.freight import upload_freight_file, send_freight_request, generate_reference_id


class TestGenerateReferenceId:
    def test_format(self):
        ref = generate_reference_id()
        assert ref.startswith("FRQ-")
        assert len(ref) == 12  # "FRQ-" + 8 hex chars

    def test_unique(self):
        ids = {generate_reference_id() for _ in range(100)}
        assert len(ids) == 100


class TestUploadFreightFile:
    @patch("app.core.freight.get_supabase_client")
    def test_returns_signed_url(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        # Mock upload
        mock_client.storage.from_.return_value.upload.return_value = None
        # Mock signed URL
        mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://xyz.supabase.co/storage/v1/object/sign/freight-requests/FRQ-abc12345/test.xlsx?token=abc"
        }

        url = upload_freight_file(b"fake-file-content", "test.xlsx", "FRQ-abc12345")
        assert "supabase.co" in url
        assert "FRQ-abc12345" in url
        mock_client.storage.from_.assert_called_with("freight-requests")

    @patch("app.core.freight.get_supabase_client")
    def test_raises_on_client_none(self, mock_client_fn):
        mock_client_fn.return_value = None
        try:
            upload_freight_file(b"content", "test.xlsx", "FRQ-abc12345")
            assert False, "Should have raised"
        except Exception as e:
            assert "unavailable" in str(e).lower()


class TestSendFreightRequest:
    SENDER = {
        "from_name": "Mario Rossi",
        "from_company": "Acme Srl",
        "from_street1": "Via Roma 1",
        "from_city": "Milano",
        "from_state": "MI",
        "from_zip": "20121",
        "from_country": "IT",
        "from_phone": "0212345678",
    }

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_successful_request(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, message = send_freight_request(
            file_url="https://storage.example.com/file.xlsx",
            filename="shipments.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes="urgente",
        )
        assert success is True
        assert "inviata" in message.lower()

        # Verify payload
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["event_type"] == "freight_request"
        assert payload["reference_id"] == "FRQ-abc12345"
        assert payload["subject"] == "FREIGHT REQUEST - FRQ-abc12345"
        assert payload["file_url"] == "https://storage.example.com/file.xlsx"
        assert payload["filename"] == "shipments.xlsx"
        assert payload["from_company"] == "Acme Srl"
        assert payload["notes"] == "urgente"
        assert payload["has_notes"] is True

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_null_notes(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        success, _ = send_freight_request(
            file_url="https://example.com/f.xlsx",
            filename="f.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes=None,
        )
        assert success is True
        payload = mock_post.call_args[1]["json"]
        assert payload["has_notes"] is False
        assert payload["notes"] == ""

    @patch("app.core.freight.requests.post", side_effect=Exception("connection error"))
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_zapier_failure(self, mock_secret, mock_post):
        success, message = send_freight_request(
            file_url="https://example.com/f.xlsx",
            filename="f.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes=None,
        )
        assert success is False

    @patch("app.core.freight.get_secret", return_value=None)
    def test_no_webhook_url(self, mock_secret):
        success, message = send_freight_request(
            file_url="https://example.com/f.xlsx",
            filename="f.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes=None,
        )
        assert success is False
        assert "configurato" in message.lower()

    @patch("app.core.freight.requests.post")
    @patch("app.core.freight.get_secret", return_value="https://hooks.zapier.com/test")
    def test_timestamp_has_rome_timezone_format(self, mock_secret, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        send_freight_request(
            file_url="https://example.com/f.xlsx",
            filename="f.xlsx",
            reference_id="FRQ-abc12345",
            sender_address=self.SENDER,
            notes=None,
        )
        payload = mock_post.call_args[1]["json"]
        # Timestamp should be dd/mm/yyyy HH:MM format
        import re
        assert re.match(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", payload["timestamp"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alessandrolinardi/Desktop/Workspace/madmoon/elc && python3 -m pytest backend/tests/test_core/test_freight.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.freight'`

- [ ] **Step 3: Implement `freight.py`**

Create `backend/app/core/freight.py`:

```python
"""Freight request business logic — upload file to Supabase Storage, notify via Zapier."""
import uuid
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from .config_compat import get_secret, get_supabase_client
from .logging_config import get_logger

logger = get_logger(__name__)

STORAGE_BUCKET = "freight-requests"
SIGNED_URL_EXPIRY = 604800  # 7 days in seconds


def generate_reference_id() -> str:
    """Generate a unique freight request reference ID."""
    return f"FRQ-{uuid.uuid4().hex[:8]}"


def upload_freight_file(file_bytes: bytes, filename: str, reference_id: str) -> str:
    """Upload file to Supabase Storage and return a signed download URL.

    Raises Exception on failure.
    """
    client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client unavailable")

    path = f"{reference_id}/{filename}"
    try:
        client.storage.from_(STORAGE_BUCKET).upload(path, file_bytes)
        result = client.storage.from_(STORAGE_BUCKET).create_signed_url(path, SIGNED_URL_EXPIRY)
        signed_url = result.get("signedURL") or result.get("signedUrl", "")
        if not signed_url:
            raise RuntimeError(f"No signed URL returned for {path}")
        return signed_url
    except Exception as e:
        logger.exception("Error uploading freight file %s: %s", path, e)
        raise


def send_freight_request(
    file_url: str,
    filename: str,
    reference_id: str,
    sender_address: dict,
    notes: Optional[str],
) -> tuple[bool, str]:
    """Build JSON payload and POST to Zapier. Returns (success, message)."""
    zapier_url = get_secret("zapier", "webhook_url")
    if not zapier_url:
        logger.error("No Zapier webhook URL configured for freight request")
        return False, "Webhook non configurato"

    rome = ZoneInfo("Europe/Rome")
    timestamp = datetime.now(rome).strftime("%d/%m/%Y %H:%M")

    payload = {
        "event_type": "freight_request",
        "reference_id": reference_id,
        "subject": f"FREIGHT REQUEST - {reference_id}",
        "timestamp": timestamp,

        "from_name": sender_address.get("from_name", ""),
        "from_company": sender_address.get("from_company", ""),
        "from_street1": sender_address.get("from_street1", ""),
        "from_city": sender_address.get("from_city", ""),
        "from_state": sender_address.get("from_state", ""),
        "from_zip": sender_address.get("from_zip", ""),
        "from_country": sender_address.get("from_country", "IT"),
        "from_phone": sender_address.get("from_phone", ""),

        "notes": notes or "",
        "has_notes": bool(notes),

        "filename": filename,
        "file_url": file_url,
    }

    try:
        resp = requests.post(zapier_url, json=payload, timeout=15)
        if resp.status_code == 200:
            logger.info("Freight request %s sent to Zapier", reference_id)
            return True, "Richiesta inviata"
        logger.error("Zapier freight webhook HTTP %s for %s", resp.status_code, reference_id)
        return False, f"Errore nell'invio della richiesta (HTTP {resp.status_code})"
    except requests.exceptions.RequestException as e:
        logger.error("Zapier freight webhook error for %s: %s", reference_id, e)
        return False, "Errore nell'invio della richiesta, riprova"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/alessandrolinardi/Desktop/Workspace/madmoon/elc && python3 -m pytest backend/tests/test_core/test_freight.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/freight.py backend/tests/test_core/test_freight.py
git commit -m "feat: add freight core — Storage upload + Zapier notification"
```

---

### Task 3: Router Endpoint

**Files:**
- Create: `backend/app/routers/freight.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the router**

Create `backend/app/routers/freight.py`:

```python
"""Freight Request endpoint."""
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from typing import Optional

from ..limiter import limiter
from ..schemas.freight import FreightRequestForm
from ..core.freight import generate_reference_id, upload_freight_file, send_freight_request

router = APIRouter()

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/freight/request")
@limiter.limit("30/hour")
async def create_freight_request(
    request: Request,
    file: UploadFile = File(...),
    from_name: str = Form(...),
    from_company: str = Form(...),
    from_street1: str = Form(...),
    from_city: str = Form(...),
    from_state: str = Form(""),
    from_zip: str = Form(...),
    from_country: str = Form("IT"),
    from_phone: str = Form(""),
    notes: Optional[str] = Form(None),
):
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File richiesto"}
        })

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "Formato file non supportato. Usa .xlsx, .xls o .csv"}
        })

    # Validate sender address via schema
    form = FreightRequestForm(
        from_name=from_name,
        from_company=from_company,
        from_street1=from_street1,
        from_city=from_city,
        from_state=from_state,
        from_zip=from_zip,
        from_country=from_country,
        from_phone=from_phone,
        notes=notes,
    )

    # Read file
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File richiesto"}
        })
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail={
            "ok": False, "error": {"code": "VALIDATION_ERROR", "message": "File troppo grande (max 50MB)"}
        })

    # Generate reference ID
    reference_id = generate_reference_id()

    # Upload to Supabase Storage
    try:
        file_url = await asyncio.to_thread(
            upload_freight_file, file_bytes, file.filename, reference_id
        )
    except Exception:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "STORAGE_ERROR", "message": "Errore nel caricamento del file, riprova"}
        })

    # Send to Zapier
    sender_address = form.model_dump(exclude={"notes"})
    success, message = await asyncio.to_thread(
        send_freight_request, file_url, file.filename, reference_id, sender_address, form.notes
    )

    if not success:
        raise HTTPException(status_code=502, detail={
            "ok": False, "error": {"code": "WEBHOOK_ERROR", "message": message}
        })

    return {
        "ok": True,
        "data": {
            "message": "Richiesta inviata",
            "reference_id": reference_id,
        },
    }
```

- [ ] **Step 2: Register the router in `main.py`**

In `backend/app/main.py`, add after the existing router imports (around line 11):

```python
from .routers import freight
```

And add after line 99 (`app.include_router(shipments.router, ...)`):

```python
app.include_router(freight.router, prefix="/api/v1")
```

- [ ] **Step 3: Verify the server starts**

Run: `cd /Users/alessandrolinardi/Desktop/Workspace/madmoon/elc && python3 -c "from backend.app.routers.freight import router; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/freight.py backend/app/main.py
git commit -m "feat: add POST /freight/request endpoint"
```

---

### Task 4: Frontend Types + API Client

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add `FreightRequestResponse` type**

In `frontend/src/lib/types.ts`, add after the `HealthData` interface (around line 288):

```typescript
// --- Freight Request ---

export interface FreightRequestResponse {
  message: string
  reference_id: string
}
```

- [ ] **Step 2: Add `submitFreightRequest` to API client**

In `frontend/src/api/client.ts`, add at the end of the file:

```typescript
export async function submitFreightRequest(formData: FormData): Promise<FreightRequestResponse> {
  return api.postForm<FreightRequestResponse>("/api/v1/freight/request", formData)
}
```

Add to the existing import at the top of `client.ts`:

```typescript
import type { ConfirmRequest, CancelPickupResponse, FreightRequestResponse } from "@/lib/types"
```

(Replace the existing import line.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/api/client.ts
git commit -m "feat: add FreightRequestResponse type and submitFreightRequest client"
```

---

### Task 5: FreightRequestTab Component

**Files:**
- Create: `frontend/src/components/FreightRequestTab.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { submitFreightRequest } from "@/api/client"
import { FileDropZone } from "@/components/FileDropZone"
import { AddressCombobox } from "@/components/AddressCombobox"
import { Button } from "@/components/ui/button"
import type { Address, FreightRequestResponse } from "@/lib/types"
import type { ManualAddressData } from "@/components/AddressCombobox"

interface FreightRequestTabProps {
  addresses: Address[]
  selectedAddress: Address | null
  onAddressSelect: (addr: Address) => void
  onManualEntry: (data: ManualAddressData) => void
  onOpenDrawer: () => void
  onSaveAndUse: (data: { name: string; company: string; contact_name?: string; street: string; zip_code: string; city: string; province?: string; phone?: string; reference?: string; is_default?: boolean }) => void
  addressesLoading: boolean
}

export function FreightRequestTab({
  addresses,
  selectedAddress,
  onAddressSelect,
  onManualEntry,
  onOpenDrawer,
  onSaveAndUse,
  addressesLoading,
}: FreightRequestTabProps) {
  const [file, setFile] = useState<File | null>(null)
  const [notes, setNotes] = useState("")
  const [successResult, setSuccessResult] = useState<FreightRequestResponse | null>(null)

  const mutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("File richiesto")
      if (!selectedAddress) throw new Error("Seleziona un indirizzo mittente")

      const formData = new FormData()
      formData.append("file", file)
      formData.append("from_name", selectedAddress.contact_name || selectedAddress.company || selectedAddress.name)
      formData.append("from_company", selectedAddress.company || "")
      formData.append("from_street1", selectedAddress.street)
      formData.append("from_city", selectedAddress.city)
      if (selectedAddress.province) formData.append("from_state", selectedAddress.province)
      formData.append("from_zip", selectedAddress.zip)
      formData.append("from_country", "IT")
      formData.append("from_phone", selectedAddress.phone || "")
      if (notes.trim()) formData.append("notes", notes.trim())

      return submitFreightRequest(formData)
    },
    onSuccess: (data) => {
      setSuccessResult(data)
      setFile(null)
      setNotes("")
    },
  })

  return (
    <div className="space-y-6">
      {/* Success banner */}
      {successResult && (
        <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-5 py-4">
          <p className="text-sm font-semibold text-emerald-800">Richiesta inviata al team</p>
          <p className="text-sm text-emerald-700 mt-1">Riferimento: {successResult.reference_id}</p>
        </div>
      )}

      {/* File upload */}
      <FileDropZone
        label="File spedizioni freight"
        subtitle="Excel o CSV con dettagli spedizioni"
        accept=".xlsx,.xls,.csv"
        icon="📦"
        onFilesSelected={(files) => { setFile(files[0] || null); setSuccessResult(null) }}
        selectedFiles={file ? [file] : []}
      />

      {/* Address */}
      <div className="elc-card">
        <div className="flex items-center justify-between mb-4">
          <label className="text-sm font-semibold text-foreground">Indirizzo mittente</label>
        </div>
        <AddressCombobox
          addresses={addresses}
          selectedAddress={selectedAddress}
          onSelect={onAddressSelect}
          onManualEntry={onManualEntry}
          onOpenDrawer={onOpenDrawer}
          onSaveAndUse={onSaveAndUse}
          isLoading={addressesLoading}
        />
      </div>

      {/* Notes */}
      <div className="elc-card">
        <label className="block text-sm font-semibold text-foreground mb-2">Note (opzionale)</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 500))}
          placeholder="Es. urgente, consegna con sponda..."
          className="w-full border border-border rounded-lg px-3 py-2 text-sm resize-y min-h-[60px] bg-background focus:outline-none focus:ring-2 focus:ring-primary/20"
          disabled={mutation.isPending}
        />
        <p className="text-xs text-muted-foreground mt-1 text-right">{notes.length}/500</p>
      </div>

      {/* Submit */}
      <Button
        onClick={() => mutation.mutate()}
        disabled={!file || !selectedAddress || mutation.isPending}
        className="bg-primary hover:bg-primary/90 text-white w-full"
      >
        {mutation.isPending ? "Invio in corso..." : "Invia richiesta freight"}
      </Button>

      {/* Error */}
      {mutation.error && (
        <p className="text-sm text-destructive text-center">
          {mutation.error instanceof Error ? mutation.error.message : "Errore durante l'invio"}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/FreightRequestTab.tsx
git commit -m "feat: add FreightRequestTab component"
```

---

### Task 6: Update ShipmentsQuotation — Tab Layout

**Files:**
- Modify: `frontend/src/pages/ShipmentsQuotation.tsx`

This is the most delicate frontend task. The existing page content becomes the "Quotazione automatica" tab, and the new `FreightRequestTab` is the second tab. Both tabs stay mounted (CSS `hidden`).

- [ ] **Step 1: Add imports**

Add at the top of `ShipmentsQuotation.tsx`:

```typescript
import { FreightRequestTab } from "@/components/FreightRequestTab"
```

- [ ] **Step 2: Add tab state**

Inside the `ShipmentsQuotation` function, after the existing state declarations (after line 39), add:

```typescript
  const [activeTab, setActiveTab] = useState<"auto" | "freight">("auto")
```

- [ ] **Step 3: Force auto-quote tab on Address Validator redirect**

In the existing `useEffect` that handles `location.state.validatorJobId` (around line 92-125), add at the start of the effect body (after `if (!validatorJobId) return`):

```typescript
    setActiveTab("auto")
```

- [ ] **Step 4: Add tab pills and wrap content**

Replace the return statement's content. The structure becomes:

```typescript
  return (
    <PageShell title="Quotazione Spedizioni" subtitle="Carica un file Excel per ottenere tariffe da DHL, UPS e FedEx.">
      {/* Tab pills */}
      <div className="flex gap-2 mb-6">
        {([
          { key: "auto" as const, label: "Quotazione automatica" },
          { key: "freight" as const, label: "Richiesta freight" },
        ]).map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1 text-sm font-medium rounded-md transition-colors ${
              activeTab === tab.key
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-muted"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Auto-quote tab — existing content */}
      <div className={activeTab !== "auto" ? "hidden" : ""}>
        <div className="space-y-6">
          {/* ... ALL existing content from the current return statement ... */}
          {/* Everything from the {!quotationResult && (...)} block */}
          {/* through the {quotationResult && (...)} block */}
        </div>
      </div>

      {/* Freight tab */}
      <div className={activeTab !== "freight" ? "hidden" : ""}>
        <FreightRequestTab
          addresses={addresses}
          selectedAddress={selectedAddress}
          onAddressSelect={selectAddress}
          onManualEntry={handleManualEntry}
          onOpenDrawer={() => setDrawerOpen(true)}
          onSaveAndUse={handleSaveAndUse}
          addressesLoading={addressesLoading}
        />
      </div>

      {/* Address drawer — shared, outside tabs */}
      <AddressDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        addresses={addresses}
        onAdd={async (data) => { await createAddress(data) }}
        onUpdate={async (id, data) => { await updateAddress({ id, data }) }}
        onDelete={async (id) => {
          await deleteAddress(id)
          if (selectedAddress?.id === id) setSelectedAddress(null)
        }}
        onSetDefault={async (id) => { await setDefault(id) }}
      />
    </PageShell>
  )
```

**Key points:**
- The existing `<div className="space-y-6">` content (lines 229-378) moves inside the auto-quote tab div
- The `<AddressDrawer>` stays OUTSIDE both tabs (it's a drawer/overlay, shared)
- Both tabs use `className="hidden"` for the inactive one — NOT conditional rendering
- `cn()` import is already available; or use template literals as shown

- [ ] **Step 5: Verify frontend builds**

Run: `cd /Users/alessandrolinardi/Desktop/Workspace/madmoon/elc/frontend && npx tsc --noEmit`
Expected: No TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ShipmentsQuotation.tsx
git commit -m "feat: add tab layout to quotazione page with freight request tab"
```

---

### Task 7: Create Supabase Storage Bucket

This is a manual step — create the `freight-requests` bucket in the Supabase dashboard.

- [ ] **Step 1: Create the bucket**

Go to Supabase Dashboard → Storage → New Bucket:
- Name: `freight-requests`
- Public: No (private — we use signed URLs)
- File size limit: 50MB

---

### Task 8: End-to-End Verification

- [ ] **Step 1: Run all backend tests**

Run: `cd /Users/alessandrolinardi/Desktop/Workspace/madmoon/elc && python3 -m pytest backend/tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run frontend build**

Run: `cd /Users/alessandrolinardi/Desktop/Workspace/madmoon/elc/frontend && npx tsc --noEmit`
Expected: No TypeScript errors.

- [ ] **Step 3: Manual smoke test**

1. Open the app → Quotazione page
2. Verify two tabs: "Quotazione automatica" and "Richiesta freight"
3. Auto-quote tab should work exactly as before
4. Switch to freight tab — file upload, address selector, notes field visible
5. Upload a test Excel file, select address, add a note, submit
6. Verify: success banner with reference ID
7. Check Zapier received the payload with `event_type: "freight_request"` and `file_url`
8. Click the `file_url` — should download the file
9. Switch back to auto-quote tab — verify state is preserved (if a job was running, it still shows)

- [ ] **Step 4: Push**

```bash
git push origin main
```
