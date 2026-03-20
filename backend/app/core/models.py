"""Data models for the address validation pipeline."""
from dataclasses import dataclass, field


@dataclass
class ParsedAddress:
    """Structured address parsed by Claude or regex fallback."""
    street_prefix: str       # "Via", "Piazza", "Corso", etc.
    street_name: str         # "Roma", "4 Novembre", "25 Aprile"
    house_number: str        # "11/A", "SNC", "", "KM 5"
    location_info: str       # "C.C. Le Grange", ""
    country_code: str        # "IT", "DE", "FR"
    confidence: str          # "high", "medium", "low"
    parse_method: str = "ai"  # "ai" or "regex"

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


@dataclass
class ValidationOutcome:
    """Result of validating a single address via Google Address Validation API."""
    # Verdict
    status: str              # "valid", "corrected", "review"
    action: str              # raw API possibleNextAction: ACCEPT/CONFIRM/FIX

    # ZIP
    input_zip: str
    output_zip: str          # from API response
    zip_confirmed: bool
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
    reasons: list[str] = field(default_factory=list)
    formatted_address: str = ""

    # Location info
    location_info: str = ""


@dataclass
class ParsingMetrics:
    """Observability metrics for Claude address parsing."""
    claude_parsed: int = 0
    claude_failed_verify: int = 0
    regex_fallback: int = 0
    batch_failures: int = 0
    batch_retries_succeeded: int = 0
    prompt_version: str = ""
