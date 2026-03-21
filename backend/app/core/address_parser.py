"""
Address parser using Claude AI with regex fallback.
Parses raw address strings into structured ParsedAddress fields.
"""
import re
import time
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import ParsedAddress, ParsingMetrics

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

# Italian street type prefixes (longest first for greedy matching)
STREET_PREFIXES = [
    'strada statale', 'strada provinciale', 'strada regionale',
    'circonvallazione', 'lungotevere', 'lungomare', 'lungarno',
    'piazzale', 'piazza', 'viale', 'vicolo', 'corso', 'largo',
    'contrada', 'borgata', 'traversa', 'salita', 'discesa',
    'strada', 'via',
]

LOCATION_PREFIXES = [
    'centro commerciale', 'c.c.', 'cc ', 'c/c',
    'centro direzionale', 'c.d.', 'cd ',
    'centro servizi', 'c.s.',
    'parco commerciale', 'p.c.',
    'galleria commerciale',
    'outlet',
    'retail park',
    # Località / Frazione prefixes (common in rural Italian addresses)
    'località', 'localita', 'loc.', 'loc ',
    'frazione', 'fraz.', 'fraz ',
]

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

SYSTEM_PROMPT = """You are an Italian address parser. For each address, extract structured components.

Rules:
- street_prefix: The street type (Via, Piazza, Corso, Viale, Largo, Vicolo, Strada, etc.)
- street_name: The street name WITHOUT the house number
- house_number: The civic number at the END of the address (e.g., "10", "11/A", "SNC", "KM 5") or empty string if none
- location_info: Commercial location prefix (C.C., Centro Commerciale, etc.) or empty string
- country_code: 2-letter ISO code detected from ZIP format, city name, and street language

Critical rules for Italian addresses:
- Numbers that are part of street NAMES (dates, historical references) are NOT house numbers:
  "Via 4 Novembre 7" → street_name="4 Novembre", house_number="7"
  "Via 25 Aprile 3" → street_name="25 Aprile", house_number="3"
  "Via XX Settembre 15" → street_name="XX Settembre", house_number="15"
- "SNC" means "senza numero civico" (no house number) — treat as house_number="SNC"
- "KM 5" at the end is a house_number (kilometer marker)
- Location prefixes come BEFORE the street: "C.C. Le Grange Via Roma 1"
  → location_info="C.C. Le Grange", street_prefix="Via", street_name="Roma", house_number="1"
- Location can also trail AFTER the street: "Via della Pace-Loc. Pascolaro"
  → street_prefix="Via", street_name="della Pace", location_info="Loc. Pascolaro"
- Loc./Località/Fraz./Frazione indicate location info, not part of the street name
- Abbreviations: "V."="Via", "P.zza"="Piazza", "C.so"="Corso", "V.le"="Viale", "L.go"="Largo"
  Expand them in street_prefix.
- Country detection: Italian ZIPs are 5 digits (00xxx-99xxx), Italian streets start with Via/Piazza/Corso etc.
  Default to "IT" if uncertain.
"""


class AddressParser:
    """Parse addresses using Claude AI with regex fallback."""

    BATCH_SIZE = 50

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.client = None
        if api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key, max_retries=3)
            except Exception as e:
                logger.warning(f"Could not init Anthropic client: {e}")
        self.metrics = ParsingMetrics(prompt_version=PROMPT_VERSION)

    def parse_all(self, addresses: list[dict]) -> list[ParsedAddress]:
        """
        Parse all addresses. Uses Claude if available, regex fallback otherwise.

        Args:
            addresses: List of {"street": str, "city": str, "zip": str}

        Returns:
            List of ParsedAddress, one per input address
        """
        if not self.client:
            logger.info("Claude not available, using regex fallback for all addresses")
            return self._parse_all_regex(addresses)

        results = [None] * len(addresses)

        # Split into batches
        batches = []
        for i in range(0, len(addresses), self.BATCH_SIZE):
            batch = addresses[i:i + self.BATCH_SIZE]
            batches.append((i, batch))

        # Process batches in parallel
        failed_batches = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for start_idx, batch in batches:
                future = executor.submit(self._parse_batch_claude, batch, start_idx)
                futures[future] = (start_idx, batch)

            for future in as_completed(futures):
                start_idx, batch = futures[future]
                try:
                    batch_results = future.result()
                    for i, parsed in enumerate(batch_results):
                        results[start_idx + i] = parsed
                except Exception as e:
                    logger.warning(f"Batch at {start_idx} failed: {e}, queuing retry")
                    failed_batches.append((start_idx, batch))

        # Retry failed batches outside the executor loop
        if failed_batches:
            time.sleep(2)
            for start_idx, batch in failed_batches:
                try:
                    batch_results = self._parse_batch_claude(batch, start_idx)
                    for i, parsed in enumerate(batch_results):
                        results[start_idx + i] = parsed
                    self.metrics.batch_retries_succeeded += 1
                except Exception as e2:
                    logger.error(f"Batch at {start_idx} retry failed: {e2}, falling back to regex")
                    self.metrics.batch_failures += 1
                    for i, addr in enumerate(batch):
                        results[start_idx + i] = self.parse_single_regex(
                            addr["street"], addr["city"], addr["zip"]
                        )
                        self.metrics.regex_fallback += 1

        # Fill any remaining None slots with regex
        for i, result in enumerate(results):
            if result is None:
                addr = addresses[i]
                results[i] = self.parse_single_regex(
                    addr["street"], addr["city"], addr["zip"]
                )
                self.metrics.regex_fallback += 1

        return results

    def _parse_batch_claude(self, batch: list[dict], start_idx: int) -> list[ParsedAddress]:
        """Parse a batch of addresses using Claude."""
        lines = []
        for i, addr in enumerate(batch):
            lines.append(
                f'{start_idx + i}: street="{addr["street"]}", '
                f'city="{addr["city"]}", zip="{addr["zip"]}"'
            )
        user_msg = "Parse these addresses:\n" + "\n".join(lines)

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[PARSE_TOOL],
            tool_choice={"type": "tool", "name": "parsed_addresses"},
            messages=[{"role": "user", "content": user_msg}]
        )

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"), None
        )
        if not tool_block:
            raise ValueError("Claude did not return tool_use response")

        parsed_data = tool_block.input.get("addresses", [])
        results = [None] * len(batch)
        parsed_by_index = {item["index"]: item for item in parsed_data}

        for i, addr in enumerate(batch):
            global_idx = start_idx + i
            item = parsed_by_index.get(global_idx)

            if item:
                parsed = ParsedAddress(
                    street_prefix=item.get("street_prefix", ""),
                    street_name=item.get("street_name", ""),
                    house_number=item.get("house_number", ""),
                    location_info=item.get("location_info", ""),
                    country_code=item.get("country_code", "IT"),
                    confidence=item.get("confidence", "medium"),
                )

                if self.verify_parsing(addr["street"], parsed):
                    parsed.parse_method = "ai"
                    results[i] = parsed
                    self.metrics.claude_parsed += 1
                else:
                    logger.warning(
                        f"Verification failed for idx {global_idx}: {addr['street']}"
                    )
                    self.metrics.claude_failed_verify += 1
                    results[i] = self.parse_single_regex(
                        addr["street"], addr["city"], addr["zip"]
                    )
                    self.metrics.regex_fallback += 1
            else:
                results[i] = self.parse_single_regex(
                    addr["street"], addr["city"], addr["zip"]
                )
                self.metrics.regex_fallback += 1

        return results

    def _parse_all_regex(self, addresses: list[dict]) -> list[ParsedAddress]:
        """Parse all addresses using regex (no Claude)."""
        results = []
        for addr in addresses:
            parsed = self.parse_single_regex(addr["street"], addr["city"], addr["zip"])
            self.metrics.regex_fallback += 1
            results.append(parsed)
        return results

    def parse_single_regex(self, street: str, city: str, zip_code: str,
                           default_country: str = "IT") -> ParsedAddress:
        """Parse a single address using regex patterns."""
        original = street.strip() if street else ""

        # Step 1: Extract location prefix (C.C., Centro Commerciale, etc.)
        location_info = ""
        clean_street = original
        street_lower = original.lower()

        for prefix in LOCATION_PREFIXES:
            if street_lower.startswith(prefix):
                for sp in STREET_PREFIXES:
                    match = re.search(rf'\b{re.escape(sp)}\.?\s+', street_lower)
                    if match:
                        location_info = original[:match.start()].strip()
                        clean_street = original[match.start():].strip()
                        break
                break

        # Step 1b: Extract trailing location suffix (e.g., "Via della Pace-Loc. Pascolaro")
        if not location_info:
            trailing_loc_match = re.search(
                r'[\s\-]+(?:loc\.?|località|localita|fraz\.?|frazione)\s+',
                clean_street, re.IGNORECASE
            )
            if trailing_loc_match:
                loc_part = clean_street[trailing_loc_match.start():].lstrip(' -').strip()
                # Don't capture trailing house number (e.g., "Loc. San Polo,1" → loc="Loc. San Polo", num goes to street)
                loc_num_match = re.search(r'[,]\s*(\d+[/\-]?\w*)\s*$', loc_part)
                if loc_num_match:
                    location_info = loc_part[:loc_num_match.start()].strip()
                    # Put house number back on clean_street for Step 3
                    clean_street = clean_street[:trailing_loc_match.start()].strip() + "," + loc_num_match.group(1)
                else:
                    location_info = loc_part
                    clean_street = clean_street[:trailing_loc_match.start()].strip()

        # Step 2: Extract street prefix (including abbreviation expansion)
        # Abbreviation map: short form → expanded form (longest first to avoid partial matches)
        ABBREVIATIONS = [
            ('p.zza', 'Piazza'), ('p.za', 'Piazza'),
            ('s.s.', 'Strada Statale'), ('s.p.', 'Strada Provinciale'),
            ('c.so', 'Corso'), ('v.le', 'Viale'), ('l.go', 'Largo'),
            ('v.', 'Via'), ('p.', 'Piazza'),
        ]

        street_prefix = ""
        street_name = clean_street
        clean_lower = clean_street.lower()

        # Try abbreviations first (more specific, already sorted longest-first)
        matched_abbrev = False
        for abbrev, expanded in ABBREVIATIONS:
            if clean_lower.startswith(abbrev):
                street_prefix = expanded
                street_name = clean_street[len(abbrev):].strip(' .')
                matched_abbrev = True
                break

        # Then try full prefixes
        if not matched_abbrev:
            for prefix in STREET_PREFIXES:
                if clean_lower.startswith(prefix + ' ') or clean_lower.startswith(prefix + '.'):
                    street_prefix = clean_street[:len(prefix)]
                    street_name = clean_street[len(prefix):].strip(' .')
                    break

        # Step 3: Extract house number from end
        house_number = ""

        # Check for SNC first
        snc_match = re.search(r'\bSNC\b', street_name, re.IGNORECASE)
        if snc_match:
            house_number = "SNC"
            street_name = street_name[:snc_match.start()].strip()
        else:
            # Check for KM markers
            km_match = re.search(r'\s+(KM\s+\d+)\s*$', street_name, re.IGNORECASE)
            if km_match:
                house_number = km_match.group(1)
                street_name = street_name[:km_match.start()].strip()
            else:
                # Match house numbers at the end: "10", "11/A", "123bis"
                # Also handles comma-separated: "Giolitti,2", "Sparano,140"
                # And compound numbers: "12/14/16", "12-12/A"
                num_match = re.search(
                    r'[,\s]+(\d+(?:[/\-]\w+)*(?:[,\s]+\d+(?:[/\-]\w+)*)*)\s*$', street_name
                )
                if num_match:
                    house_number = num_match.group(1)
                    street_name = street_name[:num_match.start()].strip()

        # Step 4: Detect country from ZIP format (fall back to caller's default)
        country_code = default_country
        zip_clean = re.sub(r'[^A-Z0-9]', '', str(zip_code).upper().strip())

        if re.match(r'^[A-Z]{1,2}[0-9][0-9A-Z]?\s*[0-9][A-Z]{2}$', zip_clean):
            country_code = "GB"
        elif re.match(r'^\d{4}[A-Z]{2}$', zip_clean):
            country_code = "NL"

        result = ParsedAddress(
            street_prefix=street_prefix,
            street_name=street_name,
            house_number=house_number,
            location_info=location_info,
            country_code=country_code,
            confidence="medium",
        )
        result.parse_method = "regex"
        return result

    def verify_parsing(self, original: str, parsed: ParsedAddress) -> bool:
        """Verify that parsed components reconstruct to the original."""
        if not original:
            return True

        reconstructed = parsed.full_street
        norm_original = self._normalize(original)
        norm_reconstructed = self._normalize(reconstructed)

        original_words = set(norm_original.split())
        reconstructed_words = set(norm_reconstructed.split())

        missing = original_words - reconstructed_words
        extra = reconstructed_words - original_words
        return len(missing) <= 1 and len(extra) <= 1

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for comparison."""
        if not text:
            return ""
        import unicodedata
        s = text.lower().strip()
        s = ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )
        s = re.sub(r'[,.\-\'\"()/]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s
