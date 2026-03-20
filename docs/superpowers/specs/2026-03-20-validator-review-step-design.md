# Address Validator — AI Parsing Review Step

## Context

The Address Validator currently processes addresses in a single pass: upload → AI parse + Google validate → results. Users have no visibility into what the AI changed before Google API calls are made. This means bad AI parsing wastes Google API quota and produces poor results.

This spec adds a human-in-the-loop review step between AI parsing and Google validation, allowing users to see, approve, and edit AI suggestions before committing to Google API calls.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Review content | Changes-only + summary (hybrid) | Don't overwhelm with 500 OK rows, focus on the 20-50 that changed |
| Row interaction | Pre-accepted, edit on exception | Least friction — AI is trusted by default, user only fixes errors |
| Regex fallback UX | Show separately with retry option | User chooses: retry Claude or proceed with regex |
| Skippable | No — always show review | Consistency, builds trust, catches errors |

## 1. Two-Phase Job Flow

### Current
```
Upload → Process (parse + validate) → Results
```

### New
```
Upload → Phase 1 (AI Parse) → Review → Phase 2 (Google Validate) → Results
```

### Job Status Transitions
```
processing_parse → parsed → processing_validate → complete
                                                 → failed (at any point)
```

- `processing_parse`: Claude is parsing addresses (with progress updates)
- `parsed`: Parsing done, waiting for user review + confirmation
- `processing_validate`: Google validation running (with progress updates)
- `complete`: Done, files ready for download
- `failed`: Error at any point

## 2. API Changes

### Existing endpoint changes

```
POST /api/v1/jobs/validator
```
Now only runs Phase 1 (AI parsing). Returns job_id as before. When status reaches `parsed`, the job pauses and waits for confirmation.

```
GET /api/v1/jobs/{id}/status
```
Returns different result shapes depending on status:
- During `processing_parse`: progress updates (current/total)
- At `parsed`: parsing results with per-row data for review
- During `processing_validate`: progress updates
- At `complete`: final validation results (unchanged from current)

### New endpoint

```
POST /api/v1/jobs/{id}/confirm
Body: {
  "edits": {
    "3": { "street": "Piazza Garibaldi 4", "city": "Torino" },
    "15": { "street": "Via Corretta 10" }
  },
  "retry_regex_rows": false
}
```

- `edits`: map of row index (string) → overridden field values. Only rows the user changed. Omitted rows use AI suggestion as-is.
- `retry_regex_rows`: if true, re-run Claude parsing on regex-fallback rows before starting Google validation. If Claude still fails, proceed with regex results.
- Returns: `{ "ok": true, "data": { "status": "processing_validate" } }`
- Starts Phase 2 (Google validation) in background.

### Parsed result shape (status = "parsed")

```json
{
  "status": "parsed",
  "result": {
    "parsing_summary": {
      "total": 300,
      "ai_parsed": 285,
      "regex_fallback": 15,
      "ai_modified": 42,
      "unchanged": 243
    },
    "rows": [
      {
        "index": 0,
        "original": { "street": "Via Roam 15", "city": "Milano", "zip": "20100" },
        "parsed": { "street": "Via Roma 15", "city": "Milano", "zip": "20100" },
        "method": "ai",
        "changed": true,
        "changes": ["street: Via Roam 15 → Via Roma 15"]
      },
      {
        "index": 5,
        "original": { "street": "SP227dir. 2", "city": "Carugate", "zip": "20061" },
        "parsed": { "street": "SP227dir. 2", "city": "Carugate", "zip": "20061" },
        "method": "regex",
        "changed": false,
        "changes": []
      }
    ]
  }
}
```

All rows are included in the response. The frontend decides what to show (modified, regex, all).

## 3. Frontend — Step 2: Revisione AI

The Address Validator page steps change from 3 to 4:

```
① Carica → ② Revisione AI → ③ Valida → ④ Risultato
```

### Summary banner

Shows at the top of the review step:
- Count of AI-parsed vs regex-fallback
- Count of modifications suggested vs unchanged
- Visual bar showing AI coverage percentage

### Modified rows section (main focus)

- Header: "N modifiche suggerite"
- All pre-accepted (no accept/reject per row)
- Each row shows: row number, city, original value in gray strikethrough → new value in indigo bold
- Pencil icon opens inline edit mode: all fields become editable inputs with Save/Cancel
- Only rows where `changed: true` and `method: "ai"` are shown here

### Regex fallback section

Shown only if `regex_fallback > 0`. Warning banner:
- "N indirizzi non verificati da AI — il servizio era temporaneamente non disponibile"
- Two buttons: "Riprova con AI" and "Procedi comunque"
- "Riprova con AI" calls confirm with `retry_regex_rows: true`
- "Procedi comunque" dismisses the warning (user proceeds to confirm)

### All rows section

Collapsed by default: "Mostra tutti (N righe) ▾"
- Expandable full table with all rows
- Shows method indicator per row (🤖 AI / ⚙️ Regex)

### Action bar

Primary button: "Conferma e avvia validazione Google"
- Collects any user edits as `edits` map
- Calls `POST /api/v1/jobs/{id}/confirm`
- Transitions to step 3 (spinner with polling)

## 4. Backend Implementation

### Parsed row display format

`AddressParser.parse_all()` returns `ParsedAddress` objects with decomposed fields (`street_prefix`, `street_name`, `house_number`, `location_info`). For the review UI, we need reassembled strings.

**Stored per-row format in job result:**
```python
{
    "index": 0,
    "original": {"street": "Via Roam 15", "city": "Milano", "zip": "20100"},
    "parsed": {"street": parsed_addr.full_street, "city": "Milano", "zip": "20100"},
    "parsed_components": {
        "street_prefix": parsed_addr.street_prefix,
        "street_name": parsed_addr.street_name,
        "house_number": parsed_addr.house_number,
        "location_info": parsed_addr.location_info,
        "country_code": parsed_addr.country_code,
    },
    "method": "ai",
    "changed": True,
    "changes": ["street: Via Roam 15 → Via Roma 15"]
}
```

- `parsed.street` uses `ParsedAddress.full_street` (the reassembled string) for display
- `parsed_components` stores the raw components for Phase 2
- User edits target the reassembled `street` string (not individual components)

**When user edits a row:** The edited `street` string replaces `parsed.street`. Since Phase 2 needs a `ParsedAddress`, the edited street is re-parsed with regex (`parse_single_regex`) to decompose it back into components. This is fast and local — no API call needed.

### Phase 1: AI Parsing (in validator router)

The existing `_process_validation` function is split into two parts:

**`_process_parse(job_id, excel_bytes, confidence, street_confidence, pin_valid, client_ip)`**
- Reads Excel, validates content, checks rate limits
- Runs `AddressParser.parse_all()` (Claude + regex fallback)
- For each row, builds the per-row format above using `ParsedAddress.full_street` for display and storing raw components
- Stores the original `excel_bytes` on disk: `job_store.save_file(job_id, "original.xlsx", excel_bytes)`
- Stores parsing results on the job: `job_store.update_status(job_id, "parsed", result={...})`
- Does NOT call Google API

**`_process_validate(job_id, confirmed_rows, confidence, street_confidence, pin_valid, client_ip)`**
- Receives the confirmed parsed rows (with user edits applied)
- Loads original Excel from disk: `job_store.get_file_path(job_id, "original.xlsx")`
- **Bypasses `ZipValidator.process_dataframe()` parsing step.** Instead:
  1. Creates `ZipValidator` instance
  2. Builds a list of `ParsedAddress` objects from `confirmed_rows[i].parsed_components` (or re-parses edited rows with `parse_single_regex`)
  3. Calls `ZipValidator._validate_addresses(df, parsed_addresses, progress_callback)` — a new internal method extracted from `process_dataframe()` that takes pre-parsed addresses and runs only the Google validation + correction logic
- Generates corrected Excel + review report
- Records API usage
- Updates job to "complete" with final results

### ZipValidator change: extract `_validate_addresses`

`ZipValidator.process_dataframe()` currently does parsing + validation in one pass. Extract the validation-only logic into a new method:

```python
def _validate_addresses(self, df, parsed_addresses, progress_callback=None):
    """Run Google validation on pre-parsed addresses. Skips parsing step."""
    # ... existing validation logic from process_dataframe, starting after parse_all()
```

`process_dataframe()` is refactored to call `parse_all()` then `_validate_addresses()`. This is a safe refactor — no behavior change for existing callers.

### Phase 2 trigger: confirm endpoint

```python
@router.post("/jobs/{job_id}/confirm")
async def confirm_validation(job_id: str, body: ConfirmRequest):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(404, ...)
    if status["status"] != "parsed":
        raise HTTPException(409, detail="Job is not in parsed state")

    # Apply user edits to parsed rows
    parsed_rows = status["result"]["rows"]
    for idx_str, edits in body.edits.items():
        idx = int(idx_str)
        row = next((r for r in parsed_rows if r["index"] == idx), None)
        if row:
            row["parsed"].update(edits)
            # Re-decompose edited street into components via regex
            if "street" in edits:
                from ..core.address_parser import AddressParser
                re_parsed = AddressParser().parse_single_regex(
                    edits["street"], row["parsed"].get("city", ""), row["parsed"].get("zip", "")
                )
                row["parsed_components"] = {
                    "street_prefix": re_parsed.street_prefix,
                    "street_name": re_parsed.street_name,
                    "house_number": re_parsed.house_number,
                    "location_info": re_parsed.location_info,
                    "country_code": re_parsed.country_code,
                }
            row["edited"] = True

    # Handle retry_regex_rows
    if body.retry_regex_rows:
        job_store.update_status(job_id, "processing_parse")  # Brief re-parse status
        # Retry is done inside _process_validate before Google validation starts

    job_store.update_status(job_id, "processing_validate")

    # Get stored config from job
    job_data = status.get("config", {})

    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None, _process_validate, job_id, parsed_rows,
        job_data.get("confidence", 90), job_data.get("street_confidence", 85),
        job_data.get("pin_valid", False), job_data.get("client_ip", "unknown"),
        body.retry_regex_rows,
    )

    return {"ok": True, "data": {"status": "processing_validate"}}
```

### Pydantic schema for confirm

```python
class ConfirmRequest(BaseModel):
    edits: dict[str, dict[str, str]] = {}  # row_index -> field overrides
    retry_regex_rows: bool = False
```

### Retry logic for regex rows

Happens inside `_process_validate` (in background thread), before Google validation:

```python
def _process_validate(job_id, parsed_rows, confidence, street_confidence, pin_valid, client_ip, retry_regex):
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
                    row["parsed_components"] = { ... }
                    row["method"] = "ai"  # upgraded
            except Exception:
                pass  # Keep regex results, proceed

    # Now run Google validation with confirmed parsed addresses
    ...
```

This runs in a thread, so the 2s retry sleep in `parse_all` is acceptable. Progress updates during retry use `job_store.update_progress`.

## 5. Frontend Type Changes

`JobStatus` in `types.ts` needs new status values:
```typescript
type JobStatusValue = "processing_parse" | "parsed" | "processing_validate" | "complete" | "failed"
```

`useJobPolling` hook needs to:
- Stop polling on `"parsed"` (not just `"complete"` / `"failed"`) — the review step needs the data
- Resume polling after confirm is called (status changes to `"processing_validate"`)

New types for the parsed result and confirm request:
```typescript
interface ParsedRow {
  index: number
  original: { street: string; city: string; zip: string }
  parsed: { street: string; city: string; zip: string }
  parsed_components: { street_prefix: string; street_name: string; house_number: string; location_info: string; country_code: string }
  method: "ai" | "regex"
  changed: boolean
  changes: string[]
  edited?: boolean
}

interface ParsingSummary {
  total: number
  ai_parsed: number
  regex_fallback: number
  ai_modified: number
  unchanged: number
}

interface ConfirmRequest {
  edits: Record<string, Record<string, string>>
  retry_regex_rows: boolean
}
```

## 6. Address Parser Retry Improvement

In `address_parser.py`, add application-level retry before regex fallback:

```python
except Exception as e:
    logger.warning(f"Batch at {start_idx} failed: {e}, retrying in 2s...")
    time.sleep(2)
    try:
        batch_results = self._parse_batch_claude(batch, start_idx)
        for i, parsed in enumerate(batch_results):
            results[start_idx + i] = parsed
    except Exception as e2:
        logger.error(f"Batch at {start_idx} retry failed, falling back to regex")
        for i, addr in enumerate(batch):
            results[start_idx + i] = self.parse_single_regex(...)
            self.metrics.regex_fallback += 1
```

Also set `max_retries=3` on the Anthropic client constructor.

## 6. Edge Cases

**100% regex fallback (Claude fully down):**
Review step shows warning banner only, no modified rows section. User can retry or proceed.

**User edits preserved on retry:**
When "Riprova con AI" is clicked, user edits to non-regex rows are preserved. Only regex-fallback rows are re-parsed.

**Retry also fails:**
Show "AI ancora non disponibile. Procedi con validazione Google." Remove retry button.

**Confirm endpoint timeout:**
Phase 2 runs async (same job pattern). Confirm returns immediately, frontend polls.

**Job expires between phase 1 and phase 2:**
If user takes too long to review (>1 hour TTL), job expires. Frontend handles 404 with "Job scaduto, ricaricare il file."

## 7. Results Page Addition

Step 4 (Risultato) adds a per-row quality indicator:
- 🤖 = AI-parsed (higher confidence)
- ⚙️ = Regex-parsed (verify manually)

This is shown as an additional column in the results table, visible in both simple and full views.
