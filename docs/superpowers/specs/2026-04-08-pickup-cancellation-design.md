# Pickup Cancellation Feature — Design Spec

**Date:** 2026-04-08
**Status:** Approved (rev 2 — addresses staff eng / architect / QA review)

## Overview

Allow users to cancel upcoming pickups from the storico (history view). Cancelled pickups are soft-deleted — flagged as "cancelled" in the database, not removed. The team is notified via the existing Zapier webhook integration.

## Constraints

- Only upcoming pickups (`pickup_date >= today` in **Europe/Rome** timezone) can be cancelled
- Same-day cancellation is allowed — the pickup date itself is still valid for cancellation
- No carrier API calls — cancellation is internal only, team handles carrier-side manually
- Cancellation reason is optional (max 500 characters)
- Already-cancelled pickups cannot be cancelled again
- Pickups with status `failed` or `rejected` can be cancelled (they were attempted but not collected)

## Timezone Convention

All date comparisons use **Europe/Rome** (CET/CEST) as the reference timezone, matching the user base. `cancelled_at` is stored as UTC `timestamptz` in the database but displayed in Europe/Rome format (`dd/mm/yyyy HH:MM`) in the Zapier payload and frontend.

## Database Changes

Three new nullable columns on `elc_pickups`:

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `cancelled_at` | `timestamptz` | `null` | UTC timestamp of cancellation |
| `cancellation_reason` | `text` | `null` | Max 500 chars, enforced at schema level |
| `zapier_notified` | `boolean` | `null` | `true` if Zapier was notified, `false` if webhook failed, `null` for pre-existing rows |

On cancellation:
- `pickup_status` → `"cancelled"`
- `cancelled_at` → current UTC timestamp
- `cancellation_reason` → user-provided text or `null`
- `zapier_notified` → `true` or `false` depending on webhook outcome

Migration file: `backend/data/supabase_migrations/add_cancellation_fields.sql`

## Backend API

### New endpoint: `POST /api/v1/pickup/{pickup_id}/cancel`

Uses `POST` (not PATCH) because this is an action/command, not a partial field update — consistent with the existing `POST /api/v1/pickup/request` pattern.

**Rate limit:** 30/hour

**Request body:**
```json
{ "reason": "string | null" }
```

**Validation:**
- Pickup must exist → 404 if not
- Pickup must be upcoming (`pickup_date >= today` in Europe/Rome) → 422 "Non è possibile annullare un ritiro passato"
- Pickup must not already be cancelled → 409 "Pickup già annullato"

Note: 422 for business-rule violations (past pickup), 409 for true conflict (already cancelled).

**On success:**
1. Atomically update the record using conditional UPDATE (see Concurrency section)
2. Build Zapier payload using the shared `_build_zapier_payload()` helper
3. POST to `ZAPIER_WEBHOOK_URL`
4. Persist `zapier_notified` result to DB
5. Return `{ success: true, message: "Pickup cancelled", zapier_notified: bool }`

### Concurrency: Atomic Conditional Update

The cancel operation uses a single conditional UPDATE to eliminate race conditions:

```sql
UPDATE elc_pickups
SET pickup_status = 'cancelled',
    cancelled_at = now(),
    cancellation_reason = $reason
WHERE id = $id AND pickup_status != 'cancelled'
RETURNING *
```

If zero rows are returned, the pickup was already cancelled (409). This eliminates the need for a separate fetch-then-validate-then-update sequence. A separate `get_pickup()` call is only needed before the UPDATE for the date validation check.

### New core functions

**`pickup_store.py`:**
- `get_pickup(pickup_id: str) -> dict | None` — fetch a single pickup record by ID (used for date validation before cancel)
- `cancel_pickup(pickup_id: str, reason: str | None) -> dict | None` — atomic conditional update; returns the updated record or `None` if already cancelled
- `update_zapier_status(pickup_id: str, notified: bool)` — persist `zapier_notified` after webhook attempt

**`pickup.py`:**
- `cancel_pickup_flow(pickup_id: str, reason: str | None) -> dict` — orchestrates the full cancellation: validate → cancel → notify → persist notification status. Router calls this single function, matching the `send_pickup_request` pattern for creation.
- `_build_zapier_payload(record: dict, event_type: str) -> dict` — **extracted shared helper** used by both `send_pickup_request` (creation) and `cancel_pickup_flow` (cancellation). Builds the full Zapier payload from a pickup record dict. Cancellation adds `cancellation_reason`, `cancelled_at` fields; creation flow remains unchanged. This prevents payload drift between the two paths.
- `send_cancellation_notification(pickup_record: dict, reason: str | None) -> bool` — calls `_build_zapier_payload` and POSTs to Zapier

**Logging:** All cancellation operations log at `INFO` level (pickup ID, carrier, date, reason) and Zapier failures log at `ERROR` level — matching existing creation flow logging.

### Schema updates

**`schemas/pickup.py`:**
- `CancelPickupRequest` — Pydantic model with `reason: str | None = None` (max_length=500)
- `PickupRecord` — **updated** to include `cancelled_at: str | None`, `cancellation_reason: str | None`, `zapier_notified: bool | None` so cancelled records are returned with full data from `list_pickups`

## Zapier Payload

Uses the same `ZAPIER_WEBHOOK_URL`. Payload follows the existing creation structure with these additions for cancellation:

```json
{
  "event_type": "cancellation",
  "subject": "ANNULLAMENTO - {CARRIER} - {DATE} - {SHIPMENT_TYPE}",
  "cancellation_reason": "string | null",
  "cancelled_at": "dd/mm/yyyy HH:MM (Europe/Rome)",
  // ... all existing pickup fields (carrier, date, address, packages, etc.)
}
```

**`event_type` on creation payloads:** The `"event_type": "creation"` field will be added to creation payloads in a **separate commit deployed first**, before the cancellation feature goes live. This allows verification that existing Zapier Zaps are unaffected by the new field before introducing the cancellation event type. The field is additive (new key, no existing keys changed), so Zaps using field-mapping should be unaffected — but this staged rollout eliminates risk.

## Frontend UI

### TypeScript type updates

`PickupRecord` in `lib/types.ts` must add:
- `cancelled_at: string | null`
- `cancellation_reason: string | null`
- `zapier_notified: boolean | null`

### STATUS_LABELS update

Add `cancelled` entry to the `STATUS_LABELS` map in `PickupHistory.tsx`:
- Label: `"Annullato"`
- Color: amber (`bg-amber-100 text-amber-800`)

### Cancel button

- "Annulla" button appears on each row in the "Prossimi" tab
- Not shown on rows where `pickup_status === "cancelled"`
- Not shown in the "Archivio" tab

### Confirmation dialog

Extracted as a standalone `<CancelPickupDialog>` component for testability and to keep `PickupHistory` focused on display.

Props: `pickup: PickupRecord`, `onSuccess: () => void`, `onClose: () => void`

- Title: "Annulla ritiro"
- Subtitle: "{carrier} — {date} — {company}"
- Optional textarea: "Motivo (opzionale)" with placeholder "Es. cambio data, ordine annullato..." (max 500 chars)
- Buttons: "Indietro" (secondary) and "Conferma annullamento" (red/destructive)

### After cancellation

- Row dims (opacity 0.6)
- Status badge becomes amber "Annullato"
- Cancel button replaced with "—"
- Row stays in "Prossimi" until pickup date passes, then moves to "Archivio" naturally
- Cache invalidated via `useInvalidatePickupHistory()`
- Success toast shown (or warning toast if `zapier_notified: false`)

## Error Handling

| Scenario | HTTP | User-facing message |
|----------|------|---------------------|
| Pickup not found | 404 | Error toast |
| Already cancelled | 409 | "Pickup già annullato" |
| Past pickup | 422 | "Non è possibile annullare un ritiro passato" |
| Zapier fails | 200 | "Ritiro annullato, ma notifica non inviata" (`zapier_notified: false`) |
| Server/network error | 5xx | Generic error toast, row unchanged |

## Testing

### Backend unit tests (`test_pickup.py`)

**Core cancellation:**
- Cancel an upcoming pickup successfully
- Cancel a same-day pickup (boundary: `pickup_date == today` in Europe/Rome)
- Reject cancellation of past pickup
- Reject cancellation of already-cancelled pickup
- Reject cancellation of non-existent pickup
- Cancel a pickup with status `failed` — should succeed
- Cancel a pickup with status `rejected` — should succeed

**Concurrency:**
- Concurrent cancellation — verify atomic UPDATE returns `None` for the second caller

**Reason validation:**
- Cancel with `null` reason
- Cancel with empty string reason
- Cancel with reason at max length (500 chars)
- Reject reason exceeding 500 chars

**Zapier integration:**
- Verify cancellation Zapier payload includes `event_type: "cancellation"`, `cancellation_reason`, `cancelled_at`
- Verify creation Zapier payload includes `event_type: "creation"` (regression test)
- Verify `_build_zapier_payload` produces identical base fields for both event types
- Verify cancellation succeeds and `zapier_notified: false` is persisted when Zapier webhook fails

**Logging:**
- Verify INFO log on successful cancellation
- Verify ERROR log on Zapier webhook failure

### Integration tests
- Full cancel flow through FastAPI test client: POST cancel → verify DB state → verify Zapier POST payload structure

### Frontend
- Cancel button visibility (shown for upcoming non-cancelled, hidden for cancelled/archive)
- `STATUS_LABELS` renders "Annullato" with amber badge for cancelled status
- `<CancelPickupDialog>` opens with correct pickup details pre-filled
- Successful cancellation dims row and updates badge
- Warning toast shown when `zapier_notified: false`
- Error states display correct messages (404, 409, 422)
- Reason textarea enforces 500 char max
