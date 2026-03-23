"""Integration tests for the full Order ID flow."""
from app.core.order_id_manager import (
    parse_order_id, normalize_order_id, generate_order_ids,
    find_within_file_duplicates, bump_version,
)


class TestFullOrderIDFlow:
    def test_parse_normalize_roundtrip(self):
        raw = "SBX-3501494822-GENNAIO TRADE VISIBILITY-1"
        parsed = parse_order_id(raw)
        assert parsed is not None
        normalized = normalize_order_id(raw, "SBX", "GENNAIO TRADE VISIBILITY")
        assert normalized == raw

    def test_reupload_version_bump_flow(self):
        """Simulate: original upload → detect duplicate → user says re-upload → V2."""
        # Original upload
        original = generate_order_ids("SBX", ["3501494822"] * 3, "CAMPAIGN")
        assert original[0] == "SBX-3501494822-CAMPAIGN-1"
        assert original[2] == "SBX-3501494822-CAMPAIGN-3"

        # Detect duplicate → user says "yes, re-upload"
        new_version = bump_version(None)  # original had no version
        assert new_version == 2

        reupload = generate_order_ids("SBX", ["3501494822"] * 3, "CAMPAIGN", version=new_version)
        assert reupload[0] == "SBX-3501494822-CAMPAIGN V2-1"
        assert reupload[0] != original[0]  # ShippyPro sees different ID

        # Parse V2 back
        parsed_v2 = parse_order_id(reupload[0])
        assert parsed_v2 is not None
        assert parsed_v2.version == 2
        assert parsed_v2.campaign == "CAMPAIGN"

    def test_second_reupload_v3(self):
        """V2 already processed → next re-upload should be V3."""
        v2 = generate_order_ids("SBX", ["3501494822"], "CAMPAIGN", version=2)
        parsed = parse_order_id(v2[0])
        assert parsed is not None

        v3_version = bump_version(parsed.version)
        assert v3_version == 3

        v3 = generate_order_ids("SBX", ["3501494822"], "CAMPAIGN", version=v3_version)
        assert v3[0] == "SBX-3501494822-CAMPAIGN V3-1"

    def test_within_file_duplicate_detection(self):
        orders = generate_order_ids("SBX", ["3501494822"] * 3, "CAMPAIGN")
        # Inject a duplicate
        orders.append(orders[0])
        dupes = find_within_file_duplicates(orders)
        assert orders[0] in dupes
        assert dupes[orders[0]] == [0, 3]

    def test_normalize_fixes_brand(self):
        """User uploads with wrong brand → normalization fixes it."""
        raw = "WRONG-3501494822-SUMMER SALE-5"
        fixed = normalize_order_id(raw, "DOUGLAS", "SUMMER SALE")
        assert fixed == "DOUGLAS-3501494822-SUMMER SALE-5"

    def test_normalize_preserves_version_on_reupload(self):
        """Re-uploaded V2 order → normalization keeps V2."""
        raw = "SBX-3501494822-CAMPAIGN V2-10"
        fixed = normalize_order_id(raw, "SBX", "CAMPAIGN")
        assert fixed == "SBX-3501494822-CAMPAIGN V2-10"

    def test_format_roundtrip_all_variants(self):
        """Parse → format for various Order ID patterns."""
        cases = [
            "SBX-3501494822-CAMPAIGN-1",
            "DOUGLAS-3501494822-XMAS 2026-42",
            "SBX-3501494822-GENNAIO TRADE VISIBILITY V2-100",
            "SBX-3501494822-TEST V3-1",
        ]
        for raw in cases:
            parsed = parse_order_id(raw)
            assert parsed is not None, f"Failed to parse: {raw}"
            assert parsed.format() == raw, f"Roundtrip failed: {raw} → {parsed.format()}"
