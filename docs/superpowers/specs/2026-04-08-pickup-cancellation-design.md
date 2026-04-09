# Pickup Cancellation Feature — Design Spec

**Date:** 2026-04-08
**Status:** Approved

## Overview

Allow users to cancel upcoming pickups from the storico (history view). Cancelled pickups are soft-deleted — flagged as "cancelled" in the database, not removed. The team is notified via the existing Zapier webhook integration.

## Constraints

- Only upcoming pickups (pickup_date >= today) can be cancelled
- No carrier API calls — cancellation is internal only, team handles carrier-side manually
- Cancellation reason is optional
- Already-cancelled pickups cannot be cancelled again

## Database Changes

Two new nullable columns on `elc_pickups`:

| Column | Type | Default |
|--------|------|---------|
| `cancelled_at` | `timestamptz` | `null` |
| `cancellation_reason` | `text` | `null` |

On cancellation:
- `pickup_status` → `"cancelled"`
- `cancelled_at` → current UTC timestamp
- `cancellation_reason` → user-provided text or `null`

Migration file: `backend/data/supabase_migrations/add_cancellation_fields.sql`

## Backend API

### New endpoint: `PATCH /api/v1/pickup/{pickup_id}/cancel`

**Rate limit:** 30/hour

**Request body:**
```json
{ "reason": "string | null" }
```

**Validation:**
- Pickup must exist → 404 if not
- Pickup must be upcoming (`pickup_date >= today`) → 409 "Non è possibile annullare un ritiro passato"
- Pickup must not already be cancelled → 409 "Pickup già annullato"

**On success:**
1. Update the record in Supabase (`pickup_status`, `cancelled_at`, `cancellation_reason`)
2. Fetch the full updated record
3. Build Zapier payload (full pickup data + cancellation fields)
4. POST to `ZAPIER_WEBHOOK_URL`
5. Return `{ success: true, message: "Pickup cancelled", zapier_notified: bool }`

### New core functions

**`pickup_store.py`:**
- `get_pickup(pickup_id: str) -> dict | None` — fetch a single pickup record by ID
- `cancel_pickup(pickup_id: str, reason: str | None) -> dict` — update `pickup_status`, `cancelled_at`, `cancellation_reason`

**`pickup.py`:**
- `send_cancellation_notification(pickup_record: dict, reason: str | None) -> bool` — build Zapier cancellation payload from the stored record (recomputes `shipment_type` from `num_packages * weight_per_package`, reuses existing payload-building helpers where possible) and POST to Zapier

### New schema

**`schemas/pickup.py`:**
- `CancelPickupRequest` — Pydantic model with `reason: str | None = None`

## Zapier Payload

Uses the same `ZAPIER_WEBHOOK_URL`. Payload follows the existing creation structure with these additions:

```json
{
  "event_type": "cancellation",
  "subject": "ANNULLAMENTO - {CARRIER} - {DATE} - {SHIPMENT_TYPE}",
  "cancellation_reason": "string | null",
  "cancelled_at": "dd/mm/yyyy HH:MM",
  // ... all existing pickup fields (carrier, date, address, packages, etc.)
}
```

The existing creation payload will also get `"event_type": "creation"` added for consistency, so Zapier can filter/route by event type.

## Frontend UI

### Cancel button

- "Annulla" button appears on each row in the "Prossimi" tab
- Not shown on rows where `pickup_status === "cancelled"`
- Not shown in the "Archivio" tab

### Confirmation dialog

- Title: "Annulla ritiro"
- Subtitle: "{carrier} — {date} — {company}"
- Optional textarea: "Motivo (opzionale)" with placeholder "Es. cambio data, ordine annullato..."
- Buttons: "Indietro" (secondary) and "Conferma annullamento" (red/destructive)

### After cancellation

- Row dims (opacity 0.6)
- Status badge becomes amber "cancelled"
- Cancel button replaced with "—"
- Row stays in "Prossimi" until pickup date passes, then moves to "Archivio" naturally
- Cache invalidated via `useInvalidatePickupHistory()`
- Success toast shown (or warning if Zapier notification failed)

## Error Handling

| Scenario | HTTP | User-facing message |
|----------|------|---------------------|
| Pickup not found | 404 | Error toast |
| Already cancelled | 409 | "Pickup già annullato" |
| Past pickup | 409 | "Non è possibile annullare un ritiro passato" |
| Zapier fails | 200 | "Ritiro annullato, ma notifica non inviata" (zapier_notified: false) |
| Server/network error | 5xx | Generic error toast, row unchanged |

## Testing

### Backend unit tests (`test_pickup.py`)
- Cancel an upcoming pickup successfully
- Reject cancellation of past pickup
- Reject cancellation of already-cancelled pickup
- Reject cancellation of non-existent pickup
- Verify Zapier payload includes cancellation fields and `event_type`
- Verify cancellation succeeds even if Zapier webhook fails

### Frontend
- Cancel button visibility (shown for upcoming non-cancelled, hidden otherwise)
- Dialog opens with correct pickup details
- Successful cancellation updates row state
- Error states display correct messages
