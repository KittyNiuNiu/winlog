from fastapi.testclient import TestClient

from tests.unit.conftest import ALLOWED_ORIGIN

OTHER_ORIGIN = "https://not-allowed.example"


def test_allowed_origin_gets_cors_headers(client: TestClient):
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()


def test_preflight_from_allowed_origin_allows_authorization_header(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_other_origin_gets_no_cors_headers(client: TestClient):
    response = client.get("/health", headers={"Origin": OTHER_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_other_origin_gets_no_cors_headers(client: TestClient):
    response = client.options(
        "/health",
        headers={
            "Origin": OTHER_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert "access-control-allow-origin" not in response.headers
