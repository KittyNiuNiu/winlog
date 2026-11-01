from fastapi import Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import create_app


class _Payload(BaseModel):
    text: str
    count: int


def _client_with_test_routes(settings) -> TestClient:
    """An app with routes that exist only in these tests."""
    app = create_app(settings)

    @app.post("/test-only/validation")
    def validation_route(payload: _Payload, limit: int = Query()) -> dict:
        return {"ok": True}

    @app.get("/test-only/crash")
    def crash_route() -> dict:
        raise RuntimeError("boom")

    return TestClient(app, raise_server_exceptions=False)


def test_unknown_path_returns_404_in_shared_format(client: TestClient, contract):
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    contract("Error").validate(response.json())


def test_unsupported_method_returns_405_in_shared_format(client: TestClient, contract):
    response = client.post("/health")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]
    contract("Error").validate(response.json())


def test_validation_error_lists_each_failing_field(settings, contract):
    client = _client_with_test_routes(settings)

    response = client.post("/test-only/validation", json={"count": "not-a-number"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    contract("Error").validate(body)
    failing = {item["field"] for item in body["fields"]}
    assert failing == {"text", "count", "limit"}
    assert all(item["reason"] for item in body["fields"])


def test_malformed_json_is_a_validation_error(settings, contract):
    client = _client_with_test_routes(settings)

    response = client.post(
        "/test-only/validation?limit=1",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    contract("Error").validate(response.json())


def test_validation_error_never_echoes_submitted_values(settings):
    client = _client_with_test_routes(settings)

    response = client.post(
        "/test-only/validation?limit=1", json={"text": "x", "count": "private-value-123"}
    )

    assert response.status_code == 422
    assert "private-value-123" not in response.text


def test_unexpected_error_returns_500_in_shared_format(settings, contract):
    client = _client_with_test_routes(settings)

    response = client.get("/test-only/crash")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "boom" not in response.text
    contract("Error").validate(response.json())
