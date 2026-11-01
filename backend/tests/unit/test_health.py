from fastapi.testclient import TestClient


def test_health_returns_documented_body_without_authentication(client: TestClient, contract):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    contract("Health").validate(response.json())


def test_module_level_app_serves_health():
    """`uvicorn app.main:app` uses this object."""
    from app.main import app

    assert TestClient(app).get("/health").status_code == 200
