"""Login, logout and authentication checks that need no database (FR-A2, FR-A3)."""

import base64
import hashlib
import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.dependencies.models import Dependant
from fastapi.testclient import TestClient

from app import accounts, demo, entries, export, health, suggestions, summaries, tags
from app.auth import AuthenticateFirstRoute, get_current_user, hash_token, new_token
from app.main import create_app
from app.models import User
from app.settings import SettingsError, load_settings
from tests.whole_number_settings import (
    accepted_values,
    assert_range_applies_in_code,
    assert_stops_at_startup,
    refused_values,
    value_id,
)

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "openapi.yaml"
DATABASE_URL = "postgresql://winlog:unit-test-secret@localhost:5432/winlog"
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


# --- Tokens --------------------------------------------------------------------------------


def test_fr_a2_token_has_at_least_32_random_bytes():
    token = new_token()

    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert len(raw) >= 32


def test_fr_a2_each_token_is_new():
    assert len({new_token() for _ in range(100)}) == 100


def test_fr_a2_token_hash_is_sha256():
    token = new_token()

    assert hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert token not in hash_token(token)


def test_fr_a2_token_lifetime_defaults_to_seven_days(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    assert load_settings().token_lifetime_days == 7


def test_fr_a2_token_lifetime_comes_from_the_environment(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("TOKEN_LIFETIME_DAYS", "30")

    assert load_settings().token_lifetime_days == 30


@pytest.mark.parametrize("value", ["0", "-1", "366", "a week"])
def test_fr_a2_invalid_token_lifetime_is_rejected(no_env_file, monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("TOKEN_LIFETIME_DAYS", value)

    with pytest.raises(SettingsError, match="TOKEN_LIFETIME_DAYS is invalid"):
        load_settings()


@pytest.mark.parametrize(("value", "expected"), accepted_values(1, 365))
def test_fr_a2_token_lifetime_takes_a_whole_number_from_1_to_365(
    no_env_file, monkeypatch, value, expected
):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("TOKEN_LIFETIME_DAYS", value)

    assert load_settings().token_lifetime_days == expected


@pytest.mark.parametrize("value", refused_values(1, 365), ids=value_id)
def test_fr_a2_token_lifetime_refuses_lax_spellings(no_env_file, monkeypatch, value):
    # Also every other value outside 1 to 365 or not a whole number (issue #108).
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    assert_stops_at_startup(monkeypatch, "TOKEN_LIFETIME_DAYS", value, 1, 365)


def test_fr_a2_token_lifetime_range_applies_in_code(no_env_file):
    assert_range_applies_in_code(
        "token_lifetime_days",
        1,
        365,
        database_url=DATABASE_URL,
        cors_allowed_origins=["http://localhost:5173"],
        ai_provider="mock",
    )


def test_fr_a2_token_lifetime_is_documented_in_env_example():
    env_example = (Path(__file__).resolve().parents[3] / ".env.example").read_text()

    assert "\nTOKEN_LIFETIME_DAYS=7\n" in env_example


# --- Login validation ----------------------------------------------------------------------


def _fields(response) -> list[str]:
    return [item["field"] for item in response.json()["fields"]]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"password": "Correct-Horse-7"}, "email"),
        ({"email": "alice@example.com"}, "password"),
        ({"email": "alice@example.com", "password": ""}, "password"),
        ({"email": "alice@example.com", "password": "A1!" + "a" * 126}, "password"),  # 129
        ({"email": "not-an-email", "password": "Correct-Horse-7"}, "email"),
    ],
)
def test_fr_a2_login_with_missing_or_invalid_field_returns_the_validation_error(
    client: TestClient, contract, body: dict, field: str
):
    response = client.post("/auth/login", json=body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert _fields(response) == [field]


def test_fr_a2_login_with_unpaired_surrogate_returns_the_validation_error(
    client: TestClient, contract
):
    # httpx cannot encode a lone surrogate, so the JSON escape is sent exactly as written.
    raw = '{"email": "alice@example.com", "password": "Surrogate-Secret-7\\ud800"}'
    response = client.post(
        "/auth/login", content=raw.encode("ascii"), headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert _fields(response) == ["password"]
    assert "Surrogate-Secret-7" not in response.text


def test_fr_a2_rejected_login_password_is_never_echoed(client: TestClient):
    response = client.post("/auth/login", json={"email": "x", "password": "Secret-" + "x" * 130})

    assert "Secret-" not in response.text


# --- Missing and malformed tokens ----------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic YWxpY2U6c2VjcmV0"},
        {"Authorization": "Token abc"},
        {"Authorization": "abc"},
    ],
)
def test_fr_a3_missing_or_malformed_token_is_not_authenticated(
    client: TestClient, contract, headers: dict
):
    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


# --- Every protected operation uses the dependency -----------------------------------------
# The bearer scheme is read only inside get_current_user's dependency chain, so FastAPI lists
# `bearerAuth` on exactly the operations that use get_current_user.


def _calls(dependant: Dependant) -> set:
    found = {dependant.call}
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


def _operations(spec: dict) -> dict[str, tuple[str, str, bool]]:
    """operationId -> (method, path, whether it needs authentication)."""
    default_security = spec.get("security", [])
    operations = {}
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue  # for example path-level parameters
            needs_auth = bool(operation.get("security", default_security))
            operations[operation["operationId"]] = (method, path, needs_auth)
    return operations


def _contract() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def test_fr_a3_every_operation_that_needs_authentication_uses_the_dependency(settings):
    contract_operations = _operations(_contract())
    app_operations = _operations(create_app(settings).openapi())

    assert "logout" in app_operations
    for operation_id, (method, path, needs_auth) in app_operations.items():
        assert operation_id in contract_operations, f"{method} {path}"
        assert needs_auth == contract_operations[operation_id][2], operation_id


def test_fr_a3_every_operation_that_needs_authentication_rejects_a_request_without_token(
    client: TestClient,
):
    for method, path, needs_auth in _operations(client.app.openapi()).values():
        if not needs_auth:
            continue
        url = path.replace("{entryId}", str(uuid.uuid4())).replace("{summaryId}", str(uuid.uuid4()))
        response = client.request(method, url)
        assert response.status_code == 401, f"{method} {path}"
        assert response.json()["code"] == "not_authenticated"


# --- The token is checked before a body that cannot be read as JSON -------------------------
# FastAPI reads a JSON body before it runs the dependencies. AuthenticateFirstRoute checks the
# token first, and then answers such a body with the body error (issue #58). These tests fail
# if a FastAPI upgrade changes how it reports a body it cannot read.

UNREADABLE_BODIES = {
    "byte-80": b"\x80",
    "latin-1-text": b'{"text": "caf\xe9"}',
    "overlong-encoding": b"\xc0\x80",
    "stray-byte-after-json": b'{"text": "a"}\x80',
    "utf-16-mark-and-odd-length": b"\xff\xfe{",
    "nested-too-deeply": b"[" * 100_000,
    "junk": b"junk",
    "cut-off": b'{"text":',
    "utf-16-mark-only": b"\xff\xfe",
    "three-spaces": b"   ",
}
"""Bodies that cannot be read as JSON (issue #58): not valid UTF-8, nested too deeply to
parse, and not JSON. Each is far below `REQUEST_BODY_MAX_BYTES`."""
BODY_ERROR = {
    "code": "validation_failed",
    "message": "The request has invalid fields.",
    "fields": [{"field": "body", "reason": "Body must be valid JSON in UTF-8."}],
}
"""The body error (issue #58), the only answer to such a body after the token check."""


def unreadable_bodies(name: str = "body"):
    """Parametrize a test with every unreadable body, named so the test ids stay short."""
    return pytest.mark.parametrize(
        name, list(UNREADABLE_BODIES.values()), ids=list(UNREADABLE_BODIES)
    )


def _url(path: str) -> str:
    return path.replace("{entryId}", str(uuid.uuid4())).replace("{summaryId}", str(uuid.uuid4()))


def _operations_with_a_body(schema: dict, *, needs_auth: bool) -> list[tuple[str, str]]:
    """(method, path) of each operation that takes a request body."""
    found = []
    for method, path, auth in _operations(schema).values():
        if auth == needs_auth and "requestBody" in schema["paths"][path][method]:
            found.append((method, path))
    return found


def _send_raw(client: TestClient, method: str, path: str, body: bytes, headers: dict):
    return client.request(
        method, _url(path), content=body, headers={**headers, "Content-Type": "application/json"}
    )


@unreadable_bodies()
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic x"}])
def test_fr_a3_body_that_is_not_json_without_token_is_not_authenticated(
    client: TestClient, contract, body: bytes, headers: dict
):
    operations = _operations_with_a_body(client.app.openapi(), needs_auth=True)
    assert len(operations) == 6
    assert ("post", "/entries") in operations
    assert ("put", "/entries/{entryId}") in operations

    for method, path in operations:
        response = _send_raw(client, method, path, body, headers)

        assert response.status_code == 401, f"{method} {path}"
        contract("Error").validate(response.json())
        assert response.json()["code"] == "not_authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"


@unreadable_bodies()
def test_fr_a3_logged_in_body_that_is_not_json_is_still_a_validation_error(
    settings, contract, body: bytes
):
    """With a valid token (an ordinary user, not the demo account), the body error."""
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="a@b.c")
    client = TestClient(app)
    operations = _operations_with_a_body(client.app.openapi(), needs_auth=True)
    assert len(operations) == 6

    for method, path in operations:
        response = _send_raw(client, method, path, body, {"Authorization": "Bearer stand-in"})

        assert response.status_code == 422, f"{method} {path}"
        contract("Error").validate(response.json())
        assert response.json() == BODY_ERROR, f"{method} {path}"


@unreadable_bodies()
def test_fr_a3_public_operations_keep_the_validation_error_for_a_body_that_is_not_json(
    client: TestClient, contract, body: bytes
):
    operations = _operations_with_a_body(client.app.openapi(), needs_auth=False)
    assert sorted(operations) == [("post", "/auth/login"), ("post", "/auth/register")]

    for method, path in operations:
        response = _send_raw(client, method, path, body, {})

        assert response.status_code == 422, f"{method} {path}"
        contract("Error").validate(response.json())
        assert response.json() == BODY_ERROR, f"{method} {path}"


def test_fr_a3_every_route_checks_the_token_before_the_body(settings):
    routers = [
        accounts.router,
        demo.router,
        entries.router,
        export.router,
        health.router,
        suggestions.router,
        summaries.router,
        tags.router,
    ]
    routes = [route for router in routers for route in router.routes]

    for route in routes:
        assert isinstance(route, AuthenticateFirstRoute), route.path
    # These routers hold every operation of the app.
    app_operations = set(_operations(create_app(settings).openapi()))
    assert app_operations == {route.operation_id for route in routes}


def test_fr_a3_logout_uses_the_current_user_dependency():
    [route] = [r for r in accounts.router.routes if r.name == "logout"]

    assert get_current_user in _calls(route.dependant)


def test_fr_a3_generated_schema_uses_the_bearer_scheme_from_the_contract(settings):
    schema = create_app(settings).openapi()

    assert schema["paths"]["/auth/logout"]["post"]["security"] == [{"bearerAuth": []}]
    assert "security" not in schema["paths"]["/auth/login"]["post"]
    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
    }
