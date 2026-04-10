# Freight Request Feature — Design Spec

**Date:** 2026-04-10
**Status:** Approved (rev 2 — addresses review findings)

## Overview

Add a "Richiesta freight" tab to the existing quotazione page, alongside the current "Quotazione automatica" tab. The freight tab lets users upload a shipment file, select a sender address, and submit the request to the team via Zapier. No automated processing — the team handles freight quotes manually.

## Constraints

- No file parsing — the raw file is uploaded to Supabase Storage and a download URL is sent to Zapier
- No database table storage — fire-and-forget to Zapier (same pattern as pickup creation). Only Supabase Storage is used for the file.
- Reuse existing address book components (`AddressCombobox`, `AddressDrawer`)
- Same file types as auto-quote: `.xlsx`, `.xls`, `.csv` (max 50MB)
- Notes field is optional (max 500 chars)
- No history of past freight requests — this is fire-and-forget by design. The reference ID in the success banner is the user's only record.

## Frontend UI

### Tab Layout

Two tab pills at the top of `ShipmentsQuotation.tsx` (same pattern as `PickupHistory`):

- **"Quotazione automatica"** — all existing page content, unchanged
- **"Richiesta freight"** — new tab (described below)

**Mount behavior:** Both tabs are always mounted in the DOM. The inactive tab is hidden via CSS (`className="hidden"`) — NOT conditional rendering. This preserves the auto-quote tab's state (job polling, timer, results) when the user switches tabs.

**Address Validator redirect:** When navigating from the Address Validator with `location.state.validatorJobId`, the auto-quote tab must be forced active regardless of which tab was last selected.

### Shared vs Independent State

**Shared** (lives in parent `ShipmentsQuotation`):
- `useAddresses()` hook — address list, loading state
- `selectedAddress` — both tabs use the same selected address
- `drawerOpen` — address drawer open/close

**Independent** (each tab owns its own):
- File selection
- Form state (notes for freight, job state for auto-quote)
- Submission state (loading, success, error)

### Freight Tab Component

Extracted as `FreightRequestTab.tsx` — a separate component to keep `ShipmentsQuotation.tsx` focused. Receives address state as props.

**Props:** `addresses`, `selectedAddress`, `onAddressChange`, `onOpenDrawer`, `addressesLoading`

**Content:**
1. **File upload** — drag-and-drop zone, same style as auto-quote. Accepts `.xlsx`, `.xls`, `.csv` (max 50MB). Rejects empty (0-byte) files.
2. **Address combobox** — own `<AddressCombobox>` instance, connected to shared address state via props
3. **Notes** (optional) — textarea with placeholder "Es. urgente, consegna con sponda...", max 500 chars with counter
4. **Submit button** — "Invia richiesta freight" (full width, primary color)

### After Submission

- **Success:** green banner with "Richiesta inviata al team" + "Riferimento: FRQ-{id}". Form resets (file + notes cleared, address stays selected).
- **Error:** red error message below submit button.

## Backend API

### New endpoint: `POST /api/v1/freight/request`

**Rate limit:** 30/hour

**Input:** `multipart/form-data` with:
- `file` — the Excel/CSV file
- `from_name` — sender name
- `from_company` — sender company
- `from_street1` — sender street
- `from_city` — sender city
- `from_state` — sender province (optional)
- `from_zip` — sender zip (5 digits)
- `from_country` — sender country (default: "IT")
- `from_phone` — sender phone (optional)
- `notes` — optional text (max 500 chars)

**Validation:**
- File must be present and non-empty (>0 bytes) → 422 "File richiesto"
- File extension must be `.xlsx`, `.xls`, or `.csv` → 422 "Formato file non supportato"
- File size ≤ 50MB → 422 "File troppo grande (max 50MB)"
- `from_zip` must be 5 digits (reuse existing validation pattern)
- Required sender fields: `from_name`, `from_company`, `from_street1`, `from_city`, `from_zip` → 422 if missing

**On success:**
1. Generate reference ID: `FRQ-{uuid4().hex[:8]}`
2. Upload file to Supabase Storage bucket `freight-requests` with path `{reference_id}/{filename}`
3. Generate a public/signed download URL for the uploaded file
4. Build Zapier JSON payload with sender address fields + metadata + file download URL
5. POST JSON to `ZAPIER_WEBHOOK_URL`
6. Return `{ ok: true, data: { message: "Richiesta inviata", reference_id: "FRQ-..." } }`

### Supabase Storage

**Bucket:** `freight-requests` (must be created manually in Supabase dashboard before first use)

**File path:** `{reference_id}/{original_filename}` — e.g., `FRQ-a3b7c2d1/spedizioni_aprile.xlsx`

**URL generation:** Use `client.storage.from_("freight-requests").create_signed_url(path, expires_in=604800)` — 7-day signed URL. This gives the team a week to download the file from the Zapier notification.

**Cleanup:** Files naturally expire via signed URL. Optionally add a Supabase Storage lifecycle policy later to auto-delete files older than 30 days. Not required for launch.

### New files

**`backend/app/routers/freight.py`:**
- Single endpoint: `POST /freight/request`
- Thin router — validates input, calls `send_freight_request` from core
- Mounted at `/api/v1` prefix in `main.py`

**`backend/app/core/freight.py`:**
- `upload_freight_file(file_bytes, filename, reference_id) -> str` — uploads to Supabase Storage, returns signed download URL
- `send_freight_request(file_url, filename, reference_id, sender_address, notes) -> tuple[bool, str]` — builds JSON payload, POSTs to Zapier. Returns `(success, message)`.

### Schema

**`backend/app/schemas/freight.py`:**
- `FreightRequestForm` — Pydantic model for sender address fields + notes. Reuses the same zip validation pattern as `ShipmentsQuotationForm`. Notes field: `str | None = None` with max_length=500. Required fields: `from_name`, `from_company`, `from_street1`, `from_city`, `from_zip`.

### Router registration

Add to `backend/app/main.py`:
```python
from .routers import freight
app.include_router(freight.router, prefix="/api/v1")
```

## Zapier Payload

JSON POST to `ZAPIER_WEBHOOK_URL` (same URL as pickup, differentiated by `event_type`):

```json
{
  "event_type": "freight_request",
  "reference_id": "FRQ-a3b7c2d1",
  "subject": "FREIGHT REQUEST - FRQ-a3b7c2d1",
  "timestamp": "10/04/2026 15:30",

  "from_company": "Estée Lauder",
  "from_name": "Estee Lauder",
  "from_street1": "Via Turati 3",
  "from_city": "Milano",
  "from_state": "MI",
  "from_zip": "20121",
  "from_country": "IT",
  "from_phone": "0212345678",

  "notes": "urgente, consegna con sponda",
  "has_notes": true,

  "filename": "spedizioni_aprile.xlsx",
  "file_url": "https://xyz.supabase.co/storage/v1/object/sign/freight-requests/FRQ-a3b7c2d1/spedizioni_aprile.xlsx?token=..."
}
```

The `file_url` is a 7-day signed URL. The team clicks it from the email/Trello card to download the file. The `event_type: "freight_request"` lets Zapier route this differently from pickup creation/cancellation events.

**Timestamp** uses Europe/Rome timezone (consistent with pickup flow).

## Error Handling

| Scenario | HTTP | User-facing message |
|----------|------|---------------------|
| No file / empty file | 422 | "File richiesto" |
| Invalid file type | 422 | "Formato file non supportato" |
| File too large (>50MB) | 422 | "File troppo grande (max 50MB)" |
| Missing required sender fields | 422 | Pydantic validation error |
| Supabase Storage upload fails | 502 | "Errore nel caricamento del file, riprova" |
| Zapier webhook fails | 502 | "Errore nell'invio della richiesta, riprova" |
| No Zapier URL configured | 502 | "Webhook non configurato" |
| Server/network error | 5xx | Generic error |

Frontend shows errors inline below the submit button. On success, green banner with reference ID, form resets (file + notes cleared, address stays).

## Frontend API Client

Add to `frontend/src/api/client.ts`:
```typescript
export async function submitFreightRequest(formData: FormData): Promise<FreightRequestResponse> {
  return api.postForm<FreightRequestResponse>("/api/v1/freight/request", formData)
}
```

Add to `frontend/src/lib/types.ts`:
```typescript
export interface FreightRequestResponse {
  message: string
  reference_id: string
}
```

## Testing

### Backend unit tests (`test_freight.py`)

**Core flow:**
- Successful freight request — file uploaded to Storage, Zapier receives payload with correct fields including `file_url`
- Reference ID format: starts with "FRQ-", 12 chars total
- Timestamp uses Europe/Rome timezone

**File validation:**
- Missing file → 422
- Empty file (0 bytes) → 422
- Invalid file extension → 422
- File at 50MB boundary

**Sender validation:**
- Missing required sender fields (`from_name`, `from_company`, etc.) → 422
- `from_zip` not 5 digits → 422

**Notes validation:**
- Notes at max length (500 chars) — accepted
- Notes exceeding 500 chars → rejected
- Null notes — accepted

**Error paths:**
- Supabase Storage upload failure → 502
- Zapier failure → 502 with error message
- Zapier failure after successful Storage upload — file is still uploaded (no rollback needed, it's just a file)

### Frontend tests
- Tab switching: both tabs remain mounted, states independent
- Address Validator redirect forces auto-quote tab active
- Auto-quote job polling continues while freight tab is active
- File upload shows filename, rejects empty files
- Address combobox works identically to auto-quote tab (shared state)
- Submit sends correct FormData
- Success banner shows reference ID
- Error displays inline
- Form resets on success (file + notes cleared, address stays)
