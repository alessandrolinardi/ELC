"""Tests for app.core.pickup — CARRIER_MAP, _generate_order_id, _split_time_window, _build_zapier_payload."""
from datetime import date, time
from unittest.mock import patch, MagicMock

from app.core.pickup import CARRIER_MAP, _generate_order_id, _split_time_window, _build_zapier_payload, cancel_pickup_flow
from app.core.pickup_store import get_pickup, cancel_pickup, update_zapier_status


class TestCarrierMap:
    """CARRIER_MAP should contain the expected carrier entries."""

    def test_carrier_map_entries(self):
        assert CARRIER_MAP["DHL"] == {"carrier_name": "MyDHL", "carrier_id": 9536}
        assert CARRIER_MAP["UPS"] == {"carrier_name": "UPSv2", "carrier_id": 7743}
        assert CARRIER_MAP["FedEx"] == {"carrier_name": "FedExv2", "carrier_id": 3699}


class TestGenerateOrderId:
    """_generate_order_id should produce deterministic, collision-resistant hashes."""

    def test_deterministic_same_inputs(self):
        """Same inputs always produce the same order_id."""
        args = ("DHL", date(2026, 3, 27), "Acme Srl", "20121", time(9, 0))
        id1 = _generate_order_id(*args)
        id2 = _generate_order_id(*args)
        assert id1 == id2
        assert id1.startswith("ELC-")

    def test_different_inputs_produce_different_ids(self):
        """Changing any input should change the order_id."""
        base = ("DHL", date(2026, 3, 27), "Acme Srl", "20121", time(9, 0))
        base_id = _generate_order_id(*base)

        # Different carrier
        assert _generate_order_id("UPS", date(2026, 3, 27), "Acme Srl", "20121", time(9, 0)) != base_id
        # Different date
        assert _generate_order_id("DHL", date(2026, 3, 28), "Acme Srl", "20121", time(9, 0)) != base_id
        # Different time_start
        assert _generate_order_id("DHL", date(2026, 3, 27), "Acme Srl", "20121", time(14, 0)) != base_id


class TestSplitTimeWindow:
    """_split_time_window should split time ranges around the midday boundary."""

    def test_window_straddling_midday(self):
        """A window from 09:00-16:00 should be split at 13:00."""
        result = _split_time_window(time(9, 0), time(16, 0))
        assert result == {
            "PickupMorningMintime": "09:00",
            "PickupMorningMaxtime": "13:00",
            "PickupAfternoonMintime": "13:00",
            "PickupAfternoonMaxtime": "16:00",
        }

    def test_window_entirely_morning(self):
        """A window from 08:00-12:00 should only populate morning fields."""
        result = _split_time_window(time(8, 0), time(12, 0))
        assert result == {
            "PickupMorningMintime": "08:00",
            "PickupMorningMaxtime": "12:00",
            "PickupAfternoonMintime": "",
            "PickupAfternoonMaxtime": "",
        }

    def test_window_entirely_afternoon(self):
        """A window from 14:00-18:00 should only populate afternoon fields."""
        result = _split_time_window(time(14, 0), time(18, 0))
        assert result == {
            "PickupMorningMintime": "",
            "PickupMorningMaxtime": "",
            "PickupAfternoonMintime": "14:00",
            "PickupAfternoonMaxtime": "18:00",
        }


class TestGetPickup:
    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_record_when_found(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [{"id": "abc-123", "carrier": "DHL", "pickup_status": None}]
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        result = get_pickup("abc-123")
        assert result == {"id": "abc-123", "carrier": "DHL", "pickup_status": None}
        mock_client.table.assert_called_with("elc_pickups")

    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_none_when_not_found(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response
        result = get_pickup("nonexistent")
        assert result is None


class TestCancelPickup:
    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_updated_record_on_success(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [{"id": "abc-123", "pickup_status": "cancelled", "cancelled_at": "2026-04-08T12:00:00Z"}]
        mock_client.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = mock_response
        result = cancel_pickup("abc-123", "cambio data")
        assert result is not None
        assert result["pickup_status"] == "cancelled"

    @patch("app.core.pickup_store.get_supabase_client")
    def test_returns_none_when_already_cancelled(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = mock_response
        result = cancel_pickup("abc-123", None)
        assert result is None

    @patch("app.core.pickup_store.get_supabase_client")
    def test_cancel_with_null_reason(self, mock_client_fn):
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [{"id": "abc-123", "pickup_status": "cancelled"}]
        mock_client.table.return_value.update.return_value.eq.return_value.neq.return_value.execute.return_value = mock_response
        result = cancel_pickup("abc-123", None)
        assert result is not None
        update_call = mock_client.table.return_value.update.call_args[0][0]
        assert update_call["cancellation_reason"] is None


class TestBuildZapierPayload:
    SAMPLE_RECORD = {
        "id": "abc-123",
        "carrier": "DHL",
        "pickup_date": "2026-04-10",
        "time_start": "09:00:00",
        "time_end": "16:00:00",
        "company": "Acme Srl",
        "contact_name": "Mario Rossi",
        "address": "Via Roma 1",
        "zip_code": "20121",
        "city": "Milano",
        "province": "MI",
        "phone": "0212345678",
        "reference": "ORD-001",
        "num_packages": 3,
        "weight_per_package": 5.0,
        "length": 30.0,
        "width": 20.0,
        "height": 10.0,
        "use_pallet": False,
        "num_pallets": 0,
        "pallet_length": 0.0,
        "pallet_width": 0.0,
        "pallet_height": 0.0,
        "notes": "Fragile",
        "pickup_status": "booked",
        "pickup_id": None,
        "confirmation_id": None,
        "created_at": "2026-04-08T10:00:00Z",
    }

    def test_creation_payload_has_event_type(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["event_type"] == "creation"

    def test_cancellation_payload_has_event_type(self):
        record = {**self.SAMPLE_RECORD, "cancellation_reason": "cambio data", "cancelled_at": "2026-04-08T14:30:00+00:00"}
        payload = _build_zapier_payload(record, "cancellation")
        assert payload["event_type"] == "cancellation"
        assert payload["cancellation_reason"] == "cambio data"
        assert "cancelled_at" in payload
        assert payload["subject"].startswith("ANNULLAMENTO")

    def test_creation_payload_has_no_cancellation_fields(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert "cancellation_reason" not in payload
        assert "cancelled_at" not in payload

    def test_shipment_type_normal(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["shipment_type"] == "NORMAL"
        assert payload["total_weight"] == 15.0

    def test_shipment_type_freight(self):
        record = {**self.SAMPLE_RECORD, "num_packages": 10, "weight_per_package": 8.0}
        payload = _build_zapier_payload(record, "creation")
        assert payload["shipment_type"] == "FREIGHT"
        assert payload["total_weight"] == 80.0

    def test_direct_passthrough_fields(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["carrier"] == "DHL"
        assert payload["company"] == "Acme Srl"
        assert payload["contact_name"] == "Mario Rossi"
        assert payload["reference"] == "ORD-001"
        assert payload["phone"] == "0212345678"
        assert payload["zip_code"] == "20121"

    def test_derived_fields(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert payload["pickup_date"] == "10/04/2026"
        assert payload["time_window"] == "09:00 - 16:00"
        assert payload["full_address"] == "Via Roma 1, 20121 Milano (MI)"
        assert payload["address_line1"] == "Acme Srl - Mario Rossi"
        assert payload["package_dimensions"] == "30.0 x 20.0 x 10.0 cm"
        assert payload["summary_packages"] == "3 colli x 5.0 kg = 15.0 kg totali"
        assert payload["has_notes"] is True

    def test_creation_includes_pickup_webhook(self):
        payload = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        assert "pickup_webhook" in payload

    def test_cancellation_excludes_pickup_webhook(self):
        record = {**self.SAMPLE_RECORD, "cancellation_reason": None, "cancelled_at": "2026-04-08T14:30:00+00:00"}
        payload = _build_zapier_payload(record, "cancellation")
        assert "pickup_webhook" not in payload

    def test_both_event_types_share_base_fields(self):
        record_cancel = {**self.SAMPLE_RECORD, "cancellation_reason": None, "cancelled_at": "2026-04-08T14:30:00+00:00"}
        creation = _build_zapier_payload(self.SAMPLE_RECORD, "creation")
        cancellation = _build_zapier_payload(record_cancel, "cancellation")
        skip_keys = {"event_type", "subject", "request_id", "timestamp", "cancellation_reason", "cancelled_at", "pickup_webhook"}
        for key in creation:
            if key not in skip_keys:
                assert creation[key] == cancellation[key], f"Field {key} differs"


class TestCancelPickupFlow:
    UPCOMING_RECORD = {
        "id": "abc-123",
        "carrier": "DHL",
        "pickup_date": "2099-12-31",
        "time_start": "09:00:00",
        "time_end": "16:00:00",
        "company": "Acme Srl",
        "contact_name": "Mario Rossi",
        "address": "Via Roma 1",
        "zip_code": "20121",
        "city": "Milano",
        "province": "MI",
        "phone": "0212345678",
        "reference": "ORD-001",
        "num_packages": 3,
        "weight_per_package": 5.0,
        "length": 30.0,
        "width": 20.0,
        "height": 10.0,
        "use_pallet": False,
        "num_pallets": 0,
        "pallet_length": 0.0,
        "pallet_width": 0.0,
        "pallet_height": 0.0,
        "notes": "",
        "pickup_status": "booked",
        "cancelled_at": None,
        "cancellation_reason": None,
        "created_at": "2026-04-08T10:00:00Z",
    }

    @patch("app.core.pickup.update_zapier_status")
    @patch("app.core.pickup.requests.post")
    @patch("app.core.pickup.cancel_pickup")
    @patch("app.core.pickup.get_pickup")
    @patch("app.core.pickup.get_secret", return_value="https://hooks.zapier.com/test")
    def test_successful_cancellation(self, mock_secret, mock_get, mock_cancel, mock_post, mock_zapier_status):
        mock_get.return_value = self.UPCOMING_RECORD
        cancelled = {**self.UPCOMING_RECORD, "pickup_status": "cancelled", "cancelled_at": "2026-04-08T14:30:00Z"}
        mock_cancel.return_value = cancelled
        mock_post.return_value = MagicMock(status_code=200)
        result = cancel_pickup_flow("abc-123", "cambio data")
        assert result["ok"] is True
        assert result["zapier_notified"] is True
        mock_zapier_status.assert_called_once_with("abc-123", True)

    @patch("app.core.pickup.get_pickup")
    def test_not_found_raises_404(self, mock_get):
        mock_get.return_value = None
        result = cancel_pickup_flow("nonexistent", None)
        assert result["ok"] is False
        assert result["status_code"] == 404

    @patch("app.core.pickup.get_pickup")
    def test_already_cancelled_raises_409(self, mock_get):
        record = {**self.UPCOMING_RECORD, "pickup_status": "cancelled"}
        mock_get.return_value = record
        result = cancel_pickup_flow("abc-123", None)
        assert result["ok"] is False
        assert result["status_code"] == 409

    @patch("app.core.pickup.get_pickup")
    def test_past_pickup_raises_422(self, mock_get):
        record = {**self.UPCOMING_RECORD, "pickup_date": "2020-01-01"}
        mock_get.return_value = record
        result = cancel_pickup_flow("abc-123", None)
        assert result["ok"] is False
        assert result["status_code"] == 422

    @patch("app.core.pickup.get_pickup")
    def test_failed_status_can_be_cancelled(self, mock_get):
        record = {**self.UPCOMING_RECORD, "pickup_status": "failed"}
        mock_get.return_value = record
        with patch("app.core.pickup.cancel_pickup") as mock_cancel, \
             patch("app.core.pickup.requests.post") as mock_post, \
             patch("app.core.pickup.update_zapier_status"), \
             patch("app.core.pickup.get_secret", return_value="https://hooks.zapier.com/test"):
            mock_cancel.return_value = {**record, "pickup_status": "cancelled"}
            mock_post.return_value = MagicMock(status_code=200)
            result = cancel_pickup_flow("abc-123", None)
            assert result["ok"] is True

    @patch("app.core.pickup.update_zapier_status")
    @patch("app.core.pickup.requests.post", side_effect=Exception("connection error"))
    @patch("app.core.pickup.cancel_pickup")
    @patch("app.core.pickup.get_pickup")
    @patch("app.core.pickup.get_secret", return_value="https://hooks.zapier.com/test")
    def test_zapier_failure_still_succeeds(self, mock_secret, mock_get, mock_cancel, mock_post, mock_zapier_status):
        mock_get.return_value = self.UPCOMING_RECORD
        mock_cancel.return_value = {**self.UPCOMING_RECORD, "pickup_status": "cancelled"}
        result = cancel_pickup_flow("abc-123", None)
        assert result["ok"] is True
        assert result["zapier_notified"] is False
        mock_zapier_status.assert_called_once_with("abc-123", False)
