"""
Zip Code Validator Module
Validates and corrects zip codes using OpenStreetMap Nominatim API.
"""

import time
import requests
from dataclasses import dataclass
from typing import Optional, Callable
from io import BytesIO
import re

import pandas as pd


@dataclass
class ValidationResult:
    """Result of a single zip code validation."""
    row_index: int
    name: str
    city: str
    street: str
    original_zip: str
    suggested_zip: Optional[str]
    confidence: int  # 0-100
    reason: str
    is_valid: bool
    auto_corrected: bool = False


@dataclass
class ValidationReport:
    """Complete validation report."""
    total_rows: int
    valid_count: int
    corrected_count: int
    review_count: int
    skipped_count: int
    results: list[ValidationResult]


class ZipValidator:
    """
    Validates zip codes using OpenStreetMap Nominatim API.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "ELC-ZipValidator/1.0 (shipping label tool)"
    REQUEST_DELAY = 1.1  # seconds between requests (Nominatim limit)

    # Italian CAP ranges for major cities (for additional validation)
    ITALIAN_CAP_RANGES = {
        'roma': ('00100', '00199'),
        'milano': ('20100', '20199'),
        'napoli': ('80100', '80147'),
        'torino': ('10100', '10156'),
        'firenze': ('50100', '50145'),
        'florence': ('50100', '50145'),
        'bologna': ('40100', '40141'),
        'venezia': ('30100', '30176'),
        'venice': ('30100', '30176'),
    }

    def __init__(self, confidence_threshold: int = 90):
        """
        Initialize validator.

        Args:
            confidence_threshold: Minimum confidence for auto-correction (default 90%)
        """
        self.confidence_threshold = confidence_threshold
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.USER_AGENT})

    def _clean_zip_code(self, zip_code: str) -> tuple[str, bool]:
        """
        Clean zip code by replacing common typos (letters for numbers).

        Args:
            zip_code: Original zip code

        Returns:
            Tuple of (cleaned_zip, was_cleaned)
        """
        original = str(zip_code).strip()

        # Common letter-to-number replacements
        replacements = {
            'o': '0', 'O': '0',  # o/O → 0
            'l': '1', 'I': '1', 'i': '1',  # l/I/i → 1
            'z': '2', 'Z': '2',  # z/Z → 2
            's': '5', 'S': '5',  # s/S → 5
            'b': '8', 'B': '8',  # b/B → 8
            'g': '9', 'G': '9',  # g/G → 9
        }

        cleaned = original
        for char, replacement in replacements.items():
            cleaned = cleaned.replace(char, replacement)

        # Remove any remaining non-digit characters
        cleaned = re.sub(r'[^\d]', '', cleaned)

        was_cleaned = cleaned != original.replace(' ', '')
        return cleaned, was_cleaned

    def _count_different_digits(self, zip1: str, zip2: str) -> int:
        """
        Count how many digits are different between two zip codes.

        Args:
            zip1: First zip code
            zip2: Second zip code

        Returns:
            Number of different digits (0-5 for Italian CAP)
        """
        if len(zip1) != len(zip2):
            return max(len(zip1), len(zip2))

        return sum(1 for a, b in zip(zip1, zip2) if a != b)

    def _is_transposition(self, zip1: str, zip2: str) -> bool:
        """
        Check if two zip codes are transpositions (same digits, different order).

        Examples:
            01870 vs 00187 -> True (same digits rearranged)
            50124 vs 50122 -> False (different digits)

        Args:
            zip1: First zip code
            zip2: Second zip code

        Returns:
            True if same digits in different order
        """
        if len(zip1) != len(zip2):
            return False

        # Check if both have the same digits (sorted)
        return sorted(zip1) == sorted(zip2)

    def _is_adjacent_swap(self, zip1: str, zip2: str) -> bool:
        """
        Check if two zip codes differ by a single adjacent digit swap.

        Examples:
            50214 vs 50124 -> True (2 and 1 swapped)
            50122 vs 50212 -> True (1 and 2 swapped)

        Args:
            zip1: First zip code
            zip2: Second zip code

        Returns:
            True if single adjacent swap
        """
        if len(zip1) != len(zip2):
            return False

        diff_positions = [i for i in range(len(zip1)) if zip1[i] != zip2[i]]

        # Must have exactly 2 different positions that are adjacent
        if len(diff_positions) != 2:
            return False

        i, j = diff_positions
        if j - i != 1:  # Must be adjacent
            return False

        # Check if swapping fixes it
        return zip1[i] == zip2[j] and zip1[j] == zip2[i]

    def _is_valid_italian_zip_format(self, zip_code: str) -> bool:
        """Check if zip code has valid Italian CAP format (5 digits)."""
        return bool(re.match(r'^\d{5}$', str(zip_code).strip()))

    def _query_nominatim(self, street: str, city: str, country: str = "Italy") -> Optional[dict]:
        """
        Query Nominatim API for address.

        Args:
            street: Street address
            city: City name
            country: Country name

        Returns:
            First result from API or None
        """
        try:
            # First try with full address
            params = {
                'street': street,
                'city': city,
                'country': country,
                'format': 'json',
                'addressdetails': 1,
                'limit': 1
            }

            response = self.session.get(self.NOMINATIM_URL, params=params, timeout=10)
            response.raise_for_status()
            results = response.json()

            if results:
                return results[0]

            # Fallback: city-only search
            time.sleep(self.REQUEST_DELAY)
            params = {
                'city': city,
                'country': country,
                'format': 'json',
                'addressdetails': 1,
                'limit': 1
            }

            response = self.session.get(self.NOMINATIM_URL, params=params, timeout=10)
            response.raise_for_status()
            results = response.json()

            if results:
                result = results[0]
                result['_city_only'] = True  # Mark as city-only match
                return result

            return None

        except Exception as e:
            return None

    def validate_zip(
        self,
        street: str,
        city: str,
        original_zip: str,
        country: str = "IT"
    ) -> tuple[bool, Optional[str], int, str]:
        """
        Validate a single zip code.

        Args:
            street: Street address
            city: City name
            original_zip: Original zip code to validate
            country: Country code

        Returns:
            Tuple of (is_valid, suggested_zip, confidence, reason)
        """
        original_zip_raw = str(original_zip).strip()

        # Only validate Italian addresses for now
        if country.upper() not in ('IT', 'ITALY'):
            return True, original_zip_raw, 100, "Non-IT country - skipped"

        # Try to clean up the zip code (handle typos like 'o' instead of '0')
        cleaned_zip, was_cleaned = self._clean_zip_code(original_zip_raw)

        # Format check on cleaned version
        if not self._is_valid_italian_zip_format(cleaned_zip):
            # If even cleaned version is invalid, try to get suggestion anyway
            result = self._query_nominatim(street or "", city, "Italy")
            if result:
                suggested = result.get('address', {}).get('postcode')
                if suggested:
                    if ';' in suggested:
                        suggested = suggested.split(';')[0]
                    return False, suggested, 75, f"Invalid format '{original_zip_raw}' - suggested from address"
            return False, None, 0, f"Invalid format '{original_zip_raw}' (must be 5 digits)"

        # Use cleaned zip for comparison
        working_zip = cleaned_zip

        # Query Nominatim
        result = self._query_nominatim(street or "", city, "Italy")

        if not result:
            return False, None, 0, "Address not found in API"

        suggested_zip = result.get('address', {}).get('postcode')

        if not suggested_zip:
            # Try to get zip from city name lookup
            city_lower = city.lower().strip()
            if city_lower in self.ITALIAN_CAP_RANGES:
                cap_start, cap_end = self.ITALIAN_CAP_RANGES[city_lower]
                if cap_start <= working_zip <= cap_end:
                    return True, working_zip, 75, "Within city CAP range"
            return False, None, 50, "No postal code in API response"

        # Handle multiple postcodes (e.g., "50121;50122")
        if ';' in suggested_zip:
            suggested_zips = suggested_zip.split(';')
            if working_zip in suggested_zips:
                return True, working_zip, 100, "Exact match (one of multiple)"
            # Check if any of the suggested matches closely
            for sz in suggested_zips:
                if self._count_different_digits(working_zip, sz) == 1:
                    suggested_zip = sz
                    break
            else:
                suggested_zip = suggested_zips[0]

        # Exact match
        if working_zip == suggested_zip:
            if was_cleaned:
                return False, suggested_zip, 95, f"Typo fixed: '{original_zip_raw}' → '{suggested_zip}'"
            return True, working_zip, 100, "Exact match"

        # Calculate confidence based on type of error
        diff_count = self._count_different_digits(working_zip, suggested_zip)
        is_city_only = result.get('_city_only', False)
        is_transposition = self._is_transposition(working_zip, suggested_zip)
        is_adjacent_swap = self._is_adjacent_swap(working_zip, suggested_zip)

        # Confidence logic - prioritize by error type
        if is_city_only:
            confidence = 70
            reason = "City-level match only (street not found)"
        elif is_adjacent_swap:
            # Adjacent digit swap = very likely typo = highest confidence
            confidence = 96
            reason = f"Adjacent digits swapped ({working_zip} → {suggested_zip})"
        elif is_transposition:
            # Same digits, different order = likely mistyped = high confidence
            confidence = 95
            reason = f"Digits transposed ({working_zip} → {suggested_zip})"
        elif diff_count == 1:
            # Only 1 digit different = likely typo = high confidence
            confidence = 95
            reason = f"Typo: 1 digit different ({working_zip} → {suggested_zip})"
        elif diff_count == 2:
            # 2 digits different = still likely correction needed
            confidence = 92
            reason = f"2 digits different ({working_zip} → {suggested_zip})"
        elif diff_count >= 3 and not is_city_only:
            # 3+ digits different BUT full address match (city confirmed)
            # Higher confidence because API found the exact street+city
            confidence = 91
            reason = f"{diff_count} digits different, city confirmed ({working_zip} → {suggested_zip})"
        else:
            # 3+ digits different with city-only match = less certain
            confidence = 85
            reason = f"{diff_count} digits different - verify manually"

        # Add note if original was cleaned
        if was_cleaned:
            reason = f"Cleaned '{original_zip_raw}' → '{working_zip}'. " + reason

        return False, suggested_zip, confidence, reason

    def process_dataframe(
        self,
        df: pd.DataFrame,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> ValidationReport:
        """
        Process entire DataFrame and validate all zip codes.

        Args:
            df: DataFrame with address data
            progress_callback: Optional callback(current, total, message)

        Returns:
            ValidationReport with all results
        """
        results = []
        valid_count = 0
        corrected_count = 0
        review_count = 0
        skipped_count = 0

        # Find relevant columns (case-insensitive)
        col_map = self._map_columns(df)

        if not all(col_map.get(k) for k in ['city', 'zip', 'country']):
            raise ValueError(
                f"Missing required columns. Found: {list(df.columns)}\n"
                f"Need: City, Zip, Country"
            )

        total = len(df)

        for idx, row in df.iterrows():
            if progress_callback:
                progress_callback(idx + 1, total, f"Validating row {idx + 1}...")

            # Extract values
            name = str(row.get(col_map.get('name', ''), ''))
            street = str(row.get(col_map.get('street', ''), ''))
            city = str(row.get(col_map['city'], ''))
            original_zip = str(row.get(col_map['zip'], ''))
            country = str(row.get(col_map['country'], 'IT'))

            # Skip non-IT countries
            if country.upper() not in ('IT', 'ITALY'):
                results.append(ValidationResult(
                    row_index=idx,
                    name=name,
                    city=city,
                    street=street,
                    original_zip=original_zip,
                    suggested_zip=original_zip,
                    confidence=100,
                    reason="Non-IT country - skipped",
                    is_valid=True
                ))
                skipped_count += 1
                continue

            # Validate
            is_valid, suggested_zip, confidence, reason = self.validate_zip(
                street, city, original_zip, country
            )

            # Determine action
            auto_correct = not is_valid and confidence >= self.confidence_threshold and suggested_zip

            result = ValidationResult(
                row_index=idx,
                name=name,
                city=city,
                street=street,
                original_zip=original_zip,
                suggested_zip=suggested_zip,
                confidence=confidence,
                reason=reason,
                is_valid=is_valid,
                auto_corrected=auto_correct
            )
            results.append(result)

            if is_valid:
                valid_count += 1
            elif auto_correct:
                corrected_count += 1
            else:
                review_count += 1

            # Rate limiting
            time.sleep(self.REQUEST_DELAY)

        return ValidationReport(
            total_rows=total,
            valid_count=valid_count,
            corrected_count=corrected_count,
            review_count=review_count,
            skipped_count=skipped_count,
            results=results
        )

    def _map_columns(self, df: pd.DataFrame) -> dict:
        """Map DataFrame columns to expected fields."""
        col_map = {}
        columns_lower = {c.lower().strip(): c for c in df.columns}

        mappings = {
            'name': ['name', 'nome', 'customer name'],
            'street': ['street 1', 'street', 'address', 'indirizzo', 'via'],
            'city': ['city', 'città', 'citta'],
            'zip': ['zip', 'cap', 'postal code', 'postcode', 'zip code'],
            'country': ['country', 'paese', 'nazione'],
        }

        for field, possible_names in mappings.items():
            for name in possible_names:
                if name in columns_lower:
                    col_map[field] = columns_lower[name]
                    break

        return col_map

    def generate_corrected_excel(
        self,
        original_df: pd.DataFrame,
        report: ValidationReport
    ) -> bytes:
        """
        Generate corrected Excel with auto-corrections applied.

        Args:
            original_df: Original DataFrame
            report: Validation report

        Returns:
            Excel file as bytes
        """
        df = original_df.copy()
        col_map = self._map_columns(df)
        zip_col = col_map.get('zip')

        if zip_col:
            for result in report.results:
                if result.auto_corrected and result.suggested_zip:
                    df.at[result.row_index, zip_col] = result.suggested_zip

        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        return output.getvalue()

    def generate_review_report(self, report: ValidationReport) -> bytes:
        """
        Generate Excel report for items needing manual review.

        Args:
            report: Validation report

        Returns:
            Excel file as bytes
        """
        review_items = [
            {
                'Row': r.row_index + 2,  # Excel row (1-indexed + header)
                'Name': r.name,
                'City': r.city,
                'Street': r.street,
                'Original ZIP': r.original_zip,
                'Suggested ZIP': r.suggested_zip or '-',
                'Confidence': f"{r.confidence}%",
                'Reason': r.reason,
                'Action': 'Auto-corrected' if r.auto_corrected else 'Manual review needed'
            }
            for r in report.results
            if not r.is_valid
        ]

        df = pd.DataFrame(review_items)
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        return output.getvalue()
