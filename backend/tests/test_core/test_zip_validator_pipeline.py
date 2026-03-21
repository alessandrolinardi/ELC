"""
ZipValidator pipeline tests covering:
- Issue #6: Progress callback scaling
- Issue #9: _validate_addresses length guard

Tests the validation pipeline with mocked Google API, progress tracking,
column mapping, and edge cases.
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from app.core.zip_validator import ZipValidator, ValidationReport
from app.core.models import ParsedAddress


def _make_validator(**kwargs):
    """Create a ZipValidator with mocked external dependencies."""
    with patch('app.core.zip_validator.get_supabase_client', return_value=None):
        return ZipValidator(
            google_api_key="fake-key",
            anthropic_api_key=None,
            **kwargs
        )


def _make_parsed(prefix="Via", name="Roma", number="10",
                 country="IT", method="ai"):
    addr = ParsedAddress(
        street_prefix=prefix,
        street_name=name,
        house_number=number,
        location_info="",
        country_code=country,
        confidence="high",
    )
    addr.parse_method = method
    return addr


class TestLengthGuard:
    """Issue #9: _validate_addresses must check len(parsed_addresses) == len(df)."""

    def test_length_mismatch_raises(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10", "Via Milano 5"],
            "City": ["Roma", "Milano"],
            "Zip": ["00100", "20121"],
        })
        parsed = [_make_parsed()]  # Only 1, but df has 2 rows

        with pytest.raises(ValueError, match="parsed_addresses length"):
            validator._validate_addresses(df, parsed)

    def test_length_match_passes(self):
        """Equal lengths should not raise."""
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Roma"],
            "Zip": ["00100"],
        })
        parsed = [_make_parsed()]

        # Mock the API to avoid real calls
        with patch.object(validator.address_validator, 'validate_address', return_value=None):
            report, _ = validator._validate_addresses(df, parsed)
            assert report.total_rows == 1

    def test_empty_df_with_empty_parsed(self):
        """Empty dataframe with empty parsed list should work."""
        validator = _make_validator()
        df = pd.DataFrame({"City": [], "Zip": []})
        parsed = []

        report, _ = validator._validate_addresses(df, parsed)
        assert report.total_rows == 0


class TestColumnGuard:
    """_validate_addresses column validation."""

    def test_missing_city_column_raises(self):
        validator = _make_validator()
        df = pd.DataFrame({"Street": ["Via Roma 10"], "Zip": ["00100"]})
        parsed = [_make_parsed()]

        with pytest.raises(ValueError, match="Missing required columns"):
            validator._validate_addresses(df, parsed)

    def test_missing_zip_column_raises(self):
        validator = _make_validator()
        df = pd.DataFrame({"Street": ["Via Roma 10"], "City": ["Roma"]})
        parsed = [_make_parsed()]

        with pytest.raises(ValueError, match="Missing required columns"):
            validator._validate_addresses(df, parsed)

    def test_optional_street_column_ok(self):
        """Street column is optional — should not raise if missing."""
        validator = _make_validator()
        df = pd.DataFrame({"City": ["Roma"], "Zip": ["00100"]})
        parsed = [_make_parsed()]

        with patch.object(validator.address_validator, 'validate_address', return_value=None):
            report, _ = validator._validate_addresses(df, parsed)
            assert report.total_rows == 1


class TestProgressCallback:
    """Issue #6: Progress scaling correctness."""

    def test_progress_reports_0_to_100(self):
        """_validate_addresses should report progress from 0% to 100%."""
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10", "Piazza Duomo 1", "Corso Italia 5"],
            "City": ["Roma", "Milano", "Torino"],
            "Zip": ["00100", "20122", "10121"],
        })
        parsed = [_make_parsed() for _ in range(3)]
        progress_calls = []

        def track_progress(current, total, message):
            progress_calls.append((current, total, message))

        with patch.object(validator.address_validator, 'validate_address', return_value=None):
            validator._validate_addresses(df, parsed, track_progress)

        assert len(progress_calls) == 3
        # Each call should have total=100
        assert all(t == 100 for _, t, _ in progress_calls)
        # Progress should increase
        percents = [c for c, _, _ in progress_calls]
        assert percents == sorted(percents)
        # Last call should be 100%
        assert percents[-1] == 100

    def test_process_dataframe_scales_20_to_100(self):
        """process_dataframe should scale validation progress from 20-100%."""
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Roma"],
            "Zip": ["00100"],
        })
        progress_calls = []

        def track_progress(current, total, message):
            progress_calls.append((current, total, message))

        with patch.object(validator.address_parser, 'parse_all',
                          return_value=[_make_parsed()]):
            with patch.object(validator.address_validator, 'validate_address',
                              return_value=None):
                validator.process_dataframe(df, track_progress)

        # Should have parsing progress (0/100) and then scaled validation
        # The first call is parsing start, then parsing complete (20/100),
        # then validation scaled from 20-100%
        validation_calls = [c for c in progress_calls if "Validating" in c[2]]
        for current, total, _ in validation_calls:
            assert current >= 20, f"Validation progress {current} should be >= 20"
            assert total == 100


class TestNonITCountrySkip:
    """Non-Italian addresses should be skipped."""

    def test_non_it_country_skipped(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Hauptstraße 5"],
            "City": ["Berlin"],
            "Zip": ["10115"],
        })
        parsed = [_make_parsed(prefix="", name="Hauptstraße", number="5", country="DE")]

        report, _ = validator._validate_addresses(df, parsed)
        assert report.skipped_count == 1
        assert report.total_rows == 1
        assert report.results[0].country_code == "DE"

    def test_it_country_not_skipped(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Milano"],
            "Zip": ["20121"],
        })
        parsed = [_make_parsed()]

        with patch.object(validator.address_validator, 'validate_address', return_value=None):
            report, _ = validator._validate_addresses(df, parsed)
            assert report.skipped_count == 0


class TestGoogleAPIUnavailable:
    """Graceful handling when Google API returns None."""

    def test_api_unavailable_marks_review(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Roma"],
            "Zip": ["00100"],
        })
        parsed = [_make_parsed()]

        with patch.object(validator.address_validator, 'validate_address', return_value=None):
            report, _ = validator._validate_addresses(df, parsed)

        assert report.review_count == 1
        assert report.results[0].reason == "Google API unavailable"

    def test_api_returns_no_result_key(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Roma"],
            "Zip": ["00100"],
        })
        parsed = [_make_parsed()]

        with patch.object(validator.address_validator, 'validate_address',
                          return_value={"error": "something"}):
            report, _ = validator._validate_addresses(df, parsed)

        assert report.review_count == 1


class TestZipPadding:
    """Italian ZIP codes should be padded to 5 digits."""

    def test_short_zip_padded(self):
        """ZIP '187' should become '00187'."""
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Roma"],
            "Zip": [187],  # numeric, short
        })
        parsed = [_make_parsed()]

        api_calls = []

        def capture_call(parsed_addr, city, zip_code, state="", street2=""):
            api_calls.append(zip_code)
            return None

        with patch.object(validator.address_validator, 'validate_address',
                          side_effect=capture_call):
            validator._validate_addresses(df, parsed)

        assert api_calls[0] == "00187"

    def test_full_zip_unchanged(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Milano"],
            "Zip": ["20121"],
        })
        parsed = [_make_parsed()]

        api_calls = []

        def capture_call(parsed_addr, city, zip_code, state="", street2=""):
            api_calls.append(zip_code)
            return None

        with patch.object(validator.address_validator, 'validate_address',
                          side_effect=capture_call):
            validator._validate_addresses(df, parsed)

        assert api_calls[0] == "20121"


class TestColumnMapping:
    """Column name mapping handles variations."""

    def test_italian_column_names(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Indirizzo": ["Via Roma 10"],
            "Città": ["Milano"],
            "CAP": ["20121"],
            "Nome": ["Mario Rossi"],
        })
        col_map = validator._map_columns(df)
        assert col_map["street"] == "Indirizzo"
        assert col_map["city"] == "Città"
        assert col_map["zip"] == "CAP"
        assert col_map["name"] == "Nome"

    def test_english_column_names(self):
        validator = _make_validator()
        df = pd.DataFrame({
            "Street 1": ["Via Roma 10"],
            "City": ["Milano"],
            "Zip": ["20121"],
        })
        col_map = validator._map_columns(df)
        assert col_map["street"] == "Street 1"
        assert col_map["city"] == "City"
        assert col_map["zip"] == "Zip"
