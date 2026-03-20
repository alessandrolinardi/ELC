from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["version"] == "3.0.0"
