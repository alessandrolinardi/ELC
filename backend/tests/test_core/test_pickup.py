"""Tests for app.core.pickup — CARRIER_MAP, _generate_order_id, _split_time_window."""
from datetime import date, time

from app.core.pickup import CARRIER_MAP, _generate_order_id, _split_time_window


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
