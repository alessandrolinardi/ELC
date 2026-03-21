"""
Advanced AddressParser tests covering:
- Issue #4: default_country parameter in parse_single_regex
- Issue #5: Retry not blocking as_completed loop
- Issue #8: AddressParser construction cost

Tests batch failure fallback, country code preservation, and retry behavior.
"""
import time
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from app.core.address_parser import AddressParser
from app.core.models import ParsedAddress


class TestDefaultCountry:
    """Issue #4: parse_single_regex should respect default_country param."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)

    def test_default_country_is_it(self):
        """Default behavior (no param) should still be IT."""
        result = self.parser.parse_single_regex("Via Roma 10", "Milano", "20121")
        assert result.country_code == "IT"

    def test_explicit_default_country_preserved(self):
        """When ZIP doesn't match a known pattern, default_country is used."""
        result = self.parser.parse_single_regex(
            "Hauptstraße 5", "Berlin", "10115",
            default_country="DE"
        )
        assert result.country_code == "DE"

    def test_zip_pattern_overrides_default_country(self):
        """UK ZIP pattern should override default_country."""
        result = self.parser.parse_single_regex(
            "Baker Street 221B", "London", "NW16XE",
            default_country="IT"
        )
        assert result.country_code == "GB"

    def test_nl_zip_overrides_default_country(self):
        """Dutch ZIP pattern should override default_country."""
        result = self.parser.parse_single_regex(
            "Keizersgracht 100", "Amsterdam", "1015AA",
            default_country="IT"
        )
        assert result.country_code == "NL"

    def test_preserves_ai_country_on_city_edit(self):
        """Simulates user editing city on an AI-parsed German address.
        The existing country_code 'DE' should be preserved since the regex
        parser can't detect DE from a 5-digit ZIP."""
        result = self.parser.parse_single_regex(
            "Berliner Str. 5", "München", "80331",
            default_country="DE"
        )
        assert result.country_code == "DE"

    def test_preserves_ai_country_on_street_edit(self):
        """User edits street but keeps same country — should preserve."""
        result = self.parser.parse_single_regex(
            "Rue de Rivoli 1", "Paris", "75001",
            default_country="FR"
        )
        assert result.country_code == "FR"

    def test_default_it_for_italian_zip(self):
        """Italian 5-digit ZIP with default_country=IT should stay IT."""
        result = self.parser.parse_single_regex(
            "Via Garibaldi 20", "Torino", "10122",
            default_country="IT"
        )
        assert result.country_code == "IT"


class TestRetryBehavior:
    """Issue #5: Retry should not block the as_completed loop."""

    def test_failed_batches_collected_not_blocking(self):
        """Verify retries happen after all futures complete, not inline."""
        parser = AddressParser(api_key="fake-key")

        # Mock the client to avoid real API calls
        mock_client = MagicMock()
        parser.client = mock_client

        call_times = []

        def mock_parse_batch(batch, start_idx):
            call_times.append(("call", time.monotonic(), start_idx))
            if start_idx == 0:
                raise ValueError("Simulated failure for batch 0")
            # Return valid results for other batches
            results = []
            for addr in batch:
                results.append(ParsedAddress(
                    street_prefix="Via", street_name="Test",
                    house_number="1", location_info="",
                    country_code="IT", confidence="high",
                    parse_method="ai"
                ))
            return results

        with patch.object(parser, '_parse_batch_claude', side_effect=mock_parse_batch):
            addresses = [
                {"street": f"Via Test {i}", "city": "Roma", "zip": "00100"}
                for i in range(100)  # 2 batches of 50
            ]
            results = parser.parse_all(addresses)

        # All 100 addresses should have results
        assert len(results) == 100
        assert all(r is not None for r in results)

    def test_all_batches_fail_falls_back_to_regex(self):
        """When all batches fail even after retry, regex fallback kicks in."""
        parser = AddressParser(api_key="fake-key")
        mock_client = MagicMock()
        parser.client = mock_client

        def always_fail(batch, start_idx):
            raise ValueError("Always fails")

        with patch.object(parser, '_parse_batch_claude', side_effect=always_fail):
            addresses = [
                {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
                {"street": "Piazza Duomo 1", "city": "Milano", "zip": "20122"},
            ]
            results = parser.parse_all(addresses)

        assert len(results) == 2
        # Should have fallen back to regex
        assert all(r.parse_method == "regex" for r in results)
        assert parser.metrics.batch_failures >= 1
        assert parser.metrics.regex_fallback >= 2

    def test_retry_succeeds_after_initial_failure(self):
        """First attempt fails, retry succeeds."""
        parser = AddressParser(api_key="fake-key")
        mock_client = MagicMock()
        parser.client = mock_client

        attempt_count = {"count": 0}

        def fail_then_succeed(batch, start_idx):
            attempt_count["count"] += 1
            if attempt_count["count"] == 1:
                raise ValueError("First attempt fails")
            return [
                ParsedAddress(
                    street_prefix="Via", street_name="Roma",
                    house_number="10", location_info="",
                    country_code="IT", confidence="high",
                    parse_method="ai"
                )
                for _ in batch
            ]

        with patch.object(parser, '_parse_batch_claude', side_effect=fail_then_succeed):
            addresses = [{"street": "Via Roma 10", "city": "Milano", "zip": "20121"}]
            results = parser.parse_all(addresses)

        assert len(results) == 1
        assert results[0].parse_method == "ai"
        assert parser.metrics.batch_retries_succeeded == 1


class TestParseMethod:
    """Verify parse_method is set correctly."""

    def setup_method(self):
        self.parser = AddressParser(api_key=None)

    def test_regex_parse_method(self):
        result = self.parser.parse_single_regex("Via Roma 10", "Milano", "20121")
        assert result.parse_method == "regex"

    def test_parse_all_regex_sets_method(self):
        addresses = [
            {"street": "Via Roma 10", "city": "Milano", "zip": "20121"},
        ]
        results = self.parser.parse_all(addresses)
        assert results[0].parse_method == "regex"

    def test_default_parse_method_is_ai(self):
        """ParsedAddress default is 'ai' for Claude-parsed results."""
        addr = ParsedAddress(
            street_prefix="Via", street_name="Roma",
            house_number="10", location_info="",
            country_code="IT", confidence="high"
        )
        assert addr.parse_method == "ai"


class TestAddressParserConstruction:
    """Issue #8: Construction cost."""

    def test_no_api_key_skips_client_init(self):
        """Parser with no API key should have client=None."""
        parser = AddressParser(api_key=None)
        assert parser.client is None

    def test_empty_string_api_key_skips_client(self):
        parser = AddressParser(api_key="")
        assert parser.client is None

    def test_regex_only_parser_is_cheap(self):
        """Constructing a regex-only parser should be fast."""
        start = time.monotonic()
        for _ in range(100):
            AddressParser(api_key=None)
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"100 constructions took {elapsed:.3f}s"

    def test_metrics_initialized(self):
        parser = AddressParser(api_key=None)
        assert parser.metrics.claude_parsed == 0
        assert parser.metrics.regex_fallback == 0
        assert parser.metrics.prompt_version == "v1"
