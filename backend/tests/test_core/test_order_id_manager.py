"""Tests for order_id_manager module — parsing, normalization, generation, dedup."""
import pytest
from unittest.mock import MagicMock, patch
from app.core.order_id_manager import (
    OrderIDComponents,
    parse_order_id,
    normalize_order_id,
    generate_order_ids,
    bump_version,
    find_within_file_duplicates,
    find_cross_file_duplicates,
    record_processed_orders,
)


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestParseOrderID:
    """Tests for parse_order_id()."""

    def test_standard_format(self):
        result = parse_order_id("SBX-3501494822-GENNAIO TRADE VISIBILITY-1")
        assert result is not None
        assert result.brand == "SBX"
        assert result.po == "3501494822"
        assert result.campaign == "GENNAIO TRADE VISIBILITY"
        assert result.seq == 1
        assert result.version is None

    def test_with_version_v2(self):
        result = parse_order_id("SBX-3501494822-CAMPAIGN V2-1")
        assert result is not None
        assert result.brand == "SBX"
        assert result.po == "3501494822"
        assert result.campaign == "CAMPAIGN"
        assert result.seq == 1
        assert result.version == 2

    def test_with_version_v3(self):
        result = parse_order_id("SBX-3501494822-CAMPAIGN V3-42")
        assert result is not None
        assert result.campaign == "CAMPAIGN"
        assert result.seq == 42
        assert result.version == 3

    def test_unparseable_garbage(self):
        result = parse_order_id("RANDOM GARBAGE")
        assert result is None

    def test_missing_po(self):
        result = parse_order_id("SBX--CAMPAIGN-1")
        assert result is None

    def test_empty_string(self):
        result = parse_order_id("")
        assert result is None

    def test_invalid_po_format(self):
        # PO must start with 350 followed by 7 digits
        result = parse_order_id("SBX-1234567890-CAMPAIGN-1")
        assert result is None

    def test_po_too_short(self):
        result = parse_order_id("SBX-350123-CAMPAIGN-1")
        assert result is None

    def test_multi_word_campaign(self):
        result = parse_order_id("MAC-3507654321-SUMMER BEAUTY FEST-10")
        assert result is not None
        assert result.campaign == "SUMMER BEAUTY FEST"
        assert result.seq == 10
        assert result.version is None

    def test_format_roundtrip_no_version(self):
        raw = "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"
        result = parse_order_id(raw)
        assert result is not None
        assert result.format() == raw

    def test_format_roundtrip_v2(self):
        raw = "SBX-3501494822-CAMPAIGN V2-1"
        result = parse_order_id(raw)
        assert result is not None
        assert result.format() == raw

    def test_format_roundtrip_v3(self):
        raw = "SBX-3501494822-CAMPAIGN V3-42"
        result = parse_order_id(raw)
        assert result is not None
        assert result.format() == raw

    def test_version_in_middle_of_campaign(self):
        # "V2" appearing mid-campaign should not be treated as version marker
        # e.g. "CAMPAIGN V2 EXTRA" — version is only recognised at the END
        result = parse_order_id("SBX-3501494822-CAMPAIGN V2 EXTRA-1")
        assert result is not None
        assert result.version is None
        assert result.campaign == "CAMPAIGN V2 EXTRA"


# ---------------------------------------------------------------------------
# OrderIDComponents.format() tests
# ---------------------------------------------------------------------------

class TestOrderIDComponentsFormat:
    """Tests for OrderIDComponents.format()."""

    def test_format_no_version(self):
        c = OrderIDComponents(brand="SBX", po="3501494822",
                              campaign="TEST CAMP", seq=5, version=None)
        assert c.format() == "SBX-3501494822-TEST CAMP-5"

    def test_format_v2(self):
        c = OrderIDComponents(brand="SBX", po="3501494822",
                              campaign="TEST CAMP", seq=5, version=2)
        assert c.format() == "SBX-3501494822-TEST CAMP V2-5"

    def test_format_v3(self):
        c = OrderIDComponents(brand="SBX", po="3501494822",
                              campaign="TEST CAMP", seq=5, version=3)
        assert c.format() == "SBX-3501494822-TEST CAMP V3-5"


# ---------------------------------------------------------------------------
# Normalization tests
# ---------------------------------------------------------------------------

class TestNormalizeOrderID:
    """Tests for normalize_order_id()."""

    def test_already_correct(self):
        raw = "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"
        result = normalize_order_id(raw, "SBX", "GENNAIO TRADE VISIBILITY")
        assert result == raw

    def test_wrong_brand_corrected(self):
        raw = "MAC-3501494822-GENNAIO TRADE VISIBILITY-1"
        result = normalize_order_id(raw, "SBX", "GENNAIO TRADE VISIBILITY")
        assert result == "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"

    def test_wrong_campaign_corrected(self):
        raw = "SBX-3501494822-OLD CAMPAIGN-1"
        result = normalize_order_id(raw, "SBX", "NEW CAMPAIGN")
        assert result == "SBX-3501494822-NEW CAMPAIGN-1"

    def test_preserves_version(self):
        raw = "SBX-3501494822-CAMPAIGN V2-5"
        result = normalize_order_id(raw, "SBX", "CAMPAIGN")
        assert result == "SBX-3501494822-CAMPAIGN V2-5"

    def test_preserves_version_with_brand_fix(self):
        raw = "MAC-3501494822-CAMPAIGN V3-7"
        result = normalize_order_id(raw, "SBX", "CAMPAIGN")
        assert result == "SBX-3501494822-CAMPAIGN V3-7"

    def test_unparseable_returns_none(self):
        result = normalize_order_id("GARBAGE", "SBX", "CAMPAIGN")
        assert result is None

    def test_empty_string_returns_none(self):
        result = normalize_order_id("", "SBX", "CAMPAIGN")
        assert result is None


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------

class TestGenerateOrderIDs:
    """Tests for generate_order_ids()."""

    def test_three_rows_sequential(self):
        result = generate_order_ids("SBX", ["3501494822"], "GENNAIO TRADE VISIBILITY")
        # 1 PO × 1 = 1 ID, but we pass a list of rows — need to clarify
        # generate_order_ids takes a list of PO numbers (one per row)
        assert len(result) == 1
        assert result[0] == "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"

    def test_sequential_numbering(self):
        po_numbers = ["3501494822", "3501494822", "3501494822"]
        result = generate_order_ids("SBX", po_numbers, "CAMP")
        assert result == [
            "SBX-3501494822-CAMP-1",
            "SBX-3501494822-CAMP-2",
            "SBX-3501494822-CAMP-3",
        ]

    def test_with_version_2(self):
        po_numbers = ["3501494822", "3501494822"]
        result = generate_order_ids("SBX", po_numbers, "CAMP", version=2)
        assert result == [
            "SBX-3501494822-CAMP V2-1",
            "SBX-3501494822-CAMP V2-2",
        ]

    def test_with_version_none(self):
        po_numbers = ["3501494822"]
        result = generate_order_ids("SBX", po_numbers, "CAMP", version=None)
        assert result == ["SBX-3501494822-CAMP-1"]

    def test_multiple_pos(self):
        po_numbers = ["3501494822", "3509876543"]
        result = generate_order_ids("MAC", po_numbers, "SUMMER")
        assert result[0] == "MAC-3501494822-SUMMER-1"
        assert result[1] == "MAC-3509876543-SUMMER-2"

    def test_empty_list(self):
        result = generate_order_ids("SBX", [], "CAMP")
        assert result == []


# ---------------------------------------------------------------------------
# Version bump tests
# ---------------------------------------------------------------------------

class TestBumpVersion:
    """Tests for bump_version()."""

    def test_none_to_2(self):
        assert bump_version(None) == 2

    def test_2_to_3(self):
        assert bump_version(2) == 3

    def test_3_to_4(self):
        assert bump_version(3) == 4

    def test_5_to_6(self):
        assert bump_version(5) == 6


# ---------------------------------------------------------------------------
# Within-file duplicate tests
# ---------------------------------------------------------------------------

class TestFindWithinFileDuplicates:
    """Tests for find_within_file_duplicates()."""

    def test_no_duplicates(self):
        order_numbers = [
            "SBX-3501494822-CAMP-1",
            "SBX-3501494822-CAMP-2",
            "SBX-3501494822-CAMP-3",
        ]
        result = find_within_file_duplicates(order_numbers)
        assert result == {}

    def test_exact_duplicates(self):
        order_numbers = [
            "SBX-3501494822-CAMP-1",
            "SBX-3501494822-CAMP-2",
            "SBX-3501494822-CAMP-1",  # duplicate of index 0
        ]
        result = find_within_file_duplicates(order_numbers)
        assert "SBX-3501494822-CAMP-1" in result
        assert sorted(result["SBX-3501494822-CAMP-1"]) == [0, 2]

    def test_triple_duplicate(self):
        order_numbers = ["A-3501494822-C-1"] * 3
        result = find_within_file_duplicates(order_numbers)
        assert result["A-3501494822-C-1"] == [0, 1, 2]

    def test_multiple_duplicate_groups(self):
        order_numbers = [
            "SBX-3501494822-CAMP-1",
            "SBX-3501494822-CAMP-2",
            "SBX-3501494822-CAMP-1",
            "SBX-3501494822-CAMP-2",
        ]
        result = find_within_file_duplicates(order_numbers)
        assert sorted(result["SBX-3501494822-CAMP-1"]) == [0, 2]
        assert sorted(result["SBX-3501494822-CAMP-2"]) == [1, 3]

    def test_empty_list(self):
        result = find_within_file_duplicates([])
        assert result == {}

    def test_single_item(self):
        result = find_within_file_duplicates(["SBX-3501494822-CAMP-1"])
        assert result == {}


# ---------------------------------------------------------------------------
# Cross-file duplicate tests
# ---------------------------------------------------------------------------

class TestFindCrossFileDuplicates:
    """Tests for find_cross_file_duplicates() with mocked Supabase."""

    def test_no_client_returns_empty(self):
        result = find_cross_file_duplicates(["SBX-3501494822-CAMP-1"], None)
        assert result == {}

    def test_found_matches(self):
        mock_client = MagicMock()
        match_data = {
            "order_number": "SBX-3501494822-CAMP-1",
            "processed_at": "2024-01-15T10:00:00",
            "campaign": "CAMP",
            "job_id": "job-123",
        }
        (mock_client.table.return_value
                          .select.return_value
                          .in_.return_value
                          .execute.return_value) = MagicMock(data=[match_data])

        result = find_cross_file_duplicates(["SBX-3501494822-CAMP-1"], mock_client)
        assert "SBX-3501494822-CAMP-1" in result
        assert result["SBX-3501494822-CAMP-1"]["processed_at"] == "2024-01-15T10:00:00"

    def test_no_matches_returns_empty(self):
        mock_client = MagicMock()
        (mock_client.table.return_value
                          .select.return_value
                          .in_.return_value
                          .execute.return_value) = MagicMock(data=[])

        result = find_cross_file_duplicates(["SBX-3501494822-CAMP-1"], mock_client)
        assert result == {}

    def test_supabase_error_returns_empty(self):
        mock_client = MagicMock()
        (mock_client.table.return_value
                          .select.return_value
                          .in_.return_value
                          .execute.side_effect) = Exception("DB error")

        result = find_cross_file_duplicates(["SBX-3501494822-CAMP-1"], mock_client)
        assert result == {}

    def test_empty_order_numbers_returns_empty(self):
        mock_client = MagicMock()
        result = find_cross_file_duplicates([], mock_client)
        assert result == {}


# ---------------------------------------------------------------------------
# Record processed orders tests
# ---------------------------------------------------------------------------

class TestRecordProcessedOrders:
    """Tests for record_processed_orders()."""

    def test_no_client_returns_zero(self):
        count = record_processed_orders(
            ["SBX-3501494822-CAMP-1"], "job-1", "SBX", "CAMP", "3501494822", None
        )
        assert count == 0

    def test_upserts_and_returns_count(self):
        mock_client = MagicMock()
        (mock_client.table.return_value
                          .upsert.return_value
                          .execute.return_value) = MagicMock(data=[{"order_number": "SBX-3501494822-CAMP-1"}])

        count = record_processed_orders(
            ["SBX-3501494822-CAMP-1"], "job-1", "SBX", "CAMP", "3501494822", mock_client
        )
        assert count == 1

    def test_upsert_error_returns_zero(self):
        mock_client = MagicMock()
        (mock_client.table.return_value
                          .upsert.return_value
                          .execute.side_effect) = Exception("DB error")

        count = record_processed_orders(
            ["SBX-3501494822-CAMP-1"], "job-1", "SBX", "CAMP", "3501494822", mock_client
        )
        assert count == 0

    def test_empty_order_numbers_returns_zero(self):
        mock_client = MagicMock()
        count = record_processed_orders(
            [], "job-1", "SBX", "CAMP", "3501494822", mock_client
        )
        assert count == 0
