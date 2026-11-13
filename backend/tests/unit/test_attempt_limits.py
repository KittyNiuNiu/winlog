"""Login and demo-login attempt limits without a database (FR-A4, issue #46).

The settings, the visitor IP, the error, the contract and the order of the checks. The
limiter itself is replaced by the `attempts` fake from conftest.py. The counting against
PostgreSQL, including parallel attempts, is tested in tests/integration/test_attempt_limits.py.
"""

import hashlib
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.accounts
from app.attempt_limits import TooManyAttemptsError, hash_key, visitor_ip
from app.auth import CurrentLogin, get_current_login
from app.db import get_session
from app.main import create_app
from app.models import User
from app.passwords import hash_password
from app.settings import MAX_ATTEMPT_WINDOW_MINUTES, Settings, SettingsError, load_settings
from tests.unit.conftest import ALLOWED_ORIGIN, FakeAttempts

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
PASSWORD = "Correct-Horse-7"
PASSWORD_HASH = hash_password(PASSWORD)
DEMO = "demo@example.com"

VARIABLES = {
    "LOGIN_MAX_FAILED_ATTEMPTS": ("login_max_failed_attempts", 10),
    "LOGIN_ATTEMPT_WINDOW_MINUTES": ("login_attempt_window_minutes", 15),
    "DEMO_LOGIN_MAX_ATTEMPTS": ("demo_login_max_attempts", 20),
    "DEMO_LOGIN_WINDOW_MINUTES": ("demo_login_window_minutes", 60),
}
OPERATIONS = [("/auth/login", "post"), ("/auth/demo", "post"), ("/account", "delete")]


@pytest.fixture
def required_env(no_env_file, monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    return monkeypatch


def _request(headers: list[tuple[str, str]], client: tuple[str, int] | None = ("10.1.2.3", 5000)):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/demo",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
        "client": client,
    }
    return Request(scope)


# --- Settings -----------------------------------------------------------------------------


def test_fr_a4_limits_have_the_agreed_defaults(required_env):
    settings = load_settings()

    for name, default in VARIABLES.values():
        assert getattr(settings, name) == default


@pytest.mark.parametrize("variable", VARIABLES)
def test_fr_a4_limits_come_from_environment_variables(required_env, variable: str):
    required_env.setenv(variable, " 7 ")

    assert getattr(load_settings(), VARIABLES[variable][0]) == 7


@pytest.mark.parametrize("variable", VARIABLES)
@pytest.mark.parametrize("value", ["0", "-1", "1.0", "+5", "1_000", "1e3", "ten", "", " ", "٣"])
def test_fr_a4_invalid_limit_stops_the_app_naming_the_variable(
    required_env, variable: str, value: str
):
    required_env.setenv(variable, value)

    with pytest.raises(SettingsError, match=f"{variable} is invalid") as error:
        load_settings()
    assert "whole number" in str(error.value)


@pytest.mark.parametrize("variable", ["LOGIN_ATTEMPT_WINDOW_MINUTES", "DEMO_LOGIN_WINDOW_MINUTES"])
def test_fr_a4_window_longer_than_a_year_stops_the_app(required_env, variable: str):
    required_env.setenv(variable, str(MAX_ATTEMPT_WINDOW_MINUTES))
    assert getattr(load_settings(), VARIABLES[variable][0]) == MAX_ATTEMPT_WINDOW_MINUTES

    required_env.setenv(variable, str(MAX_ATTEMPT_WINDOW_MINUTES + 1))
    with pytest.raises(SettingsError, match=f"{variable} is invalid"):
        load_settings()


@pytest.mark.parametrize("variable", ["LOGIN_MAX_FAILED_ATTEMPTS", "DEMO_LOGIN_MAX_ATTEMPTS"])
def test_fr_a4_attempt_counts_have_no_upper_bound(required_env, variable: str):
    required_env.setenv(variable, "1000000")

    assert getattr(load_settings(), VARIABLES[variable][0]) == 1_000_000


def test_fr_a4_invalid_limit_stops_the_app_at_startup(required_env):
    required_env.setenv("DEMO_LOGIN_MAX_ATTEMPTS", "0")

    with pytest.raises(SettingsError, match="DEMO_LOGIN_MAX_ATTEMPTS"):
        create_app()


@pytest.mark.parametrize("variable", VARIABLES)
def test_fr_a4_limits_are_documented_in_env_example(variable: str):
    default = VARIABLES[variable][1]

    assert re.search(rf"^{variable}={default}$", ENV_EXAMPLE, re.MULTILINE)
    assert re.search(rf"^# Optional, default {default}\.", ENV_EXAMPLE, re.MULTILINE)


# --- Visitor IP and hashes ----------------------------------------------------------------


def test_fr_a4_visitor_ip_is_the_proxys_x_forwarded_for_entry():
    request = _request([("X-Forwarded-For", "203.0.113.7")])

    assert visitor_ip(request) == "203.0.113.7"


@pytest.mark.parametrize(
    "headers",
    [
        [("X-Forwarded-For", "1.1.1.1, 203.0.113.7")],
        [("X-Forwarded-For", "evil, 10.0.0.1,203.0.113.7")],
        [("X-Forwarded-For", " 1.1.1.1 ,  203.0.113.7 ")],
        [("X-Forwarded-For", "1.1.1.1, 203.0.113.7, ")],
        # A client's own header line first, the proxy's appended last.
        [("X-Forwarded-For", "1.1.1.1"), ("X-Forwarded-For", "203.0.113.7")],
    ],
)
def test_fr_a4_values_a_client_added_to_x_forwarded_for_are_ignored(headers):
    assert visitor_ip(_request(headers)) == "203.0.113.7"


def test_fr_a4_visitor_ip_without_x_forwarded_for_is_the_connection_address():
    assert visitor_ip(_request([])) == "10.1.2.3"
    assert visitor_ip(_request([("X-Forwarded-For", " , ")])) == "10.1.2.3"


def test_fr_a4_visitor_ip_without_any_address_is_still_counted():
    assert visitor_ip(_request([], client=None)) == "unknown"


def test_fr_a4_ipv6_addresses_have_one_spelling():
    long = _request([("X-Forwarded-For", "2001:DB8:0:0:0:0:0:1")])
    short = _request([("X-Forwarded-For", "2001:db8::1")])

    assert visitor_ip(long) == visitor_ip(short) == "2001:db8::1"


def test_fr_a4_keys_are_stored_as_sha256_hashes():
    assert hash_key("alice@example.com") == hashlib.sha256(b"alice@example.com").hexdigest()
    assert "alice" not in hash_key("alice@example.com")


def test_fr_a4_too_many_attempts_error_has_its_status_code_and_retry_after():
    error = TooManyAttemptsError(61)

    assert error.status_code == 429
    assert error.code == "too_many_attempts"
    assert error.headers == {"Retry-After": "61"}


# --- Contract -----------------------------------------------------------------------------


@pytest.mark.parametrize(("path", "method"), OPERATIONS)
def test_fr_a4_contract_documents_the_error_and_retry_after(path: str, method: str):
    responses = OPENAPI["paths"][path][method]["responses"]

    assert responses["429"] == {"$ref": "#/components/responses/TooManyAttempts"}


def test_fr_a4_too_many_attempts_response_matches_the_contract(contract):
    response = OPENAPI["components"]["responses"]["TooManyAttempts"]
    header = OPENAPI["components"]["headers"]["RetryAfter"]

    assert response["headers"]["Retry-After"] == {"$ref": "#/components/headers/RetryAfter"}
    assert header["schema"] == {"type": "integer", "minimum": 1}
    example = response["content"]["application/json"]["example"]
    contract("Error").validate(example)
    assert example["code"] == "too_many_attempts"
    codes = OPENAPI["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
    assert codes.count("too_many_attempts") == 1


def test_fr_a4_429_is_its_own_status_on_these_operations():
    for path, method in OPERATIONS:
        responses = OPENAPI["paths"][path][method]["responses"]
        others = {status for status in responses if status != "429"}
        assert all("TooManyAttempts" not in str(responses[status]) for status in others), (
            f"{method} {path}"
        )


@pytest.mark.parametrize(("path", "method"), OPERATIONS)
def test_fr_a4_generated_schema_lists_the_429(settings: Settings, path: str, method: str):
    generated = create_app(settings).openapi()["paths"][path][method]["responses"]

    assert "429" in generated


def test_fr_a4_cors_exposes_retry_after(client: TestClient):
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

    exposed = response.headers["access-control-expose-headers"].lower()
    assert {name.strip() for name in exposed.split(",")} >= {"content-disposition", "retry-after"}


# --- Order of the checks ------------------------------------------------------------------


def _app(settings: Settings, session: MagicMock, user: User | None = None):
    application = create_app(settings)
    application.dependency_overrides[get_session] = lambda: session
    if user is not None:
        application.dependency_overrides[get_current_login] = lambda: CurrentLogin(
            token_id=uuid.uuid4(), user=user
        )
    return application


@pytest.fixture
def password_checks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    checks: list[str] = []
    monkeypatch.setattr(
        app.accounts, "verify_password", lambda *_args: checks.append("verify") or False
    )
    monkeypatch.setattr(
        app.accounts, "verify_against_dummy_hash", lambda *_args: checks.append("dummy")
    )
    return checks


def test_fr_a4_blocked_login_checks_no_password_and_creates_no_token(
    settings: Settings, attempts: FakeAttempts, password_checks, contract
):
    attempts.retry_after = 61
    session = MagicMock()

    response = TestClient(_app(settings, session)).post(
        "/auth/login", json={"email": " Alice@Example.COM ", "password": PASSWORD}
    )

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json()["code"] == "too_many_attempts"
    assert response.headers["Retry-After"] == "61"
    # Counted for the email after trimming and lower-casing (#7).
    assert attempts.calls == [("take_login_attempt", "alice@example.com")]
    assert password_checks == []
    session.add.assert_not_called()
    session.commit.assert_not_called()


def test_fr_a4_login_validation_error_counts_nothing(settings: Settings, attempts: FakeAttempts):
    response = TestClient(_app(settings, MagicMock())).post(
        "/auth/login", json={"email": "alice@example.com", "password": ""}
    )

    assert response.status_code == 422
    assert attempts.calls == []


def test_fr_a4_blocked_demo_login_creates_no_token(
    settings: Settings, attempts: FakeAttempts, contract
):
    attempts.retry_after = 3600
    session = MagicMock()
    demo_settings = settings.model_copy(update={"demo_email": DEMO})

    response = TestClient(_app(demo_settings, session)).post(
        "/auth/demo", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.7"}
    )

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.headers["Retry-After"] == "3600"
    assert attempts.calls == [("take_demo_login", "203.0.113.7")]
    session.execute.assert_not_called()
    session.scalars.assert_not_called()
    session.commit.assert_not_called()


def test_fr_a4_blocked_deletion_checks_no_password_and_deletes_nothing(
    settings: Settings, attempts: FakeAttempts, password_checks, contract
):
    attempts.retry_after = 900
    session = MagicMock()
    user = User(id=uuid.uuid4(), email="alice@example.com", password_hash=PASSWORD_HASH)

    response = TestClient(_app(settings, session, user)).request(
        "DELETE", "/account", json={"current_password": PASSWORD}, headers={"Authorization": "t"}
    )

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.headers["Retry-After"] == "900"
    assert attempts.calls == [("take_login_attempt", "alice@example.com")]
    assert password_checks == []
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_fr_a4_deletion_body_is_validated_before_the_limit(
    settings: Settings, attempts: FakeAttempts
):
    attempts.retry_after = 900
    user = User(id=uuid.uuid4(), email="alice@example.com", password_hash=PASSWORD_HASH)

    response = TestClient(_app(settings, MagicMock(), user)).request(
        "DELETE", "/account", json={}, headers={"Authorization": "t"}
    )

    assert response.status_code == 422
    assert attempts.calls == []


def test_fr_a4_demo_account_deletion_gets_the_demo_error_before_the_limit(
    settings: Settings, attempts: FakeAttempts
):
    attempts.retry_after = 900
    demo_settings = settings.model_copy(update={"demo_email": DEMO})
    user = User(id=uuid.uuid4(), email=DEMO, password_hash=PASSWORD_HASH)

    response = TestClient(_app(demo_settings, MagicMock(), user)).request(
        "DELETE", "/account", json={"current_password": PASSWORD}, headers={"Authorization": "t"}
    )

    assert response.status_code == 409
    assert attempts.calls == []


def test_fr_a4_correct_deletion_password_clears_the_count(
    settings: Settings, attempts: FakeAttempts
):
    user = User(id=uuid.uuid4(), email="alice@example.com", password_hash=PASSWORD_HASH)

    response = TestClient(_app(settings, MagicMock(), user)).request(
        "DELETE", "/account", json={"current_password": PASSWORD}, headers={"Authorization": "t"}
    )

    assert response.status_code == 204
    assert attempts.calls == [
        ("take_login_attempt", "alice@example.com"),
        ("clear_login_attempts", "alice@example.com"),
    ]


def test_fr_a4_wrong_deletion_password_stays_counted(settings: Settings, attempts: FakeAttempts):
    user = User(id=uuid.uuid4(), email="alice@example.com", password_hash=PASSWORD_HASH)

    response = TestClient(_app(settings, MagicMock(), user)).request(
        "DELETE", "/account", json={"current_password": "Wrong-1"}, headers={"Authorization": "t"}
    )

    assert response.status_code == 403
    assert attempts.calls == [("take_login_attempt", "alice@example.com")]
