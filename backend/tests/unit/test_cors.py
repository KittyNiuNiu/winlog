import pytest
from fastapi.testclient import TestClient

from tests.unit.conftest import ALLOWED_ORIGIN

OTHER_ORIGIN = "https://not-allowed.example"

# Origins that are not in the list: an unrelated one, and near misses of ALLOWED_ORIGIN
# (http://localhost:5173), which must not match it.
NOT_ALLOWED_ORIGINS = [
    OTHER_ORIGIN,
    "http://localhost:5174",  # different port
    "https://localhost:5173",  # different scheme
    "http://localhost:5173/",  # trailing slash
    "http://app.localhost:5173",  # subdomain
    "http://127.0.0.1:5173",  # same machine, different host name
    "null",  # opaque origin, for example a sandboxed iframe or a file:// page
]


def cors_headers(response) -> list[str]:
    """The names of all CORS response headers (Access-Control-*) in the response."""
    return sorted(name for name in response.headers if name.lower().startswith("access-control-"))


def preflight(client: TestClient, path: str, origin: str):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )


@pytest.mark.parametrize(("path", "status"), [("/health", 200), ("/nope", 404)])
def test_allowed_origin_gets_cors_headers(client: TestClient, path: str, status: int):
    response = client.get(path, headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == status
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()


def test_preflight_from_allowed_origin_allows_authorization_header(client: TestClient):
    response = preflight(client, "/health", ALLOWED_ORIGIN)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("origin", NOT_ALLOWED_ORIGINS)
@pytest.mark.parametrize(("path", "status"), [("/health", 200), ("/nope", 404)])
def test_other_origin_gets_no_cors_headers(client: TestClient, origin: str, path: str, status: int):
    response = client.get(path, headers={"Origin": origin})

    assert response.status_code == status
    assert cors_headers(response) == []


@pytest.mark.parametrize("origin", NOT_ALLOWED_ORIGINS)
@pytest.mark.parametrize("path", ["/health", "/nope"])
def test_preflight_from_other_origin_gets_no_cors_headers(
    client: TestClient, origin: str, path: str
):
    response = preflight(client, path, origin)

    assert response.status_code == 400
    assert cors_headers(response) == []
