import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestBrandsAPI:
    def test_get_brands_returns_list(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
            {"name": "DOUGLAS", "created_at": "2026-01-01"},
            {"name": "SBX", "created_at": "2026-01-01"},
        ]
        with patch("app.routers.brands._get_supabase", return_value=mock_client):
            resp = client.get("/api/v1/brands")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    def test_get_brands_no_supabase(self):
        with patch("app.routers.brands._get_supabase", return_value=None):
            resp = client.get("/api/v1/brands")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_create_brand(self):
        mock_client = MagicMock()
        mock_client.table.return_value.upsert.return_value.execute.return_value.data = [{"name": "NEWBRAND"}]
        with patch("app.routers.brands._get_supabase", return_value=mock_client):
            resp = client.post("/api/v1/brands", json={"name": "newbrand"})
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "NEWBRAND"

    def test_create_brand_empty_name(self):
        resp = client.post("/api/v1/brands", json={"name": ""})
        assert resp.status_code == 400

    def test_create_brand_whitespace_only(self):
        resp = client.post("/api/v1/brands", json={"name": "   "})
        assert resp.status_code == 400

    def test_create_brand_no_supabase(self):
        with patch("app.routers.brands._get_supabase", return_value=None):
            resp = client.post("/api/v1/brands", json={"name": "TEST"})
        assert resp.status_code == 503
