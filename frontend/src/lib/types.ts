// --- Common ---

export interface JobCreatedResponse {
  job_id: string
}

export interface JobProgress {
  current: number
  total: number
  message: string
}

export interface JobStatus<T = unknown> {
  status: "processing" | "processing_parse" | "parsed" | "processing_validate" | "complete" | "failed"
  job_type: string
  progress: JobProgress | null
  result: T | null
  error: string | null
  config?: Record<string, unknown>
}

// --- Parsed Address Types (Validator Phase 1) ---

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

// --- Label Sorter ---

export interface LabelUnmatchedDetail {
  page: number
  tracking: string
  carrier: string
  reason: string
}

export interface LabelJobResult {
  total_pages: number
  matched: number
  unmatched: number
  match_rate: number
  unmatched_details: LabelUnmatchedDetail[]
  files: {
    pdf: string
    csv: string
  }
}

export type LabelJobStatus = JobStatus<LabelJobResult>

// --- Address Validator ---

export interface ValidatorResultRow {
  status: "verified" | "corrected" | "review"
  city: string
  street: string
  original_zip: string
  suggested_zip: string | null
  suggested_street: string | null
  corrections: string[]
  parse_method?: "ai" | "regex"
}

export interface ValidatorJobResult {
  total_rows: number
  valid_count: number
  corrected_count: number
  review_count: number
  skipped_count: number
  street_verified_count: number
  street_corrected_count: number
  po_invalid_count: number
  results: ValidatorResultRow[]
  files: {
    corrected: string
    review: string
  }
}

export type ValidatorJobStatus = JobStatus<ValidatorJobResult>

// --- Address Book ---

export interface Address {
  id: string
  name: string
  company: string
  contact_name: string
  street: string
  zip: string
  city: string
  province: string
  reference: string
  is_default: boolean
}

export interface AddressCreate {
  name: string
  company: string
  contact_name?: string
  street: string
  zip_code: string
  city: string
  province?: string
  reference?: string
  is_default?: boolean
}

export interface AddressUpdate {
  name?: string
  company?: string
  contact_name?: string
  street?: string
  zip_code?: string
  city?: string
  province?: string
  reference?: string
}

// --- Pickup Request ---

export interface PickupRequestData {
  carrier: "FedEx" | "DHL" | "UPS"
  pickup_date: string          // ISO date: "2026-03-20"
  time_start: string           // ISO time: "09:00:00"
  time_end: string             // ISO time: "17:00:00"
  company: string
  contact_name: string
  address: string
  zip_code: string
  city: string
  province: string
  reference: string
  num_packages: number
  weight_per_package: number
  length: number
  width: number
  height: number
  use_pallet: boolean
  num_pallets: number
  pallet_length: number
  pallet_width: number
  pallet_height: number
  notes: string
}

export interface PickupResponse {
  message: string
}

// --- Health ---

export interface HealthData {
  version: string
}

// --- Usage Stats (Address Validator) ---

export interface UsageStats {
  rows_used: number
  rows_limit: number
  rows_remaining: number
  reset_at: string             // ISO datetime
}
