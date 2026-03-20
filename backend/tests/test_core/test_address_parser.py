import pytest
from app.core.address_parser import AddressParser
from app.core.models import ParsedAddress


class TestRegexFallback:
    """Test regex-based address parsing (Tier 2/3 fallback)."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)  # No Claude, regex only

    def test_simple_address(self):
        result = self.parser.parse_single_regex("Via Roma 10", "Milano", "20121")
        assert result.street_prefix == "Via"
        assert result.street_name == "Roma"
        assert result.house_number == "10"
        assert result.country_code == "IT"

    def test_fractional_house_number(self):
        result = self.parser.parse_single_regex("Via Roma 11/A", "Milano", "20121")
        assert result.house_number == "11/A"

    def test_no_house_number(self):
        result = self.parser.parse_single_regex("Via Roma", "Milano", "20121")
        assert result.house_number == ""
        assert result.street_name == "Roma"

    def test_snc(self):
        result = self.parser.parse_single_regex("Via Roma SNC", "Roma", "00187")
        assert result.house_number == "SNC"

    def test_location_prefix(self):
        result = self.parser.parse_single_regex(
            "C.C. Le Grange Via Roma 1", "Torino", "10100"
        )
        assert result.location_info == "C.C. Le Grange"
        assert result.street_prefix == "Via"
        assert result.street_name == "Roma"
        assert result.house_number == "1"

    def test_country_detection_italian(self):
        result = self.parser.parse_single_regex("Via Roma 10", "Milano", "20121")
        assert result.country_code == "IT"

    def test_country_detection_uk(self):
        result = self.parser.parse_single_regex("Baker Street 221B", "London", "NW16XE")
        assert result.country_code == "GB"

    def test_piazza_prefix(self):
        result = self.parser.parse_single_regex("Piazza Duomo 1", "Milano", "20122")
        assert result.street_prefix == "Piazza"
        assert result.street_name == "Duomo"
        assert result.house_number == "1"

    def test_corso_prefix(self):
        result = self.parser.parse_single_regex("Corso Vittorio Emanuele II 120", "Torino", "10121")
        assert result.street_prefix == "Corso"
        assert result.house_number == "120"

    def test_km_house_number(self):
        result = self.parser.parse_single_regex("Strada Statale 16 KM 5", "Bari", "70100")
        assert result.house_number == "KM 5"

    def test_centro_commerciale_full(self):
        result = self.parser.parse_single_regex(
            "Centro Commerciale Il Miglio Via Casilina 1", "Roma", "00100"
        )
        assert result.location_info == "Centro Commerciale Il Miglio"
        assert result.street_prefix == "Via"

    def test_via_del_corso(self):
        result = self.parser.parse_single_regex("Via del Corso 10", "Roma", "00187")
        assert result.street_prefix == "Via"
        assert result.street_name == "del Corso"
        assert result.house_number == "10"


class TestVerification:
    """Test that parsed addresses reconstruct to original."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)

    def test_verification_passes_for_simple(self):
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        assert self.parser.verify_parsing("Via Roma 10", parsed) is True

    def test_verification_fails_for_wrong_parse(self):
        parsed = ParsedAddress("Via", "Totally Wrong", "10", "", "IT", "high")
        assert self.parser.verify_parsing("Via Roma 10", parsed) is False

    def test_verification_allows_abbreviation_difference(self):
        parsed = ParsedAddress("Via", "Roma", "10", "", "IT", "high")
        assert self.parser.verify_parsing("V. Roma 10", parsed) is True

    def test_verification_with_location_info(self):
        parsed = ParsedAddress("Via", "Roma", "1", "C.C. Le Grange", "IT", "high")
        assert self.parser.verify_parsing("C.C. Le Grange Via Roma 1", parsed) is True


class TestParseAll:
    """Test batch parsing with regex fallback."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)  # Regex only

    def test_parse_all_regex_fallback(self):
        addresses = [
            {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
            {"street": "Piazza Duomo 1", "city": "Milano", "zip": "20122"},
        ]
        results = self.parser.parse_all(addresses)
        assert len(results) == 2
        assert results[0].street_prefix == "Via"
        assert results[1].street_prefix == "Piazza"
        assert self.parser.metrics.regex_fallback == 2
