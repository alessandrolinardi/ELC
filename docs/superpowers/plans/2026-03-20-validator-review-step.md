# Validator Review Step Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a human-in-the-loop review step between AI parsing and Google validation in the Address Validator, allowing users to see, edit, and confirm AI suggestions before burning Google API calls.

**Architecture:** Split the existing single-phase validator job into two phases (parse → confirm → validate). Extract `_validate_addresses()` from `ZipValidator.process_dataframe()`. Add new `/confirm` endpoint. Frontend gets a new Step 2 (Revisione AI) with inline editing.

**Tech Stack:** FastAPI, React, TypeScript, TanStack Query

**Spec:** `docs/superpowers/specs/2026-03-20-validator-review-step-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/core/models.py` | Modify | Add `parse_method` field to `ParsedAddress`, add `batch_retries_succeeded` to `ParsingMetrics` |
| `backend/app/core/zip_validator.py` | Modify | Extract `_validate_addresses()` from `process_dataframe()` |
| `backend/app/core/address_parser.py` | Modify | Add retry logic, set `max_retries=3`, set `parse_method` on results |
| `backend/app/routers/validator.py` | Modify | Split into two-phase flow, add `/confirm` endpoint |
| `backend/app/schemas/validator.py` | Modify | Add `ConfirmRequest`, `ParsedRow`, `ParsingSummary` schemas |
| `backend/tests/test_routers/test_validator_confirm.py` | Create | Test the confirm endpoint |
| `frontend/src/lib/types.ts` | Modify | Add new status values, ParsedRow, ParsingSummary, ConfirmRequest |
| `frontend/src/hooks/useJobPolling.ts` | Modify | Stop polling on "parsed" status too |
| `frontend/src/api/client.ts` | Modify | Add `confirmValidation()` API call |
| `frontend/src/components/ParseReviewTable.tsx` | Create | Review table with inline editing |
| `frontend/src/pages/AddressValidator.tsx` | Modify | Add Step 2 (Revisione AI) |

---

## Task 1: Add `parse_method` to models

**Files:**
- Modify: `backend/app/core/models.py`

- [ ] **Step 1: Add `parse_method` field to `ParsedAddress` dataclass**

```python
@dataclass
class ParsedAddress:
    # ... existing fields ...
    parse_method: str = "ai"  # "ai" or "regex"
```

- [ ] **Step 2: Add `batch_retries_succeeded` field to `ParsingMetrics` dataclass**

```python
@dataclass
class ParsingMetrics:
    # ... existing fields ...
    batch_retries_succeeded: int = 0
```

- [ ] **Step 3: Run tests**

Run: `cd backend && python3 -m pytest tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/models.py
git commit -m "feat: add parse_method to ParsedAddress and batch_retries_succeeded to ParsingMetrics

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Extract `_validate_addresses` from ZipValidator

**Files:**
- Modify: `backend/app/core/zip_validator.py`

This is the critical backend refactor — split `process_dataframe()` so validation can run independently from parsing.

- [ ] **Step 1: Read `process_dataframe()` (lines 306-626)**

Understand the two sections:
- Lines 345-362: Parsing (calls `self.address_parser.parse_all()`)
- Lines 364-609: Validation loop (Google API, ZIP checks, result building)

- [ ] **Step 2: Create `_validate_addresses` method**

Extract lines 364-609 (the validation loop) into a new method:

```python
def _validate_addresses(self, df, parsed_addresses, progress_callback=None):
    """Run Google validation on pre-parsed addresses. Skips parsing step.

    Args:
        df: Original DataFrame with address data
        parsed_addresses: List of ParsedAddress objects (one per row)
        progress_callback: Optional callback(current, total, message)

    Returns:
        tuple[ValidationReport, pd.DataFrame] — same as process_dataframe()
    """
    # ... validation loop code moved here from process_dataframe
```

- [ ] **Step 3: Refactor `process_dataframe()` to call `_validate_addresses`**

```python
def process_dataframe(self, df, progress_callback=None):
    # ... preprocessing (lines 306-344)

    # Step 1: Parse addresses
    parsed_addresses = self.address_parser.parse_all(raw_addresses)

    # Step 2: Validate (now delegated)
    return self._validate_addresses(df, parsed_addresses, progress_callback)
```

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: Same 103 pass / 3 pre-existing fail

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/zip_validator.py
git commit -m "refactor: extract _validate_addresses from process_dataframe

Safe refactor — process_dataframe now calls parse_all then _validate_addresses.
No behavior change for existing callers. Enables Phase 2 to skip re-parsing.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add address parser retry logic + set parse_method

**Files:**
- Modify: `backend/app/core/address_parser.py`

- [ ] **Step 1: Set max_retries=3 on Anthropic client (line 99)**

```python
self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)
```

- [ ] **Step 2: Set `parse_method` on results in `_parse_batch_claude` and `parse_single_regex`**

In `_parse_batch_claude`, after creating each `ParsedAddress`, set:
```python
parsed.parse_method = "ai"
```

In `parse_single_regex`, before returning:
```python
result.parse_method = "regex"
return result
```

- [ ] **Step 3: Add application-level retry in `parse_all()` (lines 139-146)**

Replace the immediate regex fallback with a retry:

```python
except Exception as e:
    logger.warning(f"Batch at {start_idx} failed: {e}, retrying in 2s...")
    time.sleep(2)
    try:
        batch_results = self._parse_batch_claude(batch, start_idx)
        for i, parsed in enumerate(batch_results):
            results[start_idx + i] = parsed
        self.metrics.batch_retries_succeeded += 1
    except Exception as e2:
        logger.error(f"Batch at {start_idx} retry also failed: {e2}, falling back to regex")
        self.metrics.batch_failures += 1
        for i, addr in enumerate(batch):
            results[start_idx + i] = self.parse_single_regex(
                addr["street"], addr["city"], addr["zip"]
            )
            self.metrics.regex_fallback += 1
```

Add `import time` at top if not present.

- [ ] **Step 3: Run tests**

Run: `cd backend && python3 -m pytest tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/address_parser.py
git commit -m "feat: add retry logic for Claude API failures before regex fallback

SDK max_retries=3, plus application-level retry with 2s delay.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Add Pydantic schemas for two-phase flow

**Files:**
- Modify: `backend/app/schemas/validator.py`

- [ ] **Step 1: Add new schemas**

```python
# Add to backend/app/schemas/validator.py

class ParsedRowOriginal(BaseModel):
    street: str
    city: str
    zip: str

class ParsedRowComponents(BaseModel):
    street_prefix: str = ""
    street_name: str = ""
    house_number: str = ""
    location_info: str = ""
    country_code: str = "IT"

class ParsedRow(BaseModel):
    index: int
    original: ParsedRowOriginal
    parsed: ParsedRowOriginal  # reassembled for display
    parsed_components: ParsedRowComponents
    method: str  # "ai" or "regex"
    changed: bool
    changes: list[str] = []
    edited: bool = False

class ParsingSummary(BaseModel):
    total: int
    ai_parsed: int
    regex_fallback: int
    ai_modified: int
    unchanged: int

class ParsedJobResult(BaseModel):
    parsing_summary: ParsingSummary
    rows: list[ParsedRow]

class ConfirmRequest(BaseModel):
    edits: dict[str, dict[str, str]] = {}
    retry_regex_rows: bool = False
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/validator.py
git commit -m "feat: add Pydantic schemas for two-phase validator flow

ParsedRow, ParsingSummary, ParsedJobResult, ConfirmRequest.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Split validator router into two phases + confirm endpoint

**Files:**
- Modify: `backend/app/routers/validator.py`

This is the core backend change. The existing `_process_validation` is split into `_process_parse` and `_process_validate`, and a new `/confirm` endpoint is added.

- [ ] **Step 1: Rewrite `_process_validation` → `_process_parse`**

The function now:
1. Reads Excel, validates content, checks rate limits (same as before)
2. Runs `AddressParser.parse_all()` (same as before)
3. **NEW:** Builds per-row `ParsedRow` data with original/parsed/method/changes
4. **NEW:** Saves `excel_bytes` to disk via `job_store.save_file(job_id, "original.xlsx", excel_bytes)`
5. **NEW:** Stores config inside the result dict so `/confirm` can retrieve it:
   ```python
   result = {
       "parsing_summary": {...},
       "rows": [...],
       "config": {
           "confidence": confidence,
           "street_confidence": street_confidence,
           "pin_valid": pin_valid,
           "client_ip": client_ip,
       }
   }
   ```
6. Sets job status to `"parsed"` instead of continuing to Google validation
7. **IMPORTANT:** After loading the Excel into a DataFrame, verify the index is 0-based RangeIndex before storing: `df = df.reset_index(drop=True)`. This ensures `parsed_addresses[i]` aligns with `df.iloc[i]` after the save/reload round-trip in Phase 2.

Key code for building per-row data:

```python
rows = []
for i, (parsed_addr, raw) in enumerate(zip(parsed_addresses, raw_addresses)):
    original_street = raw["street"]
    parsed_street = parsed_addr.full_street
    changed = original_street.strip().lower() != parsed_street.strip().lower()

    changes = []
    if changed:
        changes.append(f"street: {original_street} → {parsed_street}")

    rows.append({
        "index": i,
        "original": {"street": original_street, "city": raw["city"], "zip": raw["zip"]},
        "parsed": {"street": parsed_street, "city": raw["city"], "zip": raw["zip"]},
        "parsed_components": {
            "street_prefix": parsed_addr.street_prefix,
            "street_name": parsed_addr.street_name,
            "house_number": parsed_addr.house_number,
            "location_info": parsed_addr.location_info,
            "country_code": parsed_addr.country_code,
        },
        "method": parsed_addr.parse_method,  # "ai" or "regex" — set by address_parser
        "changed": changed,
        "changes": changes,
    })
```

Note: determining `method` per-row requires tracking which rows fell back to regex. The simplest approach: check `parser.metrics` or add a `method` attribute to `ParsedAddress` in the parser. Alternatively, run a separate parse pass and track which indices succeeded with Claude vs regex.

**Practical approach for method tracking:** After `parse_all()`, the `parser.metrics.regex_fallback` count tells how many fell back, but not which ones. Add a simple tracking mechanism: have `parse_all()` return `list[tuple[ParsedAddress, str]]` where the string is "ai" or "regex". Or simpler: add a `parse_method` attribute to `ParsedAddress`:

```python
# In models.py, add to ParsedAddress:
parse_method: str = "ai"  # "ai" or "regex"
```

Then in `address_parser.py`, set `parse_method="regex"` when falling back.

- [ ] **Step 2: Create `_process_validate` function**

```python
def _process_validate(job_id, parsed_rows, confidence, street_confidence, pin_valid, client_ip, retry_regex):
    settings = get_settings()
    try:
        # Retry regex rows if requested
        if retry_regex:
            regex_rows = [r for r in parsed_rows if r["method"] == "regex" and not r.get("edited")]
            if regex_rows:
                job_store.update_progress(job_id, 0, len(regex_rows), "Nuovo tentativo AI...")
                parser = AddressParser(api_key=settings.anthropic_api_key)
                addresses = [{"street": r["original"]["street"], "city": r["original"]["city"], "zip": r["original"]["zip"]} for r in regex_rows]
                try:
                    re_parsed = parser.parse_all(addresses)
                    for row, new_parsed in zip(regex_rows, re_parsed):
                        row["parsed"]["street"] = new_parsed.full_street
                        row["parsed_components"] = {
                            "street_prefix": new_parsed.street_prefix,
                            "street_name": new_parsed.street_name,
                            "house_number": new_parsed.house_number,
                            "location_info": new_parsed.location_info,
                            "country_code": new_parsed.country_code,
                        }
                        row["method"] = "ai"
                except Exception:
                    pass  # Keep regex results

        # Load original Excel — reset index to ensure 0-based alignment with parsed_addresses
        excel_path = job_store.get_file_path(job_id, "original.xlsx")
        df = pd.read_excel(excel_path).reset_index(drop=True)

        # Build ParsedAddress objects from confirmed rows
        from ..core.models import ParsedAddress
        from ..core.address_parser import AddressParser as AP

        parsed_addresses = []
        for row in parsed_rows:
            comp = row["parsed_components"]
            parsed_addresses.append(ParsedAddress(
                street_prefix=comp["street_prefix"],
                street_name=comp["street_name"],
                house_number=comp["house_number"],
                location_info=comp.get("location_info", ""),
                country_code=comp.get("country_code", "IT"),
            ))

        # Run Google validation (Phase 2)
        validator = ZipValidator(
            confidence_threshold=confidence,
            street_confidence_threshold=street_confidence,
            google_api_key=settings.google_address_validation_api_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        def progress_callback(current, total, message):
            job_store.update_progress(job_id, current, total, message)

        report, preprocessed_df = validator._validate_addresses(df, parsed_addresses, progress_callback)

        # Generate output files + build results (same as current code)
        corrected_excel = validator.generate_corrected_excel(preprocessed_df, report)
        review_excel = validator.generate_review_report(report)
        job_store.save_file(job_id, "corrected.xlsx", corrected_excel)
        job_store.save_file(job_id, "review.xlsx", review_excel)

        if not pin_valid:
            from ..core.security import record_usage
            record_usage(client_ip, len(df))

        # Build result (same format as current complete result)
        # ... same per-row result building code as current ...

        job_store.update_status(job_id, "complete", result={...})
    except Exception as e:
        job_store.update_status(job_id, "failed", error=str(e))
```

- [ ] **Step 3: Add `/confirm` endpoint**

```python
@router.post("/jobs/{job_id}/confirm")
async def confirm_validation(job_id: str, body: ConfirmRequest):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail={
            "ok": False, "error": {"code": "JOB_NOT_FOUND", "message": "Job not found or expired"}
        })
    if status["status"] != "parsed":
        raise HTTPException(status_code=409, detail={
            "ok": False, "error": {"code": "INVALID_STATE", "message": f"Job is in state '{status['status']}', expected 'parsed'"}
        })

    # Apply user edits
    parsed_rows = status["result"]["rows"]
    for idx_str, field_edits in body.edits.items():
        idx = int(idx_str)
        row = next((r for r in parsed_rows if r["index"] == idx), None)
        if row:
            row["parsed"].update(field_edits)
            if "street" in field_edits:
                from ..core.address_parser import AddressParser
                re_parsed = AddressParser().parse_single_regex(
                    field_edits["street"],
                    row["parsed"].get("city", ""),
                    row["parsed"].get("zip", ""),
                )
                row["parsed_components"] = {
                    "street_prefix": re_parsed.street_prefix,
                    "street_name": re_parsed.street_name,
                    "house_number": re_parsed.house_number,
                    "location_info": re_parsed.location_info,
                    "country_code": re_parsed.country_code,
                }
            row["edited"] = True

    # Get stored config from the parsed result
    config = status.get("result", {}).get("config", {})

    job_store.update_status(job_id, "processing_validate")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_validate, job_id, parsed_rows,
        config.get("confidence", 90), config.get("street_confidence", 85),
        config.get("pin_valid", False), config.get("client_ip", "unknown"),
        body.retry_regex_rows,
    )

    return {"ok": True, "data": {"status": "processing_validate"}}
```

- [ ] **Step 4: Update existing `POST /jobs/validator` to only run Phase 1**

Change the endpoint to call `_process_parse` instead of `_process_validation`.

- [ ] **Step 5: Register confirm endpoint**

The confirm endpoint uses the same `router` — no change to `main.py` needed.

- [ ] **Step 6: Run tests**

Run: `cd backend && python3 -m pytest tests/ -v`

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/validator.py backend/app/schemas/validator.py
git commit -m "feat: two-phase validator — parse, review, then validate

Split validator into Phase 1 (AI parse) and Phase 2 (Google validate).
New /confirm endpoint applies user edits and triggers Phase 2.
Supports retry_regex_rows for re-parsing failed Claude batches.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Update frontend types and hooks

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/hooks/useJobPolling.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Update types.ts**

Add new status values and types:

```typescript
// Update JobStatus to include new states
export interface JobStatus<T = unknown> {
  status: "processing_parse" | "parsed" | "processing_validate" | "complete" | "failed"
  job_type: string
  progress: JobProgress | null
  result: T | null
  error: string | null
  config?: Record<string, unknown>
}

// Add new types
export interface ParsedRowData {
  street: string
  city: string
  zip: string
}

export interface ParsedRowComponents {
  street_prefix: string
  street_name: string
  house_number: string
  location_info: string
  country_code: string
}

export interface ParsedRow {
  index: number
  original: ParsedRowData
  parsed: ParsedRowData
  parsed_components: ParsedRowComponents
  method: "ai" | "regex"
  changed: boolean
  changes: string[]
  edited?: boolean
}

export interface ParsingSummary {
  total: number
  ai_parsed: number
  regex_fallback: number
  ai_modified: number
  unchanged: number
}

export interface ParsedJobResult {
  parsing_summary: ParsingSummary
  rows: ParsedRow[]
}

export interface ConfirmRequest {
  edits: Record<string, Record<string, string>>
  retry_regex_rows: boolean
}
```

- [ ] **Step 2: Update useJobPolling.ts**

Add `"parsed"` to the list of statuses that stop polling:

```typescript
// Change the refetchInterval condition:
refetchInterval: (query) => {
  const status = query.state.data?.data?.status
  if (status === "complete" || status === "failed" || status === "parsed") {
    return false  // stop polling
  }
  return pollInterval
}
```

- [ ] **Step 3: Add `confirmValidation` to client.ts**

```typescript
export async function confirmValidation(jobId: string, body: ConfirmRequest): Promise<ApiResponse<{ status: string }>> {
  return post(`/api/v1/jobs/${jobId}/confirm`, body)
}
```

- [ ] **Step 4: Build**

Run: `cd frontend && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/hooks/useJobPolling.ts frontend/src/api/client.ts
git commit -m "feat: update frontend types and hooks for two-phase validator

Add parsed status, ParsedRow types, confirmValidation API call.
useJobPolling now stops on 'parsed' status for review step.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Create ParseReviewTable component

**Files:**
- Create: `frontend/src/components/ParseReviewTable.tsx`

- [ ] **Step 1: Build the review table component**

```typescript
interface ParseReviewTableProps {
  rows: ParsedRow[]
  summary: ParsingSummary
  onEdit: (index: number, field: string, value: string) => void
  onRetryRegex: () => void
  onConfirm: () => void
  isConfirming: boolean
}
```

The component has these sections:

**Summary banner:** Shows AI coverage bar + counts (ai_parsed, regex_fallback, ai_modified, unchanged)

**Modified rows list:** Only rows where `changed: true` and `method: "ai"`. Each row:
- Row index + city label
- Original street in gray strikethrough → parsed street in indigo bold
- Pencil icon → opens inline edit (Input fields for street, city, zip with Save/Cancel)

**Regex fallback warning:** If `regex_fallback > 0`, shows amber warning banner with "Riprova con AI" and "Procedi comunque" buttons.

**All rows (collapsed):** "Mostra tutti (N righe) ▾" expander with full table.

**Action bar:** "Conferma e avvia validazione Google" primary button.

Use shadcn/ui components: Card, Button, Input, Badge, Separator.
Use Tailwind for styling.

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ParseReviewTable.tsx
git commit -m "feat: add ParseReviewTable component for AI review step

Summary banner, modified rows with inline editing, regex warning,
expandable all-rows table, confirm action bar.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Update AddressValidator page with Step 2

**Files:**
- Modify: `frontend/src/pages/AddressValidator.tsx`

- [ ] **Step 1: Update steps from 3 to 4**

```typescript
const STEPS = [
  { label: "Carica" },       // Step 0: Upload
  { label: "Revisione AI" }, // Step 1: Review parsing (NEW)
  { label: "Valida" },       // Step 2: Google validation
  { label: "Risultato" },    // Step 3: Final results
]
```

- [ ] **Step 2: Update step transition logic**

```typescript
// When job status becomes "parsed" → advance to step 1 (review)
useEffect(() => {
  if (jobStatus === "parsed" && currentStep === 0) {
    setCurrentStep(1)
  }
}, [jobStatus])

// After confirm, when status becomes "processing_validate" → advance to step 2
// When job status becomes "complete" → advance to step 3
```

- [ ] **Step 3: Add Step 1 (Revisione AI) rendering**

When `currentStep === 1` and job status is `"parsed"`:
- Extract `parsing_summary` and `rows` from job result
- Manage local edit state: `const [edits, setEdits] = useState<Record<string, Record<string, string>>>({})`
- Render `<ParseReviewTable>` with the data
- Handle confirm: call `confirmValidation(jobId, { edits, retry_regex_rows: false })`
- Handle retry: call `confirmValidation(jobId, { edits, retry_regex_rows: true })`
- After confirm, reset polling (set jobId again to trigger re-poll)

- [ ] **Step 4: Add per-row quality indicator to Step 3 (results)**

In the results table, add a column showing 🤖 (AI) or ⚙️ (regex) per row.

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/AddressValidator.tsx
git commit -m "feat: add AI review step to Address Validator

4-step flow: Upload → AI Review → Google Validate → Results.
Users can see and edit AI suggestions before Google API calls.
Regex fallback rows shown separately with retry option.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Integration test + push

**Files:**
- All modified files

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: 103+ pass, 3 pre-existing fail

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Clean build, 0 errors

- [ ] **Step 3: Push**

```bash
git push origin main
```
