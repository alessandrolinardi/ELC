# Freight Request Feature — Design Spec

**Date:** 2026-04-10
**Status:** Approved

## Overview

Add a "Richiesta freight" tab to the existing quotazione page, alongside the current "Quotazione automatica" tab. The freight tab lets users upload a shipment file, select a sender address, and submit the request to the team via Zapier. No automated processing — the team handles freight quotes manually.

## Constraints

- No file parsing — the raw file is forwarded to Zapier as-is
- No database storage — fire-and-forget to Zapier (same pattern as pickup creation)
- Reuse existing address book components (`AddressCombobox`, `AddressDrawer`)
- Same file types as auto-quote: `.xlsx`, `.xls`, `.csv` (max 50MB)
- Notes field is optional (max 500 chars)

## Frontend UI

### Tab Layout

Two tab pills at the top of `ShipmentsQuotation.tsx` (same pattern as `PickupHistory`):

- **"Quotazione automatica"** — all existing page content, unchanged
- **"Richiesta freight"** — new tab (described below)

Tab state is independent — switching tabs does not affect the other tab's form/results.

### Freight Tab Content

1. **File upload** — drag-and-drop zone, same style as auto-quote. Accepts `.xlsx`, `.xls`, `.csv` (max 50MB)
2. **Address combobox** — reuses `AddressCombobox` + `AddressDrawer`, identical to auto-quote tab. Auto-selects default address.
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
- File must be present → 422 "File richiesto"
- File extension must be `.xlsx`, `.xls`, or `.csv` → 422 "Formato file non supportato"
- File size ≤ 50MB → 422 "File troppo grande (max 50MB)"
- `from_zip` must be 5 digits (reuse existing validation pattern)

**On success:**
1. Generate reference ID: `FRQ-{uuid4().hex[:8]}`
2. Build Zapier payload with sender address fields + metadata
3. POST to `ZAPIER_WEBHOOK_URL` as multipart (JSON fields + file attachment)
4. Return `{ ok: true, data: { message: "Richiesta inviata", reference_id: "FRQ-..." } }`

### New files

**`backend/app/routers/freight.py`:**
- Single endpoint: `POST /freight/request`
- Thin router — validates input, calls `send_freight_request` from core
- Mounted at `/api/v1` prefix in `main.py`

**`backend/app/core/freight.py`:**
- `send_freight_request(file_bytes, filename, sender_address, notes) -> tuple[bool, str, str]` — builds payload, generates reference ID, POSTs to Zapier. Returns `(success, message, reference_id)`.

### Schema

**`backend/app/schemas/freight.py`:**
- `FreightRequestForm` — Pydantic model for sender address fields + notes. Reuses the same zip validation pattern as `ShipmentsQuotationForm`. Notes field: `str | None = None` with max_length=500.

### Router registration

Add to `backend/app/main.py`:
```python
from .routers import freight
app.include_router(freight.router, prefix="/api/v1")
```

## Zapier Payload

Multipart POST to `ZAPIER_WEBHOOK_URL` with:

**JSON fields (as form fields, not a JSON body — since we're sending multipart with a file):**
```
event_type: "freight_request"
reference_id: "FRQ-a3b7c2d1"
subject: "FREIGHT REQUEST - FRQ-a3b7c2d1"
timestamp: "10/04/2026 15:30" (Europe/Rome)

from_company: "Estée Lauder"
from_name: "Estee Lauder"
from_street1: "Via Turati 3"
from_city: "Milano"
from_state: "MI"
from_zip: "20121"
from_country: "IT"
from_phone: "0212345678"

notes: "urgente, consegna con sponda"
has_notes: true

filename: "spedizioni_aprile.xlsx"
```

**File part:**
- The uploaded file as a multipart file attachment

The `event_type: "freight_request"` allows Zapier to route this differently from pickup events.

## Error Handling

| Scenario | HTTP | User-facing message |
|----------|------|---------------------|
| No file uploaded | 422 | "File richiesto" |
| Invalid file type | 422 | "Formato file non supportato" |
| File too large (>50MB) | 422 | "File troppo grande (max 50MB)" |
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
- Successful freight request — Zapier receives payload with correct fields
- Reference ID format: starts with "FRQ-", 12 chars total
- Missing file → 422
- Invalid file extension → 422
- Notes at max length (500 chars)
- Notes exceeding 500 chars → rejected
- Zapier failure → 502 with error message
- Timestamp uses Europe/Rome timezone

### Frontend
- Tab switching works, states are independent
- File upload shows filename
- Address combobox works identically to auto-quote tab
- Submit sends correct FormData
- Success banner shows reference ID
- Error displays inline
- Form resets on success (file + notes cleared, address stays)
