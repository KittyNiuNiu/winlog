"""Request bodies the backend cannot read as JSON, without a database (issue #58).

Every operation with a request body answers such a body with the body error: 422
`validation_failed` with one field error naming `body` (`unreadable_body` in app/errors.py,
raised by `AuthenticateFirstRoute` in app/auth.py). No requirement ID covers the body error, so
these tests start with `test_unreadable_body_`. The token-first tests (FR-A3) are in
tests/unit/test_auth.py. That such a body changes nothing in the database, and the 401 for an
unknown or expired token, are tested against PostgreSQL in
tests/integration/test_unreadable_body.py. A stand-in user takes the place of a valid token.
"""

import codecs
import uuid

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.trace import StatusCode

from app.auth import get_current_user
from app.health import check_database
from app.main import create_app
from app.models import User
from app.settings import Settings
from app.telemetry import ALLOWED_ATTRIBUTE_KEYS, ALLOWED_RESOURCE_KEYS, LOG_LINE_KEYS
from tests.conftest import OPENAPI_PATH
from tests.telemetry_capture import CapturedTelemetry, json_lines
from tests.unit.conftest import ALLOWED_ORIGIN, FakeAttempts
from tests.unit.test_auth import BODY_ERROR, UNREADABLE_BODIES, unreadable_bodies

OPERATIONS_WITH_A_BODY = {
    "register",
    "login",
    "deleteAccount",
    "createEntry",
    "updateEntry",
    "suggestCategoryAndTags",
    "generateSummary",
    "updateSummary",
}
PUBLIC_OPERATIONS = {"register", "login"}
JSON_CONTENT_TYPES = [
    "application/json",
    "application/json; charset=iso-8859-1",
    "application/merge-patch+json",
]
DEMO_EMAIL = "demo@example.com"
DEFAULT_BODY_LIMIT = 262_144
TOO_LARGE = {"code": "request_too_large", "message": "The request body is too large."}
# A marker that must never appear in a response, a log line or telemetry.
SECRET = "unreadable-body-marker-3f9a"
SECRET_BODIES = {
    "latin-1-password": b'{"email": "a@b.c", "password": "' + SECRET.encode() + b'\xe9"}',
    "stray-byte": b'{"text": "' + SECRET.encode() + b'"}\x80',
    "nested-too-deeply": b"[" * 100_000 + b'"' + SECRET.encode() + b'"',
    "not-json": SECRET.encode(),
    "cut-off": b'{"password": "' + SECRET.encode(),
}
"""Unreadable bodies of each kind that carry the marker."""
# Parts of the exception messages of FastAPI, json and the codecs for such bodies.
EXCEPTION_MESSAGES = [
    "There was an error parsing the body",
    "JSON decode error",
    "Expecting",
    "codec can't decode",
    "invalid start byte",
    "recursion",
    "Traceback",
]


def _operations_with_a_body() -> dict[str, tuple[str, str]]:
    """operationId -> (method, path) of every operation with a `requestBody` in openapi.yaml."""
    contract = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    found = {}
    for path, path_item in contract["paths"].items():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and "requestBody" in operation:
                found[operation["operationId"]] = (method.upper(), path)
    return found


OPERATIONS = _operations_with_a_body()


def _url(path: str) -> str:
    return path.replace("{entryId}", str(uuid.uuid4())).replace("{summaryId}", str(uuid.uuid4()))


def _settings(**values) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://winlog:unit-test-secret@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        **values,
    )


def _app(settings: Settings, email: str = "a@b.c", telemetry=None) -> FastAPI:
    """The real app with a stand-in user for a valid token: an ordinary user by default."""
    app = create_app(settings, telemetry=telemetry)
    app.dependency_overrides[check_database] = lambda: True
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email=email)
    return app


def _send(client: TestClient, operation_id: str, body: bytes, content_type: str | None):
    """Send the body to the operation, with the stand-in token if the operation needs one."""
    method, path = OPERATIONS[operation_id]
    headers = {} if operation_id in PUBLIC_OPERATIONS else {"Authorization": "Bearer stand-in"}
    if content_type is not None:
        headers["Content-Type"] = content_type
    return client.request(method, _url(path), content=body, headers=headers)


def _assert_no_ai_call_and_no_login_attempt(app: FastAPI, attempts: FakeAttempts) -> None:
    assert app.state.ai_provider.suggest_calls == []
    assert app.state.ai_provider.summarise_calls == []
    assert attempts.calls == []


@pytest.fixture
def api(settings: Settings) -> TestClient:
    return TestClient(_app(settings))


# --- The body error -----------------------------------------------------------------------


def test_unreadable_body_operations_with_a_body_are_the_eight_of_the_contract():
    assert set(OPERATIONS) == OPERATIONS_WITH_A_BODY


@unreadable_bodies()
@pytest.mark.parametrize("content_type", JSON_CONTENT_TYPES)
def test_unreadable_body_gets_the_body_error_on_every_operation_with_a_body(
    api: TestClient, attempts: FakeAttempts, contract, body: bytes, content_type: str
):
    for operation_id in OPERATIONS:
        response = _send(api, operation_id, body, content_type)

        assert response.status_code == 422, operation_id
        assert response.json() == BODY_ERROR, operation_id
        contract("Error").validate(response.json())
        assert response.headers["content-type"] == "application/json"
        assert body not in response.content
    _assert_no_ai_call_and_no_login_attempt(api.app, attempts)


@pytest.mark.parametrize("body", list(SECRET_BODIES.values()), ids=list(SECRET_BODIES))
def test_unreadable_body_is_never_repeated_in_the_response(
    api: TestClient, attempts: FakeAttempts, body: bytes
):
    for operation_id in OPERATIONS:
        response = _send(api, operation_id, body, "application/json")

        assert response.json() == BODY_ERROR, operation_id
        assert SECRET not in response.text
        for message in EXCEPTION_MESSAGES:
            assert message not in response.text
    _assert_no_ai_call_and_no_login_attempt(api.app, attempts)


# --- The order of the checks --------------------------------------------------------------


@pytest.mark.parametrize("body", [b"\x80", b"[", b"{"], ids=["byte-80", "brackets", "braces"])
@pytest.mark.parametrize("token", [True, False], ids=["token", "no-token"])
def test_unreadable_body_over_the_size_limit_gets_413_first(
    api: TestClient, contract, body: bytes, token: bool
):
    """413 before 401 and before the body error, also for a body that is not UTF-8."""
    too_large = body * (DEFAULT_BODY_LIMIT + 1)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer stand-in"

    for operation_id, (method, path) in OPERATIONS.items():
        response = api.request(method, _url(path), content=too_large, headers=headers)

        assert response.status_code == 413, operation_id
        assert response.json() == TOO_LARGE
        contract("Error").validate(response.json())


@unreadable_bodies()
def test_fr_x1_demo_account_gets_the_demo_error_before_the_body_error(
    attempts: FakeAttempts, contract, body: bytes
):
    """The demo account's 409 on `deleteAccount` comes before the body error, `\\x80` too.
    That it deletes nothing is tested against PostgreSQL in tests/integration/test_demo.py."""
    api = TestClient(_app(_settings(demo_email=DEMO_EMAIL), email=DEMO_EMAIL))

    response = _send(api, "deleteAccount", body, "application/json")

    assert response.status_code == 409
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "demo_account_not_deletable",
        "message": "The demo account cannot be deleted.",
    }
    assert attempts.calls == []


# --- Bodies the backend can read keep their answers ---------------------------------------


def test_unreadable_body_empty_body_still_gets_field_required(api: TestClient, contract):
    for operation_id in OPERATIONS:
        response = _send(api, operation_id, b"", "application/json")

        assert response.status_code == 422, operation_id
        contract("Error").validate(response.json())
        assert response.json()["fields"] == [{"field": "body", "reason": "Field required"}]


@pytest.mark.parametrize("content_type", [None, "text/plain"])
@pytest.mark.parametrize("body", [b'{"text": "Shipped"}', b"\x80"], ids=["json", "byte-80"])
def test_unreadable_body_without_a_json_content_type_still_names_body(
    api: TestClient, contract, content_type: str | None, body: bytes
):
    """Such a body is not parsed as JSON, so it keeps the error naming `body` it got before."""
    for operation_id in OPERATIONS:
        response = _send(api, operation_id, body, content_type)

        assert response.status_code == 422, operation_id
        contract("Error").validate(response.json())
        assert response.json()["fields"] == [
            {
                "field": "body",
                "reason": "Input should be a valid dictionary or object to extract fields from",
            }
        ]


def test_unreadable_body_valid_json_that_fails_validation_still_names_each_field(
    api: TestClient, contract
):
    body = b'{"text": "", "date": "2026-11-15", "category": "Achievement", "tags": ["Go", " "]}'

    response = _send(api, "createEntry", body, "application/json")

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert [field["field"] for field in response.json()["fields"]] == ["text", "tags.1"]


@pytest.mark.parametrize(
    "character",
    [b"\\u0000", b"\\ud800", b"\xed\xa0\x80"],
    ids=["nul-escape", "surrogate-escape", "surrogate-bytes"],
)
@pytest.mark.parametrize("field", ["text", "tags.0"])
def test_unreadable_body_nul_or_unpaired_surrogate_still_names_the_field(
    api: TestClient, contract, character: bytes, field: str
):
    """Written as a JSON escape or as raw bytes: `json.loads` reads both, so the field is named."""
    value = b"Before" + character + b"after"
    text, tag = (value, b"Go") if field == "text" else (b"Shipped", value)
    body = (
        b'{"text": "' + text + b'", "date": "2026-11-15", "category": "Achievement", '
        b'"tags": ["' + tag + b'"]}'
    )

    response = _send(api, "createEntry", body, "application/json")

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert [item["field"] for item in response.json()["fields"]] == [field]
    assert "Before" not in response.text


@pytest.mark.parametrize(
    "encoded",
    [
        codecs.BOM_UTF8 + b"{}",
        "{}".encode("utf-16"),
        "{}".encode("utf-16-le"),
        "{}".encode("utf-16-be"),
        "{}".encode("utf-32"),
        "{}".encode("utf-32-le"),
        "{}".encode("utf-32-be"),
    ],
    ids=[
        "utf-8-bom",
        "utf-16-bom",
        "utf-16-le",
        "utf-16-be",
        "utf-32-bom",
        "utf-32-le",
        "utf-32-be",
    ],
)
def test_unreadable_body_encodings_that_json_loads_detects_are_still_read(
    api: TestClient, contract, encoded: bytes
):
    """`json.loads` detects these encodings from the first bytes, so `{}` is read as before."""
    response = _send(api, "createEntry", encoded, "application/json")

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert [item["field"] for item in response.json()["fields"]] == ["text", "date", "category"]


# --- Telemetry ----------------------------------------------------------------------------


def test_unreadable_body_request_finished_line_shows_422_without_error_type(settings, capsys):
    captured = CapturedTelemetry()
    api = TestClient(_app(settings, telemetry=captured.telemetry))
    bodies = [*UNREADABLE_BODIES.values(), *SECRET_BODIES.values()]
    capsys.readouterr()

    for operation_id in OPERATIONS:
        for body in bodies:
            assert _send(api, operation_id, body, "application/json").status_code == 422

    output = capsys.readouterr().out
    requests = len(OPERATIONS) * len(bodies)
    lines = [line for line in json_lines(output) if line["message"] == "request finished"]
    assert len(lines) == requests
    for line in lines:
        assert line["http.response.status_code"] == 422
        assert line["level"] == "INFO"
        assert "error.type" not in line
        assert set(line) <= set(LOG_LINE_KEYS) | ALLOWED_ATTRIBUTE_KEYS
    servers = captured.server_spans()
    assert len(servers) == requests
    for server in servers:
        assert server.attributes["http.response.status_code"] == 422
        assert "error.type" not in server.attributes
        assert server.status.status_code == StatusCode.UNSET
        assert server.events == ()
    for point in captured.points("http.server.request.duration"):
        assert point.attributes["http.response.status_code"] == 422
        assert "error.type" not in point.attributes
    for log in captured.logs():
        assert "error.type" not in (log.log_record.attributes or {})
    for where, key in captured.attribute_keys():
        allowed = ALLOWED_RESOURCE_KEYS if where == "resource" else ALLOWED_ATTRIBUTE_KEYS
        assert key in allowed, f"{key} in {where}"
    exported = captured.everything_as_text()
    for text in (output, exported):
        assert SECRET not in text
        assert "junk" not in text
        for message in EXCEPTION_MESSAGES:
            assert message not in text
