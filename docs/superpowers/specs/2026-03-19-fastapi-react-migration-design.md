# ELC Tools — FastAPI + React Migration Spec

## Context

ELC Tools is a Streamlit app for Estée Lauder logistics with 3 features (Label Sorter, Address Validator, Pickup Request) and plans to grow to 6-10+ tools. The Streamlit UI hits fundamental limits: HTML sanitization strips interactive elements, no JavaScript, no real routing, no proper component model. The backend business logic (`src/`) is already cleanly separated and framework-agnostic.

This spec covers migrating from Streamlit to FastAPI (backend) + React/Vite/TypeScript (frontend) while preserving all existing business logic and the Cool Indigo UI design from the earlier UX redesign spec.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | API-first, two separate services | Clean separation, independently deployable |
| Backend | FastAPI + Python 3.11 | Wraps existing Python business logic directly |
| Frontend | React 18 + Vite + TypeScript | Full UI control, type safety, proper routing |
| CSS | Tailwind CSS + shadcn/ui | Matches design tokens, professional components |
| Long operations | Async job pattern with polling | Avoids HTTP timeouts on 1-2 min operations |
| Auth | None (open access) | Current behavior, internal tool |
| Repo structure | Monorepo (backend/ + frontend/) | Single repo, atomic commits |
| Deployment | Two Render services (web + static) | API and frontend deploy independently |
| Migration | Replace in-place | No parallel Streamlit maintenance |

## 1. Backend API

### Framework & Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, lifespan, middleware
│   ├── routers/
│   │   ├── labels.py        # Label Sorter endpoints
│   │   ├── validator.py     # Address Validator endpoints
│   │   ├── addresses.py     # Address Book CRUD
│   │   ├── pickup.py        # Pickup Request endpoint
│   │   └── jobs.py          # Job status + file download
│   ├── core/                # Business logic (migrated from src/)
│   │   ├── pdf_processor.py
│   │   ├── excel_parser.py
│   │   ├── matcher.py
│   │   ├── sorter.py
│   │   ├── zip_validator.py
│   │   ├── address_validator.py
│   │   ├── address_parser.py
│   │   ├── address_book.py
│   │   ├── italian_db.py
│   │   ├── models.py
│   │   └── security.py
│   ├── schemas/             # Pydantic request/response models
│   │   ├── labels.py
│   │   ├── validator.py
│   │   ├── addresses.py
│   │   ├── pickup.py
│   │   └── common.py        # ApiResponse wrapper, error format
│   ├── services/
│   │   └── job_store.py     # In-memory + disk job storage with TTL
│   └── config.py            # Environment variable config
├── data/                    # JSON reference files (comuni, province, PO numbers)
├── requirements.txt
└── tests/
    ├── test_routers/
    └── test_core/
```

### API Endpoints

All endpoints versioned under `/api/v1/`.

#### Label Sorter

```
POST /api/v1/jobs/labels
  Input: multipart/form-data
    - pdf_files: File[] (one or more PDFs)
    - excel_file: File (ShippyPro export)
    - sort_method: "excel_order" | "order_id_numeric"
  Response: { "ok": true, "data": { "job_id": "uuid" } }

GET /api/v1/jobs/{job_id}/status
  Response: {
    "ok": true,
    "data": {
      "status": "processing" | "complete" | "failed",
      "progress": {                      # optional, during processing
        "current": 42,
        "total": 100,
        "message": "Validating address 42/100"
      },
      "result": {                        # only when complete
        "total_pages": 342,
        "matched": 338,
        "unmatched": 4,
        "match_rate": 98.8,
        "unmatched_details": [...],
        "files": {
          "pdf": "/api/v1/jobs/{id}/files/reordered.pdf",
          "csv": "/api/v1/jobs/{id}/files/unmatched.csv"
        }
      },
      "error": "..."                     # only when failed
    }
  }

GET /api/v1/jobs/{job_id}/files/{filename}
  Response: Binary file download (FileResponse)
```

#### Address Validator

```
POST /api/v1/jobs/validator
  Input: multipart/form-data
    - excel_file: File
    - confidence_threshold: int (default 90)
    - street_confidence_threshold: int (default 85)
    - bypass_pin: str (optional)
  Response: { "ok": true, "data": { "job_id": "uuid" } }

# Status and file download use the same /jobs/{id}/status and /jobs/{id}/files endpoints.
# Result shape:
{
  "total_rows": 100,
  "valid_count": 82,
  "corrected_count": 12,
  "review_count": 3,
  "skipped_count": 3,
  "street_verified_count": 78,
  "street_corrected_count": 8,
  "po_invalid_count": 2,
  "results": [
    {
      "status": "verified" | "corrected" | "review",
      "city": "Roma",
      "street": "Via Roma 1",
      "original_zip": "00187",
      "suggested_zip": null,
      "suggested_street": null,
      "corrections": []
    }
  ],
  "files": {
    "corrected": "/api/v1/jobs/{id}/files/corrected.xlsx",
    "review": "/api/v1/jobs/{id}/files/review.xlsx"
  }
}
```

#### Address Book

```
GET    /api/v1/addresses              → list all addresses
POST   /api/v1/addresses              → create address
PUT    /api/v1/addresses/{id}         → update address
DELETE /api/v1/addresses/{id}         → delete address
PUT    /api/v1/addresses/{id}/default → set as default
```

Request/response bodies use Pydantic schemas matching the existing `Address` dataclass.

#### Pickup Request

```
POST /api/v1/pickup/request
  Input: JSON body (PickupRequestSchema)
    - carrier, pickup_date, time_start, time_end
    - company, contact_name, address, zip_code, city, province, reference
    - num_packages, weight_per_package, length, width, height
    - use_pallet, num_pallets, pallet_length, pallet_width, pallet_height
    - notes
  Response: { "ok": true, "data": { "message": "Richiesta inviata" } }
```

**Backend logic:** The existing `send_pickup_request()` function (currently in `app.py`) moves to `backend/app/core/pickup.py`. It builds a ~40-field Zapier webhook payload (calculated fields: `shipment_type`, `total_weight`, `total_volume_m3`, formatted strings, summary fields) and POSTs to the Zapier webhook URL. This is non-trivial business logic — copy it as-is, only removing the Streamlit-specific error handling wrappers.

#### Utility

```
GET /api/v1/health → { "ok": true, "data": { "version": "3.0" } }
```

### Consistent Response Format

```python
# schemas/common.py
class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: ErrorDetail | None = None

class ErrorDetail(BaseModel):
    code: str          # e.g. "VALIDATION_ERROR", "FILE_TOO_LARGE", "RATE_LIMIT"
    message: str       # Human-readable
```

### Job Store

```python
# services/job_store.py
class JobStore:
    """Async job storage — in-memory index + disk for files."""

    def create_job(job_type: str) -> str:
        """Create a new job, return job_id (UUID)."""

    def update_status(job_id: str, status: str, result: dict = None, error: str = None):
        """Update job status."""

    def save_file(job_id: str, filename: str, data: bytes):
        """Save a result file to /tmp/elc-jobs/{job_id}/{filename}."""

    def get_status(job_id: str) -> dict:
        """Return current job status + result."""

    def get_file_path(job_id: str, filename: str) -> Path | None:
        """Return file path for download, or None if not found."""

    def cleanup_expired():
        """Remove jobs older than 1 hour. Called periodically."""
```

- Files stored at `/tmp/elc-jobs/{job_id}/`
- In-memory dict tracks status + result metadata
- Cleanup runs every 10 minutes via FastAPI lifespan background task
- Max 50 concurrent jobs (prevent abuse)
- **Ephemeral storage:** Job data is lost on server restart (Render can restart at any time). This is acceptable for an internal tool. Frontend must handle 404 on `/jobs/{id}/status` gracefully — show "Job expired or server restarted. Please re-run." and reset to the upload step.
- **Progress tracking:** `zip_validator.py` still calls a callback internally — instead of removing it, adapt it to write progress to the job store via `update_progress(job_id, current, total, message)`. This powers the optional `progress` field in the status response.

### Server-Side Security

All file validation is enforced server-side (client-side validation is a UX convenience, not a security boundary):

- **Max file size:** 50 MB per file (reject with `FILE_TOO_LARGE` error)
- **Max PDF pages:** 500 (reject after counting pages)
- **Max Excel rows:** 1000 for Address Validator (reject after parsing)
- **Total PDF size:** max 100 MB across all uploaded PDFs
- **Excel content injection:** scan for formula injection patterns (`=CMD(`, `=SYSTEM(`, etc.) via `validate_excel_content()` — reject with `CONTENT_INVALID` error
- **Filename sanitization:** `sanitize_filename()` on all uploaded filenames (path traversal prevention)
- **Failed attempt tracking:** `record_failed_attempt()` for content injection attempts

These limits are implemented as FastAPI dependency functions injected per-router.

### Rate Limiting

**Address Validator:** 1000 rows per 12-hour window, **global** (not per-IP) — tracked via Supabase, matching current behavior. Bypass with PIN. Additionally, 3-second cooldown between validation requests (prevents accidental double-submit).

**Other endpoints** use `slowapi` middleware per-IP:
- Label Sorter: 20 requests/hour
- Pickup Request: 30 requests/hour
- Address CRUD: 100 requests/hour

### Module Migration

| Current (`src/`) | Target (`backend/app/core/`) | Changes |
|------------------|------------------------------|---------|
| pdf_processor.py | Copy as-is | None |
| excel_parser.py | Copy as-is | None |
| matcher.py | Copy as-is | None |
| sorter.py | Copy as-is | None |
| models.py | Copy as-is | None |
| address_parser.py | Copy as-is | None |
| address_validator.py | Copy as-is | None |
| italian_db.py | Copy as-is | None |
| zip_validator.py | Copy, adapt | Remove `progress_callback` param. File generation methods (`generate_corrected_excel`, `generate_review_report`) stay in this module — called by the router after processing |
| — `send_pickup_request()` (in app.py) | Move to `core/pickup.py` | Extract from app.py, remove Streamlit error handling wrappers |
| — `generate_csv_report()` (in app.py) | Move to `core/label_report.py` | Extract from app.py — generates CSV report for unmatched labels |
| config.py | Rewrite | Simple `os.environ.get()`, Pydantic Settings class. Remove `st.secrets` fallback entirely. |
| security.py | Refactor | Remove `get_client_ip()` (use FastAPI `Request.client.host`), remove `import streamlit` and `st.session_state` entirely. Keep `validate_excel_content()`, `sanitize_filename()`, rate limit functions. |
| address_book.py | Refactor | Remove `import streamlit` entirely. Remove `_clear_cache()` and `st.session_state` caching (Supabase queries are fast enough for internal tool). Keep all Supabase CRUD functions. |
| logging_config.py | Simplify | Remove `StreamlitLogHandler`. Keep `get_logger()` and `setup_logging()` — core modules import from this. Use standard `logging.StreamHandler` instead. |
| ui_components.py | Delete | Replaced by React |

### Backend Dependencies

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9
slowapi>=0.1.9
pydantic>=2.6.0
pydantic-settings>=2.1.0
pandas>=2.0.0
pymupdf>=1.23.0
openpyxl>=3.1.0
anthropic>=0.80.0
supabase>=2.0.0
requests>=2.28.0
lxml
html5lib
beautifulsoup4
python-calamine
xlrd>=2.0.1       # for .xls file support
pytest>=8.0.0
httpx>=0.27.0     # for TestClient
```

## 2. Frontend

### Tech Stack

- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- shadcn/ui (component library — buttons, inputs, cards, tables, toggles, dropdowns)
- React Router v6 (client-side routing)
- TanStack Query v5 (API calls, polling, caching)

### Structure

```
frontend/
├── src/
│   ├── App.tsx                    # Router + layout
│   ├── index.tsx                  # Entry point
│   ├── api/
│   │   └── client.ts             # Typed fetch wrapper, base URL from VITE_API_URL env var
│   ├── components/
│   │   ├── layout/
│   │   │   ├── NavBar.tsx         # Top nav: logo, tool tabs, dev toggle
│   │   │   └── PageShell.tsx      # Page title + optional step indicator + children
│   │   ├── StepIndicator.tsx      # Horizontal step breadcrumb
│   │   ├── FileDropZone.tsx       # Drag-and-drop file upload with validation
│   │   ├── ResultsTable.tsx       # Filterable data table with colored status dots
│   │   ├── SegmentedProgressBar.tsx  # Green/indigo/amber segments
│   │   ├── DownloadCard.tsx       # Primary/secondary/disabled download
│   │   ├── SuccessBanner.tsx      # Green success notification
│   │   ├── CarrierTile.tsx        # Clickable carrier selection card
│   │   ├── DimensionsInput.tsx    # L × W × H inline triple input
│   │   └── ui/                    # shadcn/ui primitives
│   ├── pages/
│   │   ├── PickupRequest.tsx
│   │   ├── AddressValidator.tsx
│   │   └── LabelSorter.tsx
│   ├── hooks/
│   │   ├── useJobPolling.ts       # Poll /jobs/{id}/status every 3s
│   │   ├── useAddresses.ts        # Address CRUD via React Query
│   │   └── useDevMode.ts          # ?dev=1 query param context
│   └── lib/
│       ├── colors.ts              # Design token constants
│       └── types.ts               # TypeScript types matching API schemas
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── vite.config.ts
└── .env                       # VITE_API_URL=http://localhost:8000 (dev default)
```

**API URL config:** `client.ts` reads `import.meta.env.VITE_API_URL` for the backend base URL. Defaults to `http://localhost:8000` in development. On Render, set `VITE_API_URL` as a build-time env var pointing to the `elc-api` service URL. Vite inlines env vars at build time.

### Routing

```
/               → Redirect to /pickup
/pickup         → PickupRequest.tsx
/validator      → AddressValidator.tsx
/labels         → LabelSorter.tsx
```

Default route is `/pickup` (most used tool, matching current tab order).

### Design Tokens

Tailwind config extends the default palette with our Cool Indigo system:

```typescript
// tailwind.config.ts
theme: {
  extend: {
    colors: {
      primary: { DEFAULT: '#6366f1', light: '#eef2ff', border: '#c7d2fe' },
      success: '#22c55e',
      warning: '#f59e0b',
      error: '#dc2626',
      surface: '#f8f9fc',
      card: '#ffffff',
      border: '#e5e7eb',
      text: { primary: '#0f172a', secondary: '#64748b', muted: '#9ca3af' },
    }
  }
}
```

### Key Component Behaviors

**NavBar.tsx**
- Logo "ELC Tools" left, tool tabs center, ⚙️ dev toggle right (real `<button>`)
- Active tab: indigo underline + bold. Inactive: gray.
- Dev toggle: clickable button that adds/removes `?dev=1` from URL
- Uses React Router `<NavLink>` for tab highlighting

**FileDropZone.tsx**
- Drag-and-drop area with dashed border
- Client-side validation: file type, file size (configurable per instance) — UX convenience only, server enforces limits
- Shows filename + size after selection
- Accept multiple files (for Label Sorter PDFs) or single file
- Styled with primary_border dashed, hover state changes background

**useJobPolling.ts**
```typescript
function useJobPolling(jobId: string | null) {
  // Returns: { status, result, error, isPolling }
  // Polls GET /api/v1/jobs/{jobId}/status every 3 seconds
  // Stops polling when status is "complete" or "failed"
  // Uses TanStack Query's refetchInterval
}
```

**DimensionsInput.tsx**
- Three number inputs in a single visual row with × separators
- Labels above: Lunghezza / Larghezza / Altezza
- "cm" unit at end
- Tab key navigates between fields
- Per-field validation (red border on invalid)
- Reused for both package and pallet dimensions

**ResultsTable.tsx**
- Filter tabs: "Tutti" / "Solo problemi"
- Color-coded status dots (green/indigo/amber) with text labels
- Inline corrections: "Via Turti → **Via Turati**"
- Row background tinting for corrected (light indigo) and warning (light amber) rows
- Expandable to show all rows (default: first 10)

### Page Flows

**PickupRequest.tsx**
1. Render form cards (carrier, address, packages, notes)
2. Summary bar at bottom with weight + type badge
3. Submit → POST /api/v1/pickup/request → success banner or error

**AddressValidator.tsx**
1. Step 1 (Carica): File drop zone + usage stats + advanced options
2. Submit → POST /api/v1/jobs/validator → receive job_id
3. Step 2 (Valida): Spinner while polling job status
4. Step 3 (Risultato): Progress bar + breakdown chips + filter table + download cards

**LabelSorter.tsx**
1. Step 1 (Carica): Two file drop zones (PDF + Excel)
2. Step 2 (Configura): Sort method selection
3. Submit → POST /api/v1/jobs/labels → receive job_id
4. Step 3 (Elabora): Spinner while polling
5. Step 4 (Scarica): Success banner + download cards + unmatched table

### Dev Mode

- `useDevMode()` hook reads `?dev=1` from URL search params
- NavBar shows clickable ⚙️ that toggles the param
- When active: "DEV" badge in header, debug panels visible in pages
- Components use `const devMode = useDevMode()` and conditionally render debug sections

## 3. Deployment

### Render Configuration

```yaml
# render.yaml
services:
  - type: web
    name: elc-api
    runtime: python
    plan: starter
    region: frankfurt
    buildCommand: cd backend && pip install -r requirements.txt
    startCommand: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/v1/health
    envVars:
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
      - key: FRONTEND_URL
        sync: false

  - type: web
    name: elc-frontend
    runtime: static
    buildCommand: cd frontend && npm ci && npm run build
    staticPublishPath: frontend/dist
    headers:
      - path: /*
        name: Cache-Control
        value: public, max-age=3600
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
```

### CORS

```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Environment Variables

Same as current Render setup plus `FRONTEND_URL`. All existing env vars carry over.

### Migration Cutover

1. Develop and test locally (backend on :8000, frontend on :5173)
2. **Delete the old `elc-tools` Streamlit service from Render dashboard** (it won't auto-replace since the service name changes)
3. Push to main
4. Render detects new `render.yaml`, creates two new services: `elc-api` + `elc-frontend`
5. Configure all env vars on `elc-api` (copy from old service before deleting)
6. Set `FRONTEND_URL` on `elc-api` pointing to the `elc-frontend` URL
7. Verify all 3 tools work end-to-end

### Files Deleted

- `app.py` — replaced by backend/
- `src/ui_components.py` — replaced by React
- `.streamlit/` — no longer needed
- `streamlit_redirect_app.py` — no longer needed
- `streamlit` removed from requirements.txt
- `data/addresses.json` — legacy file, addresses are in Supabase

### Files Moved

- `src/*.py` → `backend/app/core/*.py` (business logic)
- `data/*.json` → `backend/data/*.json` (reference data)
- `tests/*.py` → `backend/tests/test_core/*.py` (existing tests)

## 4. Testing Strategy

### Backend

- **Unit tests** for each core module (migrate existing tests)
- **Router tests** using FastAPI `TestClient` (httpx) — test each endpoint with real file uploads
- **Job lifecycle tests** — create job → poll → download → verify cleanup
- **Integration tests** for rate limiting middleware

### Frontend

- **Component tests** with Vitest + React Testing Library
- **Page tests** — mock API responses, verify correct rendering at each step
- **No E2E tests initially** — manual testing for the 3 tools is sufficient for internal tooling

## 5. Design Mockups

The UI design from the earlier UX redesign spec (`2026-03-19-ux-redesign-design.md`) carries over exactly:
- Cool Indigo palette (#6366f1)
- Top nav with tabs (Ritiro → Validator → Label Sorter)
- Step wizards for Label Sorter (4 steps) and Address Validator (3 steps)
- Card-based forms for Pickup Request
- Segmented progress bar for Address Validator results
- Filter tabs on results tables
- Dev mode toggle (now a proper button)

Visual mockups in `.superpowers/brainstorm/` remain the reference.
