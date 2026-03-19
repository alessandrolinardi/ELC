# Address Validator Redesign: Claude Parsing + Google Address Validation API

**Date:** 2026-03-17
**Status:** Draft
**Scope:** Replace the address validation pipeline in `src/zip_validator.py` with Claude-powered address parsing and Google Address Validation API.

---

## 1. Problem Statement

The current address validator has accumulated complexity that makes it fragile and hard to maintain:

- **5 redundant house number preservation safeguards** across `zip_validator.py` and `app.py`, each doing the same regex-based string surgery because the core logic isn't reliable.
- **3 geocoding APIs** (Google Geocoding, Photon, Nominatim) with ~350 lines of fallback orchestration. When Google Maps is configured, Photon and Nominatim are never used.
- **~300 lines of custom confidence scoring** (digit-counting, transposition detection, adjacent-swap detection) to work around the Geocoding API not being designed for address validation.
- **Regex-based address parsing** that fails on edge cases: "Via 4 Novembre 7" (number in street name), "SNC" (no house number), "C.C. Le Grange Via Roma 1" (location prefix).
- **ZIP code validation that's unreliable** — heuristic-based country detection, hardcoded city ranges, letter-to-digit replacement with questionable mappings (z→2, g→9).

The file is 2282 lines and growing.

## 2. Solution Overview

Two changes that reinforce each other:

1. **Claude as address preprocessor** — Parse raw address strings into structured fields (street prefix, street name, house number, location info, country code) before validation. Eliminates regex parsing and the entire house-number-preservation problem.

2. **Google Address Validation API** (replacing Geocoding API + Photon + Nominatim) — Purpose-built for address validation. Returns per-component confirmation levels and correction flags instead of raw coordinates that we reverse-engineer.

### Architecture

```
Excel upload
    → Read ZIP as string (dtype=str), pad to 5 digits
    → Claude batch parse addresses → list[ParsedAddress]
         (fallback: regex if Claude unavailable)
    → Google Address Validation API per address
    → Interpret verdict + input-vs-output comparison
    → Cross-check ZIP with ITALIAN_PROVINCE_ZIP mapping
    → Output Excel with text-formatted ZIP cells
```

## 3. Data Model

### ParsedAddress

```python
@dataclass
class ParsedAddress:
    street_prefix: str       # "Via", "Piazza", "Corso", etc.
    street_name: str         # "Roma", "4 Novembre", "25 Aprile"
    house_number: str        # "11/A", "SNC", "", "KM 5"
    location_info: str       # "C.C. Le Grange", ""
    country_code: str        # "IT", "DE", "FR"
    confidence: str          # "high", "medium", "low"

    @property
    def street_with_number(self) -> str:
        """Street WITH house number — sent to Address Validation API."""
        parts = [self.street_prefix, self.street_name, self.house_number]
        return " ".join(p for p in parts if p)

    @property
    def street_without_number(self) -> str:
        """Street name only — used for comparison with API results."""
        parts = [self.street_prefix, self.street_name]
        return " ".join(p for p in parts if p)

    @property
    def full_street(self) -> str:
        """Full original street including location info — for display."""
        parts = [self.location_info, self.street_prefix, self.street_name, self.house_number]
        return " ".join(p for p in parts if p)
```

**Key principle:** House number is a separate field throughout the pipeline. It is never parsed from, compared against, or reconstructed into a street string during validation. It only appears in output via `full_street` or explicit concatenation.

### ValidationOutcome

```python
@dataclass
class ValidationOutcome:
    # Verdict
    status: str              # "valid", "corrected", "review"
    action: str              # raw API possibleNextAction: ACCEPT/CONFIRM/FIX

    # ZIP
    input_zip: str
    output_zip: str          # from API response
    zip_confirmed: bool      # API confirmationLevel == CONFIRMED
    zip_corrected: bool      # input_zip != output_zip

    # Street
    input_street: str        # original street from Excel
    output_street: str       # corrected street from API
    street_confirmed: bool
    street_corrected: bool   # detected via input-vs-output comparison
    silent_correction: bool  # API changed street but didn't flag it

    # House number
    house_number: str        # from ParsedAddress, never touched

    # Details
    granularity: str         # PREMISE, ROUTE, OTHER
    address_complete: bool
    reasons: list[str]       # human-readable list of what happened
    formatted_address: str   # Google's formatted output

    # Location info
    location_info: str       # C.C. etc. from Claude or API point_of_interest
```

## 4. Claude Address Parser

### 4a. Structured Output via tool_use

Claude is called with a tool definition that enforces the output schema:

```python
PARSE_TOOL = {
    "name": "parsed_addresses",
    "description": "Parse raw addresses into structured components",
    "input_schema": {
        "type": "object",
        "properties": {
            "addresses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "street_prefix": {"type": "string"},
                        "street_name": {"type": "string"},
                        "house_number": {"type": "string"},
                        "location_info": {"type": "string"},
                        "country_code": {"type": "string"},
                        "confidence": {"enum": ["high", "medium", "low"]}
                    },
                    "required": ["index", "street_prefix", "street_name",
                                 "house_number", "country_code", "confidence"]
                }
            }
        },
        "required": ["addresses"]
    }
}
```

**Model:** `claude-sonnet-4-6` — reliable structured extraction, good balance of accuracy and speed.

**Batching:** 50 addresses per request, parallelized with `concurrent.futures.ThreadPoolExecutor`. For 400 addresses: 8 requests, ~10-15 seconds total.

**Prompt:** System prompt with Italian address rules and examples. Includes rules for:
- Street names containing numbers: "Via 4 Novembre 7" → name="4 Novembre", house_number="7"
- SNC: "Via Roma SNC" → house_number="SNC"
- Location prefixes: "C.C. Le Grange Via Roma 1" → location_info="C.C. Le Grange"
- Country detection from ZIP format, city name, street language
- Abbreviation expansion: "V." = "Via", "P.zza" = "Piazza", "C.so" = "Corso"

### 4b. Output Verification

Every parsed result is verified before use:

```python
def _verify_parsing(self, original: str, parsed: ParsedAddress) -> bool:
    """Sanity check: parsed parts should reconstruct to the original."""
    reconstructed = parsed.full_street
    norm_original = normalize(original)
    norm_reconstructed = normalize(reconstructed)

    original_words = set(norm_original.split())
    reconstructed_words = set(norm_reconstructed.split())

    missing = original_words - reconstructed_words
    return len(missing) <= 1  # allow 1 word difference for abbreviations
```

If verification fails: fall back to regex for that address.

### 4c. Three-Tier Fallback

```
Tier 1: Claude API → structured output → verify → ParsedAddress
           ↓ (verification fails for this address)
Tier 2: Regex fallback → _extract_house_number → ParsedAddress
           ↓ (Claude API call fails for this batch)
Tier 3: Regex fallback for entire batch
```

- **Batch failure:** Retry once, then regex for that batch. Continue remaining batches via Claude.
- **Single address verification failure:** Regex for that address only. Log to metrics.
- **API key missing:** Regex for everything. Zero regression from current behavior.

### 4d. Caching

Both Claude parsing and Google API results are cached in the existing Supabase `address_cache` table with additional columns:

```
Existing columns:
  street_hash, city_normalized, original_street, original_city,
  validated_zip, validated_street, confidence, times_used,
  created_at, updated_at, expires_at

New columns:
  parsed_prefix        -- Claude: street prefix ("Via")
  parsed_name          -- Claude: street name ("Roma")
  parsed_house_number  -- Claude: house number ("11/A")
  parsed_location_info -- Claude: location info ("C.C. Le Grange")
  parsed_country_code  -- Claude: country code ("IT")
  prompt_version       -- Claude: prompt version for invalidation
  api_status           -- Google: "valid", "corrected", "review"
  api_formatted        -- Google: formattedAddress
  api_granularity      -- Google: validationGranularity
  api_reasons          -- Google: JSON array of reason strings
```

**Cache key:** Same as current — normalized `street + city` hash (via `_get_cache_key`).

**Cache hit flow:**
1. Lookup by cache key
2. If found AND `prompt_version` matches current → skip both Claude AND Google calls
3. If found but `prompt_version` is stale → re-run Claude parsing, re-run Google validation
4. If not found → full pipeline (Claude + Google)

**TTL:** 90 days (unchanged). Addresses don't change often.

**Cache write:** Only for results where `api_status` is "valid" or "corrected" (high confidence). "Review" results are not cached — they should be re-validated each time.

### 4e. Prompt Versioning

```python
PROMPT_VERSION = "v1"
```

Cached parsed results store the prompt version. On cache lookup, if version doesn't match current, treat as cache miss and re-parse. Ensures prompt improvements propagate.

### 4e. Observability

```python
@dataclass
class ParsingMetrics:
    claude_parsed: int = 0
    claude_failed_verify: int = 0
    regex_fallback: int = 0
    batch_failures: int = 0
    prompt_version: str = ""
```

Displayed in the existing debug expander in the Streamlit UI.

### 4f. Test Harness

File: `data/address_parsing_tests.json`

Seeded with ~50 edge cases:

```json
[
    {"input": "C.C. Le Grange Via 4 Novembre 11/A", "city": "Torino",
     "expected": {"street_prefix": "Via", "street_name": "4 Novembre",
                  "house_number": "11/A", "location_info": "C.C. Le Grange"}},
    {"input": "Via 25 Aprile 3", "city": "Milano",
     "expected": {"street_prefix": "Via", "street_name": "25 Aprile",
                  "house_number": "3"}},
    {"input": "Via Roma SNC", "city": "Roma",
     "expected": {"street_prefix": "Via", "street_name": "Roma",
                  "house_number": "SNC"}},
    {"input": "Strada Statale 16 KM 5", "city": "Bari",
     "expected": {"street_prefix": "Strada Statale", "street_name": "16",
                  "house_number": "KM 5"}}
]
```

Both Claude and regex are evaluated against this set. `claude_failed_verify` events from production are candidates for the test set.

## 5. Google Address Validation API

### 5a. Request Format

```python
def _validate_address(self, parsed: ParsedAddress, city: str,
                       zip_code: str, state: str = "") -> dict:
    payload = {
        "address": {
            "regionCode": parsed.country_code,
            "locality": city,
            "postalCode": zip_code,  # always 5-digit padded string
            "addressLines": [parsed.street_with_number],
            "administrativeArea": state
        }
    }

    response = self.session.post(
        "https://addressvalidation.googleapis.com/v1:validateAddress",
        params={"key": self.google_api_key},
        json=payload,
        timeout=10
    )
    return response.json()
```

**Full address with house number** is sent to the API. The API handles house numbers well (test 4: "11/A" preserved, test 10: "SNC" accepted). House number protection happens at the comparison stage, not the query stage.

### 5b. Verdict Interpretation

Based on 12 real API tests against Italian addresses:

```python
IGNORABLE_MISSING = {"street_number", "subpremise", "administrative_area_level_3"}

def _interpret_verdict(self, verdict: dict, address: dict,
                        parsed: ParsedAddress, input_zip: str) -> ValidationOutcome:
    action = verdict.get("possibleNextAction", "")
    granularity = verdict.get("validationGranularity", "")
    missing = address.get("missingComponentTypes", [])

    # --- Step 1: Override FIX for missing house number ---
    critical_missing = [m for m in missing if m not in IGNORABLE_MISSING]

    if action == "FIX" and not critical_missing:
        has_suspicious = any(
            comp.get("confirmationLevel") == "UNCONFIRMED_AND_SUSPICIOUS"
            for comp in address.get("addressComponents", [])
        )
        has_unresolved = bool(address.get("unresolvedTokens"))

        if has_suspicious or has_unresolved or granularity == "OTHER":
            action = "FIX"      # genuine problem
        else:
            action = "CONFIRM"  # just missing house number

    # --- Step 2: Detect silent corrections ---
    route_comp = next(
        (c for c in address.get("addressComponents", [])
         if c["componentType"] == "route"), None
    )

    silent_correction = False
    if route_comp and parsed:
        api_street = route_comp["componentName"]["text"]
        original_street = parsed.street_without_number
        if api_street.lower().strip() != original_street.lower().strip():
            silent_correction = True

    # --- Step 3: Detect locality mismatch ---
    api_admin3 = next(
        (c["componentName"]["text"] for c in address.get("addressComponents", [])
         if c["componentType"] == "administrative_area_level_3"), None
    )
    locality_mismatch = False
    if api_admin3 and city:
        if api_admin3.lower().strip() != city.lower().strip():
            locality_mismatch = True
            reasons.append(f"Address matched to {api_admin3}, not {city}")

    # --- Step 4: Detect ZIP changes ---
    output_zip = next(
        (c["componentName"]["text"] for c in address.get("addressComponents", [])
         if c["componentType"] == "postal_code"), None
    )
    zip_changed = output_zip and output_zip != input_zip

    # --- Step 5: Determine status ---
    zip_unconfirmed = any(
        c.get("componentType") == "postal_code"
        and c.get("confirmationLevel") == "UNCONFIRMED_BUT_PLAUSIBLE"
        for c in address.get("addressComponents", [])
    )

    if action == "FIX":
        status = "review"
    elif locality_mismatch and zip_unconfirmed:
        # Wrong municipality + unconfirmed ZIP = likely wrong address
        status = "review"
    elif action == "CONFIRM" or silent_correction or zip_changed:
        if (verdict.get("hasReplacedComponents")
            or verdict.get("hasSpellCorrectedComponents")
            or silent_correction
            or zip_changed):
            status = "corrected"
        elif verdict.get("hasInferredComponents"):
            status = "corrected"
        else:
            status = "valid"
    else:  # ACCEPT
        if silent_correction or zip_changed:
            status = "corrected"
        elif verdict.get("hasSpellCorrectedComponents"):
            status = "corrected"
        elif locality_mismatch:
            # Surface as warning but don't block — metro area match is OK
            status = "valid"  # reasons list already has the warning
        else:
            status = "valid"

    return status
```

### 5c. ZIP Cross-Check with Province Mapping

The Address Validation API's Italian ZIP validation is weak (tests 2, 9: accepts 20199 and 99999 as "plausible"). After API validation, cross-check with the existing province mapping:

```python
if output_zip and state:
    province_valid, msg = self._validate_zip_province(output_zip, state)
    if not province_valid:
        status = "review"
        reasons.append(f"ZIP {output_zip} doesn't match province {state}")
```

**Retained from current codebase:** `ITALIAN_PROVINCE_ZIP` dictionary and `_validate_zip_province` method.

### 5d. Rate Limits and Performance

Google Address Validation API allows 6,000 QPM (100 QPS). At our 1,000 addresses/day cap, no throttling is needed. Add a configurable `max_qps` parameter (default: 50) as a safety valve in case Google reduces quotas.

API calls are sequential (one address at a time). At ~200ms per call, 400 addresses takes ~80 seconds — comparable to current performance. **Future optimization:** parallelize with `ThreadPoolExecutor` + rate limiter if latency becomes an issue.

### 5e. Error Handling

| Failure | Behavior |
|---------|----------|
| No Google API key | Validation disabled. User sees clear error message. |
| Google quota exceeded (RESOURCE_EXHAUSTED) | Back off 5 seconds, retry. If still failing, stop validation and show partial results. |
| Google timeout (per address) | Retry once. If still fails, mark as "review" with reason "API unavailable". |
| Google 4xx/5xx (per address) | Mark as "review" with reason. Continue with remaining addresses. |

### 5e. Test Results Reference

| # | Input | Verdict | Granularity | Key behavior |
|---|-------|---------|-------------|-------------|
| 1 | Correct address, Milano | ACCEPT | PREMISE | ZIP UNCONFIRMED_BUT_PLAUSIBLE (Milano suburb matching) |
| 2 | Wrong ZIP 20199 | ACCEPT | PREMISE | API accepts invalid ZIP without correcting |
| 3 | Typo "roam" | ACCEPT | PREMISE | spellCorrected=true, but still ACCEPT |
| 4 | House number 11/A | ACCEPT | PREMISE | Fractional house number preserved |
| 5 | C.C. prefix, Torino | CONFIRM | PREMISE | API separates C.C. as point_of_interest, corrects ZIP 10100→10123 |
| 6 | Via→Piazza, with house# | ACCEPT | PREMISE | Silent correction, no flags |
| 7 | Fake street | FIX | OTHER | Correctly flagged |
| 8 | Small town, no house# | FIX | OTHER | Route unconfirmed even for "Via Roma" |
| 9 | Wrong ZIP + typo | FIX | ROUTE | 99999 is "plausible", spell correction works |
| 10 | SNC | ACCEPT | ROUTE | "snc" treated as literal street_number |
| 11 | Truncated ZIP "187" | ACCEPT | PREMISE | API pads to "00187", no flags |
| 12 | Correct ZIP "00187" | ACCEPT | PREMISE | Identical to test 11 (control) |

## 6. ZIP Code Handling

ZIP codes must be strings with preserved leading zeros at every stage.

### 6a. Input

```python
# Read Excel forcing ZIP column to string (prevents pandas numeric conversion)
df = pd.read_excel(file, dtype={zip_col: str})
```

ZIP padding to 5 digits happens AFTER Claude detects the country code, and only for Italian addresses:

```python
# Inside process_dataframe, after Claude parsing
if parsed.country_code == "IT":
    zip_padded = str(int(float(str(original_zip)))).zfill(5)
else:
    zip_padded = str(original_zip).strip()
```

The `int(float(str(x)))` chain handles: "00187" (string), 187 (int), 187.0 (float from pandas). Non-Italian ZIPs (e.g., "SW1A 1AA", "1234AB") are left untouched.

### 6b. Processing

The Address Validation API receives the padded 5-digit string and returns the correct ZIP (test 11: "187" → "00187"). The API's returned ZIP is used as the output value.

### 6c. Output

```python
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name='Corrected')
    ws = writer.sheets['Corrected']

    # Re-write ZIP cells as explicit text strings with leading zeros
    for row in range(2, len(df) + 2):
        cell = ws.cell(row=row, column=zip_col_idx)
        cell.number_format = '@'  # Text format
        raw = cell.value
        if raw is not None:
            cell.value = str(int(float(str(raw)))).zfill(5)
```

Both the number format (`@` = Text) AND the cell value must be set explicitly. Setting only the format doesn't restore already-lost zeros.

## 7. Street 2 / Location Info Handling

Both Claude and the Address Validation API extract location info (e.g., "C.C. Le Grange"). We intentionally keep both for safety:

- **Claude** extracts `location_info` during preprocessing (needed for verification and regex fallback)
- **API** returns `point_of_interest` component (test 5: separates it into `addressLines[0]`)

For Street 2 output, prefer the API's `point_of_interest` value if present, fall back to Claude's `location_info`:

```python
location = api_point_of_interest or parsed.location_info or ""
```

| Street 1 | Street 2 (existing) | Location info | Action |
|----------|-----------|---------------|--------|
| "C.C. Le Grange Via Roma 1" | empty | "C.C. Le Grange" | Write location_info to Street 2 |
| "Via Roma 1" | "Scala B, Int. 3" | "" | Keep Street 2 unchanged |
| "C.C. Le Grange Via Roma 1" | "Scala B" | "C.C. Le Grange" | Append with " - " separator: "Scala B - C.C. Le Grange" |

## 7b. Non-Italian Address Handling

Non-Italian addresses (detected by Claude's `country_code` or the Excel `Country` column) skip validation entirely:

```python
if parsed.country_code not in ("IT",):
    result = ValidationResult(
        status="valid",
        reason=f"Non-IT country ({parsed.country_code}) - skipped",
        ...
    )
    skipped_count += 1
    continue
```

This matches current behavior. No API calls are made for non-IT addresses.

## 7c. Progress Bar in Two-Step Flow

The progress bar accounts for both phases:

```python
# Phase 1: Claude parsing (0-20% of progress bar)
progress_callback(0, 100, "Parsing addresses with AI...")
parsed_addresses = self.address_parser.parse_all(raw_addresses)
progress_callback(20, 100, "Parsing complete")

# Phase 2: API validation (20-100% of progress bar)
for i, (idx, row) in enumerate(df.iterrows()):
    pct = 20 + int((i + 1) / total * 80)
    progress_callback(pct, 100, f"Validating address {i + 1}/{total}...")
```

## 8. Pipeline Integration

### 8a. Revised process_dataframe

Uses existing `_map_columns` method (unchanged) to find ZIP, street, city, country, phone, COD, and order number columns.

```python
def process_dataframe(self, df, progress_callback=None):
    col_map = self._map_columns(df)

    # Step 0: Read and pad ZIPs
    zip_col = col_map.get('zip')
    df[zip_col] = pad_zip_column(df[zip_col])

    # Step 1: Claude batch parse all addresses
    raw_addresses = self._extract_raw_addresses(df)
    parsed_addresses = self.address_parser.parse_all(raw_addresses)

    # Step 2: Validate each address
    for i, (idx, row) in enumerate(df.iterrows()):
        parsed = parsed_addresses[i]

        # Send full address (with house number) to API
        api_result = self._validate_address(
            parsed, city, zip_padded, state
        )

        # Interpret verdict + detect silent corrections
        outcome = self._interpret_verdict(
            api_result["result"]["verdict"],
            api_result["result"]["address"],
            parsed,
            zip_padded
        )

        # Cross-check ZIP with province mapping
        if outcome.output_zip and state:
            province_valid, msg = self._validate_zip_province(
                outcome.output_zip, state
            )
            if not province_valid:
                outcome.status = "review"
                outcome.reasons.append(msg)

        # Build final street: API's corrected name + original house number
        if outcome.street_corrected:
            suggested_street = f"{outcome.output_street} {parsed.house_number}".strip()
        else:
            suggested_street = None

        # Handle location info → Street 2
        if parsed.location_info:
            # Write to Street 2 column
            ...
```

### 8b. House Number Preservation

With `ParsedAddress`, house number preservation is one line:

```python
suggested_street = f"{api_corrected_street_name} {parsed.house_number}".strip()
```

No safeguards needed. The house number was extracted by Claude at the start and never entered the validation pipeline. It's reattached at the end.

### 8c. Output Sanitization

Both output Excel files sanitize strings to prevent formula injection:

```python
for col in df.columns:
    df[col] = df[col].apply(
        lambda x: "'" + str(x)
        if isinstance(x, str) and x and x[0] in ('=', '+', '-', '@')
        else x
    )
```

## 9. What Gets Deleted

| Code | Lines | Reason |
|------|-------|--------|
| `_query_photon` | ~90 | API removed |
| `_query_nominatim` | ~60 | API removed |
| `_query_address` orchestration | ~150 | Replaced by single `_validate_address` |
| `_search_streets_in_city` | ~25 | Used Nominatim |
| `_search_similar_streets` | ~70 | Replaced by API verdict |
| `_string_similarity` | ~45 | Replaced by input-vs-output comparison |
| `_normalize_street` | ~30 | Replaced by Claude structured fields |
| `_extract_location_prefix` | ~60 | Claude + API point_of_interest |
| `_extract_street_name` | ~20 | Claude does this |
| `detect_country_code` | ~100 | Claude does this |
| `preprocess_dataframe` | ~50 | Claude does this |
| `_build_street_suggestion` | ~35 | Structured fields eliminate need |
| 4 house number safeguards | ~80 | Structured fields eliminate need |
| `_clean_zip_code` | ~50 | API handles padding + correction |
| `_count_different_digits` | ~10 | API verdict replaces |
| `_is_transposition` | ~10 | API verdict replaces |
| `_is_adjacent_swap` | ~15 | API verdict replaces |
| `_looks_like_valid_italian_street` | ~20 | API verdict replaces |
| `ITALIAN_CAP_RANGES` | ~10 | Not needed with API + province check |
| `validate_address` (old) | ~260 | Replaced by `_validate_address` + `_interpret_verdict` |
| `validate_zip` (compat wrapper) | ~10 | No longer needed |
| `fix_suggested_street` in app.py | ~35 | No longer needed |
| Photon tracking state | ~20 | API removed |

**Total deleted: ~800 lines**

## 10. What Gets Added

| Code | Lines (est.) | Purpose |
|------|-------------|---------|
| `ParsedAddress` dataclass | ~30 | Structured address fields |
| `ValidationOutcome` dataclass | ~25 | Structured validation result |
| `AddressParser` (Claude integration) | ~120 | Batch parsing, verification, fallback |
| `_validate_address` (Google API) | ~30 | Address Validation API call |
| `_interpret_verdict` | ~60 | Verdict logic with FIX override + silent correction detection |
| `_parse_validation_response` | ~40 | Extract components from API response |
| `ParsingMetrics` | ~15 | Observability |
| ZIP padding utilities | ~15 | Input/output ZIP handling |
| Test harness data | ~50 | JSON test cases |

**Total added: ~385 lines + test data**

**Net: 2282 → ~1860 lines** (and much simpler logic).

## 11. What Stays (unchanged or minimal changes)

- `ITALIAN_PROVINCE_ZIP` mapping + `_validate_zip_province` — moved to `data/italian_zip_provinces.json`, loaded at startup (matches existing `data/valid_po_numbers.json` pattern)
- `_extract_house_number` — kept as Tier 2/3 regex fallback
- `_map_columns` — column mapping logic
- `generate_corrected_excel` — simplified (no house number safeguards, added ZIP text formatting)
- `generate_review_report` — simplified (no house number safeguards)
- `_query_google` (renamed to `_validate_address`) — different API, similar HTTP pattern
- PO number validation (`validate_po_number`, `extract_po_from_string`, `_valid_po_numbers`) — unchanged
- Phone default filling (`DEFAULT_PHONE = "393445556667"` for empty phone fields) — unchanged
- COD normalization (Cash on Delivery always set to 0) — unchanged
- Rate limiting in `src/security.py` — unchanged
- Address book in `src/address_book.py` — unchanged
- All app.py UI code — simplified (remove `fix_suggested_street`)

## 12. Deployment: Streamlit Cloud → Render

The app moves from Streamlit Cloud to Render as part of this redesign.

### Render Configuration

- **Service type:** Web Service
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
- **Environment variables:** Set via Render dashboard (replaces Streamlit secrets)
  - `ANTHROPIC_API_KEY`
  - `GOOGLE_ADDRESS_VALIDATION_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `ZAPIER_WEBHOOK_URL`
  - `BYPASS_PIN`

### Secrets Access Pattern Change

Current code uses `st.secrets["supabase"]["url"]`. On Render, secrets are env vars. Add a compatibility layer with explicit mapping (no string manipulation guessing):

```python
# src/config.py

SECRET_MAP = {
    ("supabase", "url"): "SUPABASE_URL",
    ("supabase", "key"): "SUPABASE_KEY",
    ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
    ("google", "api_key"): "GOOGLE_ADDRESS_VALIDATION_API_KEY",
    ("zapier", "webhook_url"): "ZAPIER_WEBHOOK_URL",
    ("app", "bypass_pin"): "BYPASS_PIN",
}

def get_secret(section: str, key: str) -> Optional[str]:
    """Get secret from Streamlit secrets or environment variables."""
    # Try Streamlit secrets first (for local dev)
    try:
        return st.secrets[section][key]
    except (KeyError, FileNotFoundError):
        pass
    # Fall back to env vars via explicit mapping (Render)
    env_key = SECRET_MAP.get((section, key))
    if env_key:
        return os.environ.get(env_key)
    return None
```

All secret access across the codebase (`address_book.py`, `security.py`, `zip_validator.py`, `app.py`) is updated to use `get_secret()` instead of `st.secrets` directly. This eliminates the 3 duplicate `_get_supabase_client()` functions — replaced by one shared function in `src/config.py`.

### render.yaml (Blueprint)

Place in repo root. Connect GitHub repo to Render → "New Blueprint Instance" → Render reads this file and creates the service.

```yaml
services:
  - type: web
    name: elc-tools
    runtime: python
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: >-
      streamlit run app.py
      --server.port $PORT
      --server.address 0.0.0.0
      --server.headless true
      --server.enableCORS false
      --server.enableXsrfProtection true
    healthCheckPath: /_stcore/health
    autoDeploy: true
    envVars:
      - key: PYTHON_VERSION
        value: "3.11"
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
```

**Notes:**
- `sync: false` means you set these values manually in the Render dashboard after deployment
- `healthCheckPath: /_stcore/health` is Streamlit's built-in health endpoint
- `--server.headless true` is required for non-interactive environments
- `--server.enableXsrfProtection true` preserves the existing security setting
- `autoDeploy: true` redeploys on every push to main
- The `starter` plan ($7/mo) provides enough resources for Streamlit + API calls

## 13. Migration & Rollout

### Phase 1: Shadow Mode
- Add Claude parsing alongside existing regex
- Run both, compare results, log disagreements
- No behavior change for users
- Build test harness from disagreements
- Deploy on Render alongside existing Streamlit Cloud (parallel)
- Duration: 1-2 weeks of real usage data

### Phase 2: Switch APIs
- Claude becomes primary parser (regex as fallback)
- Google Address Validation API replaces Geocoding + Photon + Nominatim
- New verdict interpretation logic
- Keep province-based ZIP cross-check
- Cut over DNS from Streamlit Cloud to Render
- User-visible change: results may differ slightly (generally better)

### Phase 3: Streamlit Cloud Redirect

Replace the Streamlit Cloud deployment with a redirect to Render. Create a `streamlit-redirect` branch that Streamlit Cloud deploys from:

```python
# app.py on streamlit-redirect branch (entire file)
import streamlit as st

RENDER_URL = "https://elc-tools.onrender.com"

st.set_page_config(page_title="ELC Tools - Redirecting...", page_icon="📦")

st.markdown(
    f'<meta http-equiv="refresh" content="3;url={RENDER_URL}">',
    unsafe_allow_html=True
)

st.markdown(f"""
# 📦 ELC Tools si è trasferito!

L'applicazione è stata spostata a un nuovo indirizzo.

Verrai reindirizzato automaticamente tra 3 secondi...

**Nuovo link:** [{RENDER_URL}]({RENDER_URL})

Aggiorna i tuoi segnalibri.
""")
```

Steps:
1. Confirm Render deployment is stable
2. Create `streamlit-redirect` branch from main
3. Replace `app.py` with redirect-only code above
4. Point Streamlit Cloud to deploy from `streamlit-redirect` branch
5. Main branch continues deploying to Render via blueprint

### Phase 4: Cleanup
- Remove dead code (~800 lines)
- Remove Photon/Nominatim imports and constants
- Remove redundant house number safeguards
- Simplify app.py (remove `fix_suggested_street`)
- After ~1 month: decommission Streamlit Cloud entirely

## 14. Configuration

### API Keys (Render env vars)

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | Claude API for address parsing | No (regex fallback) |
| `GOOGLE_ADDRESS_VALIDATION_API_KEY` | Address validation | Yes |
| `SUPABASE_URL` | Database (cache, rate limiting, address book) | Yes |
| `SUPABASE_KEY` | Database auth | Yes |
| `ZAPIER_WEBHOOK_URL` | Pickup request forwarding | Yes (for pickup feature) |
| `BYPASS_PIN` | Override PO validation + rate limits | No |

The Google Address Validation API must be enabled in the Google Cloud Console (it's a separate API from Geocoding).

### Dependencies

Add to `requirements.txt`:
- `anthropic` — Claude API client

No packages to remove — `requests` (used by Photon/Nominatim) is still needed for the Google API calls.

### Data Files

| File | Purpose | Format |
|------|---------|--------|
| `data/italian_zip_provinces.json` | Province-to-ZIP prefix mapping for cross-check | `{"TO": ["10"], "MI": ["20"], ...}` |
| `data/valid_po_numbers.json` | Valid PO numbers (existing) | `{"po_numbers": ["3501494822", ...]}` |
| `data/address_parsing_tests.json` | Test harness for Claude vs regex | Array of `{input, city, expected}` |

## 15. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Claude API unavailable | Regex fallback (Tier 2/3), zero regression |
| Google API unavailable | Mark addresses as "review", fail gracefully |
| Claude parses incorrectly | Output verification catches mismatches |
| API's Italian coverage gaps (small towns) | Province-based ZIP cross-check catches invalid ZIPs |
| Silent street corrections (Via→Piazza) | Input-vs-output comparison using Claude's structured fields |
| API accepts invalid ZIPs (99999) | Province mapping cross-check catches these |
| Excel leading-zero truncation | String dtype on read + explicit text formatting on write |
| Cost overrun | 1000 address/day limit caps both Claude and Google spend |
