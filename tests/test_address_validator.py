import pytest
from src.address_validator import AddressValidator
from src.models import ParsedAddress, ValidationOutcome

# Fixtures based on real API test results

VERDICT_ACCEPT_CLEAN = {
    "possibleNextAction": "ACCEPT",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
}

ADDRESS_ACCEPT_CLEAN = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Via Roma"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "street_number", "componentName": {"text": "10"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20121"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "formattedAddress": "Via Roma, 10, 20121 Milano MI, Italia",
}

# Test 6: Silent correction Via → Piazza
VERDICT_SILENT_CORRECTION = {
    "possibleNextAction": "ACCEPT",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
    "hasInferredComponents": True,
}

ADDRESS_SILENT_CORRECTION = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Piazza Ventiquattro Maggio"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "street_number", "componentName": {"text": "5"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20123"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "administrative_area_level_3", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED", "inferred": True},
    ],
    "formattedAddress": "Piazza Ventiquattro Maggio, 5, 20123 Milano MI, Italia",
}

# Test 7: Fake street → FIX
VERDICT_FAKE_STREET = {
    "possibleNextAction": "FIX",
    "validationGranularity": "OTHER",
    "addressComplete": True,
    "hasUnconfirmedComponents": True,
    "hasInferredComponents": True,
}

ADDRESS_FAKE_STREET = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "via inventata"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
        {"componentType": "street_number", "componentName": {"text": "99"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
        {"componentType": "postal_code", "componentName": {"text": "20121"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "formattedAddress": "via inventata, 99, 20121 Milano MI, Italia",
}

# Missing street_number only → should downgrade FIX
VERDICT_MISSING_HOUSE_NUM = {
    "possibleNextAction": "FIX",
    "validationGranularity": "ROUTE",
    "hasInferredComponents": True,
}

ADDRESS_MISSING_HOUSE_NUM = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Piazza 24 Maggio"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20123"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "missingComponentTypes": ["street_number"],
    "formattedAddress": "Piazza 24 Maggio, 20123 Milano MI, Italia",
}

# Spell correction (test 3: "roam" → "Roma")
VERDICT_SPELL_CORRECTED = {
    "possibleNextAction": "ACCEPT",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
    "hasSpellCorrectedComponents": True,
    "hasInferredComponents": True,
}

ADDRESS_SPELL_CORRECTED = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Via Roma"}, "confirmationLevel": "CONFIRMED", "spellCorrected": True},
        {"componentType": "street_number", "componentName": {"text": "10"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20121"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
    ],
    "formattedAddress": "Via Roma, 10, 20121 Milano MI, Italia",
}

# Locality mismatch (test 1: matched to Assago instead of Milano)
VERDICT_LOCALITY_MISMATCH = {
    "possibleNextAction": "ACCEPT",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
    "hasUnconfirmedComponents": True,
    "hasInferredComponents": True,
}

ADDRESS_LOCALITY_MISMATCH = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Via Roma"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "street_number", "componentName": {"text": "10"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "20121"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
        {"componentType": "locality", "componentName": {"text": "Milano"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "administrative_area_level_3", "componentName": {"text": "Assago"}, "confirmationLevel": "CONFIRMED", "inferred": True},
    ],
    "unconfirmedComponentTypes": ["postal_code"],
    "formattedAddress": "Via Roma, 10, 20121 Milano MI, Italia",
}

# ZIP replaced (test 5: 10100 → 10123)
VERDICT_ZIP_REPLACED = {
    "possibleNextAction": "CONFIRM",
    "validationGranularity": "PREMISE",
    "addressComplete": True,
    "hasReplacedComponents": True,
    "hasInferredComponents": True,
}

ADDRESS_ZIP_REPLACED = {
    "addressComponents": [
        {"componentType": "route", "componentName": {"text": "Via Roma"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "street_number", "componentName": {"text": "1"}, "confirmationLevel": "CONFIRMED"},
        {"componentType": "postal_code", "componentName": {"text": "10123"}, "confirmationLevel": "CONFIRMED", "replaced": True},
        {"componentType": "locality", "componentName": {"text": "Torino"}, "confirmationLevel": "CONFIRMED"},
    ],
    "formattedAddress": "Via Roma, 1, 10123 Torino TO, Italia",
}


class TestVerdictInterpretation:

    def setup_method(self):
        self.validator = AddressValidator(api_key="fake")

    def test_accept_clean_is_valid(self):
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_ACCEPT_CLEAN, ADDRESS_ACCEPT_CLEAN, parsed, "20121", "Milano"
        )
        assert outcome.status == "valid"

    def test_silent_correction_detected(self):
        parsed = ParsedAddress("Via", "24 Maggio", "5", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_SILENT_CORRECTION, ADDRESS_SILENT_CORRECTION, parsed, "20123", "Milano"
        )
        assert outcome.status == "corrected"
        assert outcome.silent_correction is True

    def test_fake_street_is_review(self):
        parsed = ParsedAddress("Via", "inventata", "99", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_FAKE_STREET, ADDRESS_FAKE_STREET, parsed, "20121", "Milano"
        )
        assert outcome.status == "review"

    def test_missing_house_number_downgrades_fix(self):
        """FIX triggered only by missing street_number should not be review."""
        parsed = ParsedAddress("Via", "24 Maggio", "", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_MISSING_HOUSE_NUM, ADDRESS_MISSING_HOUSE_NUM, parsed, "20123", "Milano"
        )
        assert outcome.status != "review"

    def test_spell_correction_is_corrected(self):
        """ACCEPT with spellCorrected should be corrected, not valid."""
        parsed = ParsedAddress("Via", "roam", "10", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_SPELL_CORRECTED, ADDRESS_SPELL_CORRECTED, parsed, "20121", "Milano"
        )
        assert outcome.status == "corrected"

    def test_zip_change_detected(self):
        parsed = ParsedAddress("Via", "Roma", "1", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_ZIP_REPLACED, ADDRESS_ZIP_REPLACED, parsed, "10100", "Torino"
        )
        assert outcome.zip_corrected is True
        assert outcome.output_zip == "10123"
        assert outcome.status == "corrected"

    def test_locality_mismatch_with_unconfirmed_zip_is_review(self):
        """Wrong municipality + unconfirmed ZIP = review."""
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_LOCALITY_MISMATCH, ADDRESS_LOCALITY_MISMATCH, parsed, "20121", "Milano"
        )
        assert outcome.status == "review"
        assert any("Assago" in r for r in outcome.reasons)

    def test_house_number_preserved_in_outcome(self):
        parsed = ParsedAddress("Via", "Roma", "11/A", "", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_ACCEPT_CLEAN, ADDRESS_ACCEPT_CLEAN, parsed, "20121", "Milano"
        )
        assert outcome.house_number == "11/A"

    def test_location_info_from_api(self):
        """point_of_interest component should be captured as location_info."""
        address = {
            **ADDRESS_ACCEPT_CLEAN,
            "addressComponents": [
                *ADDRESS_ACCEPT_CLEAN["addressComponents"],
                {"componentType": "point_of_interest", "componentName": {"text": "C.C. Le Grange"}, "confirmationLevel": "UNCONFIRMED_BUT_PLAUSIBLE"},
            ],
        }
        parsed = ParsedAddress("Via", "Roma", "1", "C.C. Le Grange", "IT", "high")
        outcome = self.validator.interpret_verdict(
            VERDICT_ACCEPT_CLEAN, address, parsed, "20121", "Milano"
        )
        assert outcome.location_info == "C.C. Le Grange"


class TestZipProvinceCheck:

    def setup_method(self):
        self.validator = AddressValidator(api_key="fake")

    def test_valid_zip_for_province(self):
        valid, msg = self.validator.validate_zip_province("20121", "MI")
        assert valid is True

    def test_invalid_zip_for_province(self):
        valid, msg = self.validator.validate_zip_province("10121", "MI")
        assert valid is False

    def test_unknown_province_fails(self):
        """Unknown province XX — CAP 20121 belongs to MI, not XX."""
        valid, msg = self.validator.validate_zip_province("20121", "XX")
        assert valid is False

    def test_empty_province_passes(self):
        valid, msg = self.validator.validate_zip_province("20121", "")
        assert valid is True

    def test_rome_zip(self):
        valid, msg = self.validator.validate_zip_province("00187", "RM")
        assert valid is True

    def test_invalid_zip_99999(self):
        """99999 doesn't exist in Italy."""
        valid, msg = self.validator.validate_zip_province("99999", "MI")
        assert valid is False

    def test_is_valid_italian_cap(self):
        assert self.validator.is_valid_italian_cap("20121") is True
        assert self.validator.is_valid_italian_cap("99999") is False

    def test_validate_zip_comune_correct(self):
        valid, msg = self.validator.validate_zip_comune("20121", "Milano", "MI")
        assert valid is True

    def test_validate_zip_comune_wrong(self):
        """20057 is Assago, not Milano."""
        valid, msg = self.validator.validate_zip_comune("20057", "Milano", "MI")
        assert valid is False
