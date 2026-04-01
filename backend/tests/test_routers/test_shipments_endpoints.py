"""Shipments router endpoint tests — POD, POD batch, POD from Excel, Ship."""
import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.job_store import job_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def _cleanup():
    """Reset rate limiter and job store before and after each test."""
    from app.limiter import limiter
    limiter.reset()
    yield
    job_store.cleanup_all()
    limiter.reset()


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/pod
# ---------------------------------------------------------------------------

class TestPodEndpoint:
    """Single POD lookup."""

    def test_valid_identifier_returns_200(self):
        mock_result = {"status": "found", "pdf_base64": "AAAA", "filename": "pod.pdf"}
        with patch("app.routers.shipments.fetch_single_pod", return_value=mock_result):
            resp = client.post("/api/v1/jobs/pod", json={"identifier": "TRACK123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["status"] == "found"

    def test_empty_identifier_returns_422(self):
        resp = client.post("/api/v1/jobs/pod", json={"identifier": ""})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/pod-batch
# ---------------------------------------------------------------------------

class TestPodBatchEndpoint:
    """Bulk POD lookup."""

    def test_valid_identifiers_returns_job_id(self):
        with patch("app.routers.shipments.send_batch_pod_request"):
            resp = client.post("/api/v1/jobs/pod-batch", json={
                "identifiers": ["TRACK1", "TRACK2"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "job_id" in data["data"]

    def test_empty_list_returns_422(self):
        resp = client.post("/api/v1/jobs/pod-batch", json={"identifiers": []})
        assert resp.status_code == 422

    def test_over_500_items_returns_422(self):
        resp = client.post("/api/v1/jobs/pod-batch", json={
            "identifiers": [f"T{i}" for i in range(501)],
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/pod-from-excel
# ---------------------------------------------------------------------------

class TestPodFromExcelEndpoint:
    """POD extraction from an Excel file."""

    def test_valid_excel_returns_200(self):
        identifiers = ["TRACK1", "TRACK2"]
        metadata = {"column": "Tracking", "total": 2}
        with patch(
            "app.routers.shipments.extract_identifiers_from_excel",
            return_value=(identifiers, metadata),
        ), patch("app.routers.shipments.send_batch_pod_request"):
            fake_excel = io.BytesIO(b"\x00" * 64)
            resp = client.post(
                "/api/v1/jobs/pod-from-excel",
                files={"file": ("pods.xlsx", fake_excel, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["mode"] == "batch"
        assert "job_id" in data["data"]


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/ship
# ---------------------------------------------------------------------------

_VALID_SHIP_BODY = {
    "carrier_name": "MyDHL",
    "carrier_id": 9536,
    "carrier_service": "EXPRESS WORLDWIDE",
    "from_address": {
        "name": "Mario Rossi",
        "street1": "Via Roma 10",
        "city": "Milano",
        "zip": "20121",
        "country": "IT",
        "phone": "+39021234567",
    },
    "to_address": {
        "name": "Hans Mueller",
        "street1": "Hauptstrasse 1",
        "city": "Berlin",
        "zip": "10115",
        "country": "DE",
    },
    "parcels": [{"length": 30, "width": 20, "height": 15, "weight": 5.0}],
}


class TestShipEndpoint:
    """Shipment creation."""

    def test_valid_ship_request_returns_job_id(self):
        with patch("app.routers.shipments.send_ship_request"):
            resp = client.post("/api/v1/jobs/ship", json=_VALID_SHIP_BODY)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "job_id" in data["data"]

    def test_mismatched_carrier_id_returns_422(self):
        body = {**_VALID_SHIP_BODY, "carrier_id": 9999}
        resp = client.post("/api/v1/jobs/ship", json=body)
        assert resp.status_code == 422
