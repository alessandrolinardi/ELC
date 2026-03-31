# Crisp → Trello Ticket Integration

## Problem

The ELC team uses Crisp for live chat support. When a user sends a message, the team needs a Trello card created automatically so nothing falls through the cracks. Crisp's native integrations (webhooks, Zapier app, REST API) require the Pro plan ($25/month). We need this on the free tier.

## Solution

Use Crisp's free client-side JavaScript event (`message:sent`) to detect when a user sends their first message in a page session. The frontend POSTs the message and current page to the ELC backend, which fires a Zapier catch hook to create a Trello card.

## Data Flow

```
User types message in Crisp widget → hits Send
  ↓
Crisp widget fires client-side JS event: $crisp "message:sent"
  ↓
React hook (useCrispTicket) catches the event
  ↓
Check dedup flag for current page path
  ↓ (first message only)
POST /api/v1/support/ticket
  body: { message, page }
  ↓
Backend validates, POSTs to Zapier catch hook
  payload: { message, page, category, timestamp }
  ↓
Zapier creates Trello card
  title: "[{category}] {first 50 chars of message}"
  description: full message + "Inviato da: {page}"
  ↓
Backend returns success → frontend sets dedup flag + shows toast
```

## Components

### 1. Frontend: `useCrispTicket` hook

**File:** `frontend/src/hooks/useCrispTicket.ts`

**Responsibilities:**
- Register Crisp `message:sent` event listener on mount
- Track dedup flag per page path (React ref, resets on path change)
- On first message for current page: POST to backend
- On success: set dedup flag, show toast "Il team è stato notificato" (5s)
- On failure: don't set flag, auto-retry once after 2s
- Log events in dev mode (`?dev=1`)
- Cleanup event listener on unmount

**Dedup logic:**
- `useRef<string | null>(null)` stores the page path that already triggered a ticket
- On `message:sent`: if `ref.current === location.pathname`, skip
- On success: `ref.current = location.pathname`
- On navigation (pathname change): ref resets to `null` via `useEffect`

**Toast:**
- Small fixed-position banner below the Crisp widget area (bottom-right, above the chat bubble)
- "Il team è stato notificato" with a subtle green background
- Auto-dismiss after 5 seconds
- CSS-only animation (fade in/out), no toast library needed

### 2. Frontend: Hook integration

**File:** `frontend/src/App.tsx`

Call `useCrispTicket()` at the App level so it's active on all pages. The hook is self-contained — no props, no UI except the toast.

### 3. Backend: `POST /api/v1/support/ticket`

**File:** `backend/app/routers/support.py` (new)

**Request:**
```json
{
  "message": "Non riesco a scaricare il file corretto",
  "page": "/validator"
}
```

**Validation:**
- `message`: required, 1-2000 chars
- `page`: optional string, max 100 chars

**Logic:**
- Map page path to Italian category label (same PAGE_CATEGORIES map as before)
- Build Zapier payload: `{message, page, category, timestamp}`
- POST to `SUPPORT_ZAPIER_URL` env var (Zapier catch hook)
- Use `run_in_executor` (non-blocking)
- Rate limit: 10/hour

**Response:**
```json
{"ok": true, "data": {"sent": true, "category": "Validator"}}
```

**Error handling:**
- Missing `SUPPORT_ZAPIER_URL` → 503
- Zapier returns non-2xx → 502
- Network error → 502

### 4. Config

**File:** `backend/app/config.py`

Add: `support_zapier_url: str = ""`

Separate from the existing `zapier_webhook_url` (used by pickups). Independent Zap, independent automation.

## Edge Cases

| Scenario | Behavior |
|---|---|
| User sends 5 messages on /validator | 1 Trello card (first message only) |
| User navigates /validator → /pickup, sends on both | 2 Trello cards (one per page) |
| User refreshes page, sends again | New card (ref resets on refresh) |
| Backend is down | No dedup flag set, next message retries |
| POST fails, auto-retry succeeds | 1 card created, flag set on retry success |
| POST fails twice | No card, no flag — next user message retries |
| Zapier is down | Backend returns 502, no flag set, retries on next message |
| User has JS blocked | No Crisp widget, no hook — not a concern |
| Dev mode active | Console logs: "Crisp ticket: posting...", "Crisp ticket: success/failed" |

## What This Does NOT Do

- Does not read Crisp conversations server-side (requires Pro)
- Does not sync Trello responses back to Crisp (out of scope)
- Does not distinguish urgent vs normal (Crisp is the live channel; everything is "normal" — if they need urgency, they say it in the message)
- Does not store ticket history in Supabase (Trello is the system of record)

## Files to Create/Modify

| File | Action |
|---|---|
| `frontend/src/hooks/useCrispTicket.ts` | Create — hook + toast |
| `frontend/src/App.tsx` | Modify — add `useCrispTicket()` call |
| `backend/app/routers/support.py` | Create — ticket endpoint |
| `backend/app/main.py` | Modify — register support router |
| `backend/app/config.py` | Modify — add `support_zapier_url` |

## Verification

1. Open the tool, send a message in Crisp
2. Check Zapier catch hook received the payload
3. Verify Trello card created with correct title/description/category
4. Send another message on the same page — no second card
5. Navigate to a different page, send a message — new card
6. Refresh the page, send a message — new card
7. Dev mode: verify console logs appear
8. Kill the backend, send a message — no card, no flag set. Restart backend, send another message — card created
