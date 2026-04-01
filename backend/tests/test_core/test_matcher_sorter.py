"""
Tests for Matcher and Sorter modules.
"""

import pytest

from app.core.matcher import (
    Matcher,
    MatchReport,
    MatchResult,
    MatchType,
    UnmatchedReason,
    match_pdf_to_excel,
)
from app.core.sorter import Sorter, SortMethod, SortedResult, sort_pages
from app.core.excel_parser import ExcelData, OrderInfo
from app.core.pdf_processor import PageInfo, PDFData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_order(
    row_index: int,
    order_id: str,
    tracking: str,
    carrier: str = "DHL",
    numeric_suffix: int | None = None,
) -> OrderInfo:
    return OrderInfo(
        row_index=row_index,
        order_id=order_id,
        tracking=tracking,
        carrier=carrier,
        numeric_suffix=numeric_suffix,
    )


def _make_excel(orders: list[OrderInfo]) -> ExcelData:
    return ExcelData(
        orders=orders,
        total_rows=len(orders),
        columns_found=["Order ID", "Tracking", "Carrier"],
        warnings=[],
    )


def _make_page(
    page_number: int,
    tracking: str | None,
    carrier: str | None = "DHL",
    raw_text: str = "",
    extraction_error: str | None = None,
) -> PageInfo:
    return PageInfo(
        page_number=page_number,
        tracking=tracking,
        carrier=carrier,
        raw_text=raw_text,
        extraction_error=extraction_error,
    )


def _make_pdf(pages: list[PageInfo]) -> PDFData:
    return PDFData(
        pages=pages,
        total_pages=len(pages),
        pdf_bytes=b"",
    )


# ===========================================================================
# Matcher Tests
# ===========================================================================


class TestMatcherExactMatch:
    """Test 1: Exact match - identical tracking in PDF and Excel."""

    def test_exact_match_returns_confidence_100(self):
        excel = _make_excel([_make_order(0, "ORD-1", "ABC123")])
        pdf = _make_pdf([_make_page(1, "ABC123")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        assert len(report.unmatched) == 0
        result = report.matched[0]
        assert result.match_confidence == 100
        assert result.match_type == MatchType.EXACT
        assert result.order is not None
        assert result.order.tracking == "ABC123"

    def test_exact_match_case_insensitive(self):
        excel = _make_excel([_make_order(0, "ORD-1", "ABC123")])
        pdf = _make_pdf([_make_page(1, "abc123")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        assert report.matched[0].match_type == MatchType.EXACT
        assert report.matched[0].match_confidence == 100


class TestMatcherNormalizedMatch:
    """Test 2: Normalized match - whitespace differences."""

    def test_whitespace_stripped_yields_normalized_or_exact(self):
        # Excel stores "ABC123", PDF extracts "ABC 123"
        # The Matcher normalizes PDF tracking via upper().replace(' ', '')
        # which turns "ABC 123" -> "ABC123", so it will be EXACT
        # since the index already has "ABC123" -> order.
        # However, the *original* PDF tracking is "ABC 123" which differs
        # from the index key.  Let's verify the match happens.
        excel = _make_excel([_make_order(0, "ORD-1", "ABC123")])
        pdf = _make_pdf([_make_page(1, "ABC 123")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        # After normalization the lookup key is "ABC123" which is in the
        # index, so the matcher treats it as EXACT (confidence 100).
        assert result.match_confidence >= 98
        assert result.match_type in (MatchType.EXACT, MatchType.NORMALIZED)


class TestMatcherLeadingZeroNormalization:
    """Test 3: Leading zero normalization."""

    def test_leading_zeros_stripped_for_match(self):
        # Excel has "1234", PDF has "0001234"
        # Matcher indexes stripped variant "1234" for the order.
        # PDF tracking "0001234" -> normalized "0001234", then stripped "1234"
        # -> should match as NORMALIZED with confidence ~98
        excel = _make_excel([_make_order(0, "ORD-1", "1234")])
        pdf = _make_pdf([_make_page(1, "0001234")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        assert result.match_type == MatchType.NORMALIZED
        assert result.match_confidence == 98

    def test_excel_leading_zeros_stripped_matches_pdf_without(self):
        # Excel has "0001234", PDF has "1234"
        # The index stores stripped variant "1234" -> order.
        excel = _make_excel([_make_order(0, "ORD-1", "0001234")])
        pdf = _make_pdf([_make_page(1, "1234")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        assert result.match_type == MatchType.EXACT
        assert result.match_confidence == 100


class TestMatcherPartialMatch:
    """Test 4: Partial match - suffix/prefix overlap."""

    def test_pdf_tracking_ends_with_excel_tracking(self):
        # PDF tracking is longer but ends with the Excel tracking.
        # Overlap must be >= 80%.
        # Excel: "12345678901234" (14 chars)
        # PDF:   "XX12345678901234" (16 chars) -> overlap 14/16 = 87.5%
        excel = _make_excel([_make_order(0, "ORD-1", "12345678901234")])
        pdf = _make_pdf([_make_page(1, "XX12345678901234")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        assert result.match_type == MatchType.PARTIAL
        assert 90 <= result.match_confidence <= 99

    def test_excel_tracking_ends_with_pdf_tracking(self):
        # Excel: "XX12345678901234" (16 chars)
        # PDF:   "12345678901234" (14 chars) -> overlap 14/16 = 87.5%
        excel = _make_excel([_make_order(0, "ORD-1", "XX12345678901234")])
        pdf = _make_pdf([_make_page(1, "12345678901234")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        assert result.match_type == MatchType.PARTIAL
        assert 90 <= result.match_confidence <= 99


class TestMatcherFuzzyMatch:
    """Test 5: Fuzzy match - 1-2 character differences."""

    def test_one_char_difference_fuzzy_match(self):
        # Same length, 1 character different
        excel = _make_excel([_make_order(0, "ORD-1", "ABCDEFGHIJ")])
        pdf = _make_pdf([_make_page(1, "ABCDEFGHIK")])  # J -> K

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        assert result.match_type == MatchType.FUZZY
        # 1 difference -> confidence = 95 - 10 = 85
        assert result.match_confidence == 85

    def test_two_char_difference_fuzzy_match(self):
        excel = _make_excel([_make_order(0, "ORD-1", "ABCDEFGHIJ")])
        pdf = _make_pdf([_make_page(1, "XBCDEFGHIK")])  # A->X, J->K

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 1
        result = report.matched[0]
        assert result.match_type == MatchType.FUZZY
        # 2 differences -> confidence = 95 - 20 = 75
        assert result.match_confidence == 75


class TestMatcherNoMatch:
    """Test 6: No match - completely different tracking."""

    def test_completely_different_tracking_unmatched(self):
        excel = _make_excel([_make_order(0, "ORD-1", "AAAABBBBCCCC")])
        pdf = _make_pdf([_make_page(1, "ZZZZYYYYXXXX")])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 0
        assert len(report.unmatched) == 1
        result = report.unmatched[0]
        assert result.matched is False
        assert result.unmatched_reason == UnmatchedReason.TRACKING_NOT_IN_EXCEL
        assert result.match_type == MatchType.NONE
        assert result.match_confidence == 0


class TestMatcherMultiplePages:
    """Test 7: Multiple PDF pages, some match, some don't."""

    def test_mixed_matched_and_unmatched(self):
        excel = _make_excel([
            _make_order(0, "ORD-1", "TRACK001"),
            _make_order(1, "ORD-2", "TRACK002"),
        ])
        pdf = _make_pdf([
            _make_page(1, "TRACK001"),  # matches
            _make_page(2, "TRACK002"),  # matches
            _make_page(3, "TRACK999"),  # no match
            _make_page(4, None),        # no tracking extracted
        ])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 2
        assert len(report.unmatched) == 2
        assert report.total_pages == 4

        # Verify unmatched reasons
        unmatched_reasons = {r.page_number: r.unmatched_reason for r in report.unmatched}
        assert unmatched_reasons[3] == UnmatchedReason.TRACKING_NOT_IN_EXCEL
        assert unmatched_reasons[4] == UnmatchedReason.TRACKING_NOT_RECOGNIZED


class TestMatcherMatchRate:
    """Test 8: match_rate is computed correctly."""

    def test_match_rate_calculation(self):
        excel = _make_excel([
            _make_order(0, "ORD-1", "TRACK001"),
        ])
        pdf = _make_pdf([
            _make_page(1, "TRACK001"),  # matches
            _make_page(2, "TRACKXXX"),  # no match
            _make_page(3, "TRACKYYY"),  # no match
            _make_page(4, "TRACKZZZ"),  # no match
        ])

        report = match_pdf_to_excel(pdf, excel)

        # 1 out of 4 matched = 25.0%
        assert report.match_rate == 25.0

    def test_match_rate_100_percent(self):
        excel = _make_excel([
            _make_order(0, "ORD-1", "TRACK001"),
            _make_order(1, "ORD-2", "TRACK002"),
        ])
        pdf = _make_pdf([
            _make_page(1, "TRACK001"),
            _make_page(2, "TRACK002"),
        ])

        report = match_pdf_to_excel(pdf, excel)

        assert report.match_rate == 100.0


class TestMatcherEmptyExcel:
    """Test 9: Empty Excel - all PDF pages should be unmatched."""

    def test_all_unmatched_with_empty_excel(self):
        excel = _make_excel([])
        pdf = _make_pdf([
            _make_page(1, "TRACK001"),
            _make_page(2, "TRACK002"),
        ])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 0
        assert len(report.unmatched) == 2
        assert report.match_rate == 0.0
        for r in report.unmatched:
            assert r.unmatched_reason == UnmatchedReason.TRACKING_NOT_IN_EXCEL


class TestMatcherDuplicateTracking:
    """Test 10: Duplicate tracking in PDF - each matches independently."""

    def test_duplicate_tracking_in_pdf_each_matches(self):
        excel = _make_excel([
            _make_order(0, "ORD-1", "TRACK001"),
        ])
        pdf = _make_pdf([
            _make_page(1, "TRACK001"),
            _make_page(2, "TRACK001"),
        ])

        report = match_pdf_to_excel(pdf, excel)

        assert len(report.matched) == 2
        assert len(report.unmatched) == 0
        # Both should reference the same order
        assert report.matched[0].order.order_id == "ORD-1"
        assert report.matched[1].order.order_id == "ORD-1"
        assert report.matched[0].match_type == MatchType.EXACT
        assert report.matched[1].match_type == MatchType.EXACT


# ===========================================================================
# Sorter Tests
# ===========================================================================


def _make_match_result(
    page_number: int,
    page_index: int,
    tracking: str,
    order: OrderInfo | None = None,
    matched: bool = True,
) -> MatchResult:
    return MatchResult(
        page_number=page_number,
        page_index=page_index,
        tracking=tracking,
        carrier="DHL",
        matched=matched,
        order=order,
        match_type=MatchType.EXACT if matched else MatchType.NONE,
        match_confidence=100 if matched else 0,
    )


class TestSorterExcelOrder:
    """Test 1: Sort by Excel row order."""

    def test_pages_reordered_to_match_excel_rows(self):
        orders = [
            _make_order(0, "ORD-A", "TRACK_A"),
            _make_order(1, "ORD-B", "TRACK_B"),
            _make_order(2, "ORD-C", "TRACK_C"),
        ]
        excel = _make_excel(orders)

        # PDF pages arrive in reverse order relative to Excel
        matched = [
            _make_match_result(3, 2, "TRACK_C", order=orders[2]),
            _make_match_result(2, 1, "TRACK_B", order=orders[1]),
            _make_match_result(1, 0, "TRACK_A", order=orders[0]),
        ]

        report = MatchReport(
            matched=matched,
            unmatched=[],
            total_pages=3,
            match_rate=100.0,
        )

        result = sort_pages(report, excel, SortMethod.EXCEL_ORDER)

        # After sorting by Excel order (A=row0, B=row1, C=row2),
        # page indices should be [0, 1, 2] (A's page, B's page, C's page).
        assert result.page_order == [0, 1, 2]
        assert result.matched_count == 3
        assert result.unmatched_count == 0
        assert result.sort_method == SortMethod.EXCEL_ORDER


class TestSorterOrderIdNumeric:
    """Test 2: Sort by order_id numeric suffix."""

    def test_pages_sorted_by_numeric_suffix(self):
        orders = [
            _make_order(0, "ORD_ORIGINS_30", "TRACK_30", numeric_suffix=30),
            _make_order(1, "ORD_ORIGINS_10", "TRACK_10", numeric_suffix=10),
            _make_order(2, "ORD_ORIGINS_20", "TRACK_20", numeric_suffix=20),
        ]
        excel = _make_excel(orders)

        matched = [
            _make_match_result(1, 0, "TRACK_30", order=orders[0]),
            _make_match_result(2, 1, "TRACK_10", order=orders[1]),
            _make_match_result(3, 2, "TRACK_20", order=orders[2]),
        ]

        report = MatchReport(
            matched=matched,
            unmatched=[],
            total_pages=3,
            match_rate=100.0,
        )

        result = sort_pages(report, excel, SortMethod.ORDER_ID_NUMERIC)

        # Sorted by numeric suffix: 10 (page_index 1), 20 (page_index 2), 30 (page_index 0)
        assert result.page_order == [1, 2, 0]
        assert result.sort_method == SortMethod.ORDER_ID_NUMERIC


class TestSorterUnmatchedAppended:
    """Test 3: Unmatched pages are appended at the end regardless of sort method."""

    def test_unmatched_at_end_excel_order(self):
        orders = [
            _make_order(0, "ORD-A", "TRACK_A"),
        ]
        excel = _make_excel(orders)

        matched = [
            _make_match_result(1, 0, "TRACK_A", order=orders[0]),
        ]
        unmatched = [
            _make_match_result(2, 1, "UNKNOWN1", matched=False),
            _make_match_result(3, 2, "UNKNOWN2", matched=False),
        ]

        report = MatchReport(
            matched=matched,
            unmatched=unmatched,
            total_pages=3,
            match_rate=33.3,
        )

        result = sort_pages(report, excel, SortMethod.EXCEL_ORDER)

        assert result.page_order == [0, 1, 2]
        assert result.matched_count == 1
        assert result.unmatched_count == 2
        # Unmatched indices (1, 2) come after matched index (0)

    def test_unmatched_at_end_order_id(self):
        orders = [
            _make_order(0, "ORD_10", "TRACK_10", numeric_suffix=10),
        ]
        excel = _make_excel(orders)

        matched = [
            _make_match_result(1, 0, "TRACK_10", order=orders[0]),
        ]
        unmatched = [
            _make_match_result(2, 1, "UNKNOWN", matched=False),
        ]

        report = MatchReport(
            matched=matched,
            unmatched=unmatched,
            total_pages=2,
            match_rate=50.0,
        )

        result = sort_pages(report, excel, SortMethod.ORDER_ID_NUMERIC)

        # Matched page first, unmatched last
        assert result.page_order == [0, 1]
        assert result.matched_count == 1
        assert result.unmatched_count == 1


class TestSorterEmptyMatched:
    """Test 4: Empty matched list - result is just the unmatched pages."""

    def test_only_unmatched_pages(self):
        excel = _make_excel([])

        unmatched = [
            _make_match_result(1, 0, "UNKNOWN1", matched=False),
            _make_match_result(2, 1, "UNKNOWN2", matched=False),
        ]

        report = MatchReport(
            matched=[],
            unmatched=unmatched,
            total_pages=2,
            match_rate=0.0,
        )

        result = sort_pages(report, excel, SortMethod.EXCEL_ORDER)

        assert result.page_order == [0, 1]
        assert result.matched_count == 0
        assert result.unmatched_count == 2


class TestSorterAllMatched:
    """Test 5: All pages matched - no unmatched section."""

    def test_all_matched_no_unmatched(self):
        orders = [
            _make_order(0, "ORD-A", "TRACK_A"),
            _make_order(1, "ORD-B", "TRACK_B"),
        ]
        excel = _make_excel(orders)

        matched = [
            _make_match_result(2, 1, "TRACK_B", order=orders[1]),
            _make_match_result(1, 0, "TRACK_A", order=orders[0]),
        ]

        report = MatchReport(
            matched=matched,
            unmatched=[],
            total_pages=2,
            match_rate=100.0,
        )

        result = sort_pages(report, excel, SortMethod.EXCEL_ORDER)

        # Sorted by Excel row: A (row 0) then B (row 1)
        assert result.page_order == [0, 1]
        assert result.matched_count == 2
        assert result.unmatched_count == 0
