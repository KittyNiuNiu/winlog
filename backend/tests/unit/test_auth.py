"""Login, logout and authentication checks that need no database (FR-A2, FR-A3)."""

import base64
import hashlib
import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.dependencies.models import Dependant
from fastapi.testclient import TestClient

from app import accounts, entries, health, suggestions, tags
from app.auth import AuthenticateFirstRoute, get_current_user, hash_token, new_token
from app.main import create_app
from app.models import User
from app.settings import SettingsError, load_settings

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


# --- The token is checked before a body that is not valid JSON ------------------------------
# FastAPI reads a JSON body before it runs the dependencies. Without AuthenticateFirstRoute, a
# body it cannot read got 422 (or 400) even without a valid token.

NOT_JSON = [b"junk", b'{"text":', b"\xff\xfe", b"\x80"]
"""Bodies FastAPI cannot read: not JSON, cut off, a UTF-16 mark only, and not UTF-8."""
NOT_JSON_WITH_VALID_UTF8 = NOT_JSON[:3]


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


@pytest.mark.parametrize("body", NOT_JSON)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic x"}])
def test_fr_a3_body_that_is_not_json_without_token_is_not_authenticated(
    client: TestClient, contract, body: bytes, headers: dict
):
    operations = _operations_with_a_body(client.app.openapi(), needs_auth=True)
    assert ("post", "/entries") in operations
    assert ("put", "/entries/{entryId}") in operations

    for method, path in operations:
        response = _send_raw(client, method, path, body, headers)

        assert response.status_code == 401, f"{method} {path}"
        contract("Error").validate(response.json())
        assert response.json()["code"] == "not_authenticated"
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("body", NOT_JSON_WITH_VALID_UTF8)
def test_fr_a3_logged_in_body_that_is_not_json_is_still_a_validation_error(
    settings, contract, body: bytes
):
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="a@b.c")
    client = TestClient(app)

    for method, path in [("post", "/entries"), ("put", "/entries/{entryId}")]:
        response = _send_raw(client, method, path, body, {"Authorization": "Bearer stand-in"})

        assert response.status_code == 422, f"{method} {path}"
        contract("Error").validate(response.json())
        assert response.json()["code"] == "validation_failed"


@pytest.mark.parametrize("body", NOT_JSON_WITH_VALID_UTF8)
def test_fr_a3_public_operations_keep_the_validation_error_for_a_body_that_is_not_json(
    client: TestClient, contract, body: bytes
):
    operations = _operations_with_a_body(client.app.openapi(), needs_auth=False)
    assert ("post", "/auth/register") in operations
    assert ("post", "/auth/login") in operations

    for method, path in operations:
        response = _send_raw(client, method, path, body, {})

        assert response.status_code == 422, f"{method} {path}"
        contract("Error").validate(response.json())
        assert response.json()["code"] == "validation_failed"


def test_fr_a3_every_route_checks_the_token_before_the_body(settings):
    routers = [accounts.router, entries.router, health.router, suggestions.router, tags.router]
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
