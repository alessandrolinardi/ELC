"""
Google Address Validation API client and verdict interpretation.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import requests

from .models import ParsedAddress, ValidationOutcome
from .config import get_secret
from .italian_db import get_italian_db

logger = logging.getLogger(__name__)

IGNORABLE_MISSING = {"street_number", "subpremise", "administrative_area_level_3"}


class AddressValidator:
    """Validates addresses using Google Address Validation API."""

    API_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_secret("google", "api_key")
        self.session = requests.Session()
        self._italian_db = get_italian_db()

    def validate_address(self, parsed: ParsedAddress, city: str,
                          zip_code: str, state: str = "") -> Optional[dict]:
        """Call Google Address Validation API for a single address."""
        if not self.api_key:
            return None

        payload = {
            "address": {
                "regionCode": parsed.country_code,
                "locality": city,
                "postalCode": zip_code,
                "addressLines": [parsed.street_with_number],
                "administrativeArea": state,
            }
        }

        try:
            response = self.session.post(
                self.API_URL,
                params={"key": self.api_key},
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.warning("Google API timeout")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                status = e.response.status_code
                if status == 429:
                    logger.warning("Google API rate limited (RESOURCE_EXHAUSTED)")
                else:
                    logger.warning(f"Google API HTTP error: {status}")
            return None
        except Exception as e:
            logger.error(f"Google API error: {e}")
            return None

    def interpret_verdict(self, verdict: dict, address: dict,
                           parsed: ParsedAddress, input_zip: str,
                           input_city: str) -> ValidationOutcome:
        """Interpret API verdict into ValidationOutcome."""
        action = verdict.get("possibleNextAction", "")
        granularity = verdict.get("validationGranularity", "")
        missing = address.get("missingComponentTypes", [])
        components = address.get("addressComponents", [])
        reasons = []

        # --- Step 1: Override FIX for missing house number ---
        critical_missing = [m for m in missing if m not in IGNORABLE_MISSING]

        if action == "FIX" and not critical_missing:
            has_suspicious = any(
                c.get("confirmationLevel") == "UNCONFIRMED_AND_SUSPICIOUS"
                for c in components
            )
            has_unresolved = bool(address.get("unresolvedTokens"))

            if has_suspicious or has_unresolved or granularity == "OTHER":
                action = "FIX"
            else:
                action = "CONFIRM"

        # --- Step 2: Detect silent corrections ---
        route_comp = next(
            (c for c in components if c.get("componentType") == "route"), None
        )

        silent_correction = False
        output_street = ""
        street_confirmed = False
        if route_comp:
            output_street = route_comp.get("componentName", {}).get("text", "")
            street_confirmed = route_comp.get("confirmationLevel") == "CONFIRMED"
            original_street = parsed.street_without_number
            if output_street.lower().strip() != original_street.lower().strip():
                silent_correction = True

        # --- Step 3: Detect locality mismatch ---
        api_admin3 = next(
            (c.get("componentName", {}).get("text", "") for c in components
             if c.get("componentType") == "administrative_area_level_3"), None
        )
        locality_mismatch = False
        if api_admin3 and input_city:
            if api_admin3.lower().strip() != input_city.lower().strip():
                locality_mismatch = True
                reasons.append(f"Address matched to {api_admin3}, not {input_city}")

        # --- Step 4: Detect ZIP changes ---
        output_zip = next(
            (c.get("componentName", {}).get("text", "") for c in components
             if c.get("componentType") == "postal_code"), ""
        )
        zip_confirmed = any(
            c.get("componentType") == "postal_code"
            and c.get("confirmationLevel") == "CONFIRMED"
            for c in components
        )
        zip_unconfirmed = any(
            c.get("componentType") == "postal_code"
            and c.get("confirmationLevel") == "UNCONFIRMED_BUT_PLAUSIBLE"
            for c in components
        )
        zip_changed = bool(output_zip) and output_zip != input_zip

        if zip_changed:
            reasons.append(f"ZIP changed: {input_zip} → {output_zip}")

        # --- Step 5: Determine status ---
        if action == "FIX":
            status = "review"
        elif locality_mismatch and zip_unconfirmed:
            status = "review"
        elif action == "CONFIRM" or silent_correction or zip_changed:
            if (verdict.get("hasReplacedComponents")
                or verdict.get("hasSpellCorrectedComponents")
                or silent_correction
                or zip_changed):
                status = "corrected"
                if silent_correction:
                    reasons.append(f"Street corrected: {parsed.street_without_number} → {output_street}")
                if verdict.get("hasSpellCorrectedComponents"):
                    reasons.append("Spelling corrected")
                if verdict.get("hasReplacedComponents"):
                    reasons.append("Components replaced")
            elif verdict.get("hasInferredComponents"):
                status = "corrected"
                reasons.append("Missing components inferred")
            else:
                status = "valid"
        else:  # ACCEPT
            if silent_correction or zip_changed:
                status = "corrected"
                if silent_correction:
                    reasons.append(f"Street corrected: {parsed.street_without_number} → {output_street}")
            elif verdict.get("hasSpellCorrectedComponents"):
                status = "corrected"
                reasons.append("Spelling corrected")
            elif locality_mismatch:
                status = "valid"
            else:
                status = "valid"

        # Extract location info from API (point_of_interest)
        api_location = next(
            (c.get("componentName", {}).get("text", "") for c in components
             if c.get("componentType") == "point_of_interest"), ""
        )
        location_info = api_location or parsed.location_info

        return ValidationOutcome(
            status=status,
            action=action,
            input_zip=input_zip,
            output_zip=output_zip,
            zip_confirmed=zip_confirmed,
            zip_corrected=zip_changed,
            input_street=parsed.street_with_number,
            output_street=output_street,
            street_confirmed=street_confirmed,
            street_corrected=silent_correction or any(
                c.get("spellCorrected") or c.get("replaced")
                for c in components if c.get("componentType") == "route"
            ),
            silent_correction=silent_correction,
            house_number=parsed.house_number,
            granularity=granularity,
            address_complete=verdict.get("addressComplete", False),
            reasons=reasons,
            formatted_address=address.get("formattedAddress", ""),
            location_info=location_info,
        )

    def validate_zip_province(self, zip_code: str, province: str) -> tuple[bool, str]:
        """Validate if ZIP code belongs to the Italian province using comuni database."""
        return self._italian_db.validate_cap_for_provincia(zip_code, province)

    def validate_zip_comune(self, zip_code: str, comune: str,
                             province: str = "") -> tuple[bool, str]:
        """Validate if ZIP code is correct for a specific comune."""
        return self._italian_db.validate_cap_for_comune(zip_code, comune, province)

    def is_valid_italian_cap(self, zip_code: str) -> bool:
        """Check if a CAP exists in Italy."""
        return self._italian_db.is_valid_cap(zip_code)
