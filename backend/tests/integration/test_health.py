from fastapi.testclient import TestClient


def test_health_returns_200_against_the_real_test_database(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
