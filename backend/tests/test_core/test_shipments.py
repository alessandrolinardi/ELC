"""Tests for app.core.shipments — URL helpers, validators, batch builder, Excel
extraction, and response parsing for ship / POD endpoints."""

import io
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.shipments import (
    _derive_batch_ship_url,
    _derive_pod_batch_url,
    _derive_pod_jobs_url,
    _derive_pod_url,
    _derive_ship_url,
    _validate_url_segment,
    build_batch_shipments,
    extract_identifiers_from_excel,
    fetch_single_pod,
    send_ship_request,
)


# ---------------------------------------------------------------------------
# 1. URL derivation helpers
# ---------------------------------------------------------------------------

class TestDeriveShipUrl:
    """_derive_ship_url replaces the last path segment with 'ship'."""

    def test_basic(self):
        assert _derive_ship_url("https://host/api/webhook/rates") == "https://host/api/webhook/ship"

    def test_trailing_slash(self):
        assert _derive_ship_url("https://host/api/webhook/rates/") == "https://host/api/webhook/ship"


class TestDeriveBatchShipUrl:
    """_derive_batch_ship_url replaces the last segment with 'ship-batch'."""

    def test_basic(self):
        assert _derive_batch_ship_url("https://host/api/webhook/rates") == "https://host/api/webhook/ship-batch"

    def test_trailing_slash(self):
        assert _derive_batch_ship_url("https://host/api/webhook/rates/") == "https://host/api/webhook/ship-batch"


class TestDerivePodUrl:
    """_derive_pod_url replaces the last segment with 'pod'."""

    def test_basic(self):
        assert _derive_pod_url("https://host/api/webhook/rates") == "https://host/api/webhook/pod"

    def test_trailing_slash(self):
        assert _derive_pod_url("https://host/api/webhook/rates/") == "https://host/api/webhook/pod"


class TestDerivePodBatchUrl:
    """_derive_pod_batch_url replaces the last segment with 'pod-batch'."""

    def test_basic(self):
        assert _derive_pod_batch_url("https://host/api/webhook/rates") == "https://host/api/webhook/pod-batch"

    def test_trailing_slash(self):
        assert _derive_pod_batch_url("https://host/api/webhook/rates/") == "https://host/api/webhook/pod-batch"


class TestDerivePodJobsUrl:
    """_derive_pod_jobs_url builds /pod-jobs/{job_id} from the rates URL."""

    def test_basic(self):
        result = _derive_pod_jobs_url("https://host/api/webhook/rates", "abc123")
        assert result == "https://host/api/webhook/pod-jobs/abc123"

    def test_trailing_slash(self):
        result = _derive_pod_jobs_url("https://host/api/webhook/rates/", "abc123")
        assert result == "https://host/api/webhook/pod-jobs/abc123"


# ---------------------------------------------------------------------------
# 2. _validate_url_segment
# ---------------------------------------------------------------------------

class TestValidateUrlSegment:
    """Rejects path-traversal / injection chars; allows safe segments."""

    def test_valid_alphanumeric(self):
        _validate_url_segment("abc123", "test")  # should not raise

    def test_valid_hyphen(self):
        _validate_url_segment("abc-def", "test")

    def test_valid_underscore(self):
        _validate_url_segment("abc_def", "test")

    def test_valid_dot(self):
        _validate_url_segment("abc.def", "test")

    def test_invalid_path_traversal(self):
        with pytest.raises(ValueError):
            _validate_url_segment("../etc", "test")

    def test_invalid_slash(self):
        with pytest.raises(ValueError):
            _validate_url_segment("abc/def", "test")

    def test_invalid_empty(self):
        with pytest.raises(ValueError):
            _validate_url_segment("", "test")

    def test_invalid_space(self):
        with pytest.raises(ValueError):
            _validate_url_segment("abc def", "test")


# ---------------------------------------------------------------------------
# 3. build_batch_shipments
# ---------------------------------------------------------------------------

class TestBuildBatchShipments:
    """Enriches parsed shipments with carrier info and sequential IDs."""

    _PARSED = [
        {
            "to_address": {"name": "Alice", "street1": "Via Roma 1", "city": "Milano", "zip": "20100", "country": "IT", "phone": ""},
            "parcels": [{"length": 10, "width": 10, "height": 10, "weight": 1.0}],
        },
        {
            "to_address": {"name": "Bob", "street1": "Via Dante 2", "city": "Roma", "zip": "00100", "country": "IT", "phone": ""},
            "parcels": [{"length": 20, "width": 20, "height": 20, "weight": 2.0}],
        },
    ]
    _FROM_ADDR = {"name": "Warehouse", "street1": "Via Logistica 99", "city": "Torino", "zip": "10100", "country": "IT", "phone": "011111"}

    def test_enriches_with_carrier_and_from_address(self):
        batch = build_batch_shipments(
            self._PARSED, carrier_name="BRT", carrier_id=42, carrier_service="Express",
            from_address=self._FROM_ADDR, transaction_id_prefix="TX",
        )
        assert len(batch) == 2
        for row in batch:
            assert row["carrier_name"] == "BRT"
            assert row["carrier_id"] == 42
            assert row["carrier_service"] == "Express"
            assert row["from_address"] is self._FROM_ADDR

    def test_sequential_transaction_ids(self):
        batch = build_batch_shipments(
            self._PARSED, carrier_name="BRT", carrier_id=42, carrier_service="Express",
            from_address=self._FROM_ADDR, transaction_id_prefix="BATCH-20240101",
        )
        assert batch[0]["transaction_id"] == "BATCH-20240101-1"
        assert batch[1]["transaction_id"] == "BATCH-20240101-2"

    def test_empty_prefix_omits_transaction_id(self):
        batch = build_batch_shipments(
            self._PARSED, carrier_name="BRT", carrier_id=42, carrier_service="Express",
            from_address=self._FROM_ADDR, transaction_id_prefix="",
        )
        for row in batch:
            assert "transaction_id" not in row


# ---------------------------------------------------------------------------
# 4. extract_identifiers_from_excel
# ---------------------------------------------------------------------------

def _make_excel_bytes(df: pd.DataFrame) -> bytes:
    """Helper: write a DataFrame to .xlsx bytes in memory."""
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


class TestExtractIdentifiersFromExcel:
    """Parses uploaded Excel to pull POD identifiers."""

    @patch("app.core.shipments.ExcelParser")
    def test_shippypro_order_column_priority(self, MockParser):
        """When 'Numero ordine ShippyPro' is present it takes priority."""
        df = pd.DataFrame({
            "Numero ordine ShippyPro": ["SP001", "SP002"],
            "Tracking": ["TRK-A", "TRK-B"],
        })
        instance = MockParser.return_value
        instance._try_read_excel.return_value = df
        instance._find_column.return_value = None

        ids, meta = extract_identifiers_from_excel(_make_excel_bytes(df))

        assert ids == ["SP001", "SP002"]

    @patch("app.core.shipments.ExcelParser")
    def test_tracking_alias_found_in_dict(self, MockParser):
        """'Tracking' column matches via the alias dict (not _find_column fallback)."""
        df = pd.DataFrame({"Tracking": ["TRK-X", "TRK-Y"]})
        instance = MockParser.return_value
        instance._try_read_excel.return_value = df
        instance._find_column.return_value = None

        ids, meta = extract_identifiers_from_excel(_make_excel_bytes(df))

        assert ids == ["TRK-X", "TRK-Y"]
        # _find_column should NOT be called — alias dict matched first
        instance._find_column.assert_not_called()

    @patch("app.core.shipments.ExcelParser")
    def test_find_column_fallback(self, MockParser):
        """When no alias matches, falls back to ExcelParser._find_column."""
        df = pd.DataFrame({"Codice Spedizione": ["CS-1", "CS-2"]})
        instance = MockParser.return_value
        instance._try_read_excel.return_value = df
        # No alias matches "Codice Spedizione", so _find_column is called
        instance._find_column.return_value = "Codice Spedizione"

        ids, meta = extract_identifiers_from_excel(_make_excel_bytes(df))

        assert ids == ["CS-1", "CS-2"]
        instance._find_column.assert_called_once_with(df, 'tracking')

    @patch("app.core.shipments.ExcelParser")
    def test_no_matching_column_raises(self, MockParser):
        """ValueError when the Excel has no recognisable identifier column."""
        df = pd.DataFrame({"Foo": [1, 2], "Bar": [3, 4]})
        instance = MockParser.return_value
        instance._try_read_excel.return_value = df
        instance._find_column.return_value = None

        with pytest.raises(ValueError, match="Nessuna colonna identificativo"):
            extract_identifiers_from_excel(_make_excel_bytes(df))


# ---------------------------------------------------------------------------
# 5. fetch_single_pod response parsing
# ---------------------------------------------------------------------------

class TestFetchSinglePod:
    """Tests for fetch_single_pod with mocked HTTP and config."""

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_200_found(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "pod_base64": "AAAA",
            "tracking_number": "TRK1",
            "carrier": "BRT",
            "file_type": "application/pdf",
        }
        mock_post.return_value = mock_resp

        result = fetch_single_pod("TRK1")

        assert result["status"] == "found"
        assert result["pod_base64"] == "AAAA"
        assert result["tracking_number"] == "TRK1"
        assert result["carrier"] == "BRT"

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_404_not_found(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"detail": "Not found"}
        mock_post.return_value = mock_resp

        result = fetch_single_pod("TRK-MISSING")

        assert result["status"] == "not_found"

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_409_ambiguous(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_resp.json.return_value = {"detail": "Multiple matches"}
        mock_post.return_value = mock_resp

        result = fetch_single_pod("AMBIG")

        assert result["status"] == "ambiguous"

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_429_rate_limit(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {}
        mock_post.return_value = mock_resp

        result = fetch_single_pod("X")

        assert result["status"] == "error"
        assert "Rate limit" in result["error_message"]


# ---------------------------------------------------------------------------
# 6. send_ship_request response parsing
# ---------------------------------------------------------------------------

class TestSendShipRequest:
    """Tests for send_ship_request with mocked HTTP and config."""

    _SHIP_DATA = {
        "carrier_name": "BRT",
        "carrier_id": 42,
        "carrier_service": "Express",
        "from_address": {"name": "WH"},
        "to_address": {"name": "Customer"},
        "parcels": [{"weight": 1}],
    }

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_200_shipped(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "shipped",
            "sp_order_id": "SP-999",
            "tracking_number": "TRK-SHIP",
            "label_url": "https://labels/1.pdf",
        }
        mock_post.return_value = mock_resp

        result = send_ship_request(self._SHIP_DATA)

        assert result["status"] == "shipped"
        assert result["sp_order_id"] == "SP-999"
        assert result["tracking_number"] == "TRK-SHIP"
        assert result["label_url"] == "https://labels/1.pdf"

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_200_failed(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "failed",
            "error_message": "Invalid postcode",
            "error_details": {"field": "zip"},
        }
        mock_post.return_value = mock_resp

        result = send_ship_request(self._SHIP_DATA)

        assert result["status"] == "failed"
        assert result["error_message"] == "Invalid postcode"
        assert result["error_details"] == {"field": "zip"}

    @patch("app.core.shipments.get_secret")
    @patch("app.core.shipments.requests.post")
    def test_non_200_http_error(self, mock_post, mock_secret):
        mock_secret.return_value = "https://host/api/webhook/rates"
        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_resp.json.return_value = {"detail": "Bad Gateway"}
        mock_post.return_value = mock_resp

        result = send_ship_request(self._SHIP_DATA)

        assert result["status"] == "failed"
        assert "502" in result["error_message"]
