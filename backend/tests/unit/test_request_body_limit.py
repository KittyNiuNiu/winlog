"""The limit on the size of a request body, without a database (issue #88).

`REQUEST_BODY_MAX_BYTES` (app/settings.py) and the middleware that enforces it
(app/body_limit.py). The body limit has no requirement ID, so every test starts with
`test_request_body_limit_`. Saving, the largest valid requests and a real server (uvicorn
with h11, chunked bodies) are tested against PostgreSQL in
tests/integration/test_request_body_limit.py.
"""

import asyncio
import re
import uuid
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.auth import get_current_user
from app.body_limit import RequestBodyLimitMiddleware
from app.health import check_database
from app.main import create_app
from app.models import User
from app.settings import (
    MAX_REQUEST_BODY_MAX_BYTES,
    MIN_REQUEST_BODY_MAX_BYTES,
    Settings,
    SettingsError,
    load_settings,
)
from app.telemetry import ALLOWED_ATTRIBUTE_KEYS, ALLOWED_RESOURCE_KEYS
from tests.conftest import OPENAPI_PATH
from tests.telemetry_capture import CapturedTelemetry, json_lines
from tests.unit.conftest import ALLOWED_ORIGIN

ROOT = Path(__file__).resolve().parents[3]
OPENAPI = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
VARIABLE = "REQUEST_BODY_MAX_BYTES"
DEFAULT = 262_144
TOO_LARGE = {"code": "request_too_large", "message": "The request body is too large."}
ENTRY_ID = "123e4567-e89b-12d3-a456-426614174000"
# A marker that must never appear in a response, a log line or telemetry.
SECRET = "body-limit-marker-5e2b"
# Every method and path the issue names, plus one of each method the API uses.
PATHS = [
    ("GET", "/entries"),
    ("POST", "/entries"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/login"),
    ("POST", "/auth/register"),
    ("PUT", f"/entries/{ENTRY_ID}"),
    ("PATCH", f"/summaries/{ENTRY_ID}"),
    ("DELETE", "/account"),
    ("GET", "/health"),
    ("GET", "/no-such-path"),
    ("OPTIONS", "/entries"),
]


def _padded(size: int) -> bytes:
    """A valid JSON object of exactly `size` bytes: spaces after its closing brace."""
    body = ('{"text":"' + SECRET + '"}').encode()
    assert len(body) <= size
    return body + b" " * (size - len(body))


def _chunks(body: bytes, size: int = 10_000):
    """The body as a generator, so the test client sends it chunked without Content-Length."""
    for start in range(0, len(body), size):
        yield body[start : start + size]


def _settings(**values) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://winlog:unit-test-secret@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        **values,
    )


def _app(settings: Settings, telemetry: CapturedTelemetry | None = None) -> FastAPI:
    """The real app with a route that reports the body it received, and a stand-in user.

    Neither the route nor the stand-in user must run for a body over the limit.
    """
    app = create_app(settings, telemetry=telemetry.telemetry if telemetry else None)
    app.state.reached = []
    app.dependency_overrides[check_database] = lambda: True

    def stand_in_user() -> User:
        app.state.reached.append("authentication")
        return User(id=uuid.uuid4(), email="a@b.c")

    app.dependency_overrides[get_current_user] = stand_in_user

    @app.post("/test-only/echo")
    async def echo(request: Request) -> dict:
        body = await request.body()
        app.state.reached.append("route")
        return {"bytes": len(body), "start": body[:20].decode()}

    return app


@pytest.fixture
def api(settings: Settings) -> TestClient:
    return TestClient(_app(settings))


def _assert_too_large(response) -> None:
    assert response.status_code == 413, response.text
    assert response.json() == TOO_LARGE
    assert response.headers["content-type"] == "application/json"
    assert "Content Too Large" not in response.text
    assert SECRET not in response.text


# --- The setting -------------------------------------------------------------------------


@pytest.fixture
def required_env(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")


def test_request_body_limit_defaults_to_262144(required_env):
    assert load_settings().request_body_max_bytes == DEFAULT == 256 * 1024


@pytest.mark.parametrize(
    ("value", "expected"),
    [("131072", 131_072), ("262144", 262_144), (" 300000 ", 300_000), ("10485760", 10_485_760)],
)
def test_request_body_limit_comes_from_the_environment(required_env, monkeypatch, value, expected):
    monkeypatch.setenv(VARIABLE, value)

    assert load_settings().request_body_max_bytes == expected


@pytest.mark.parametrize(
    "value",
    ["", " ", "0", "-1", "131071", "10485761", "256k", "2.5", "abc", "+262144", "262_144", "1e6"],
)
def test_request_body_limit_invalid_value_stops_the_backend_naming_the_variable(
    required_env, monkeypatch, value
):
    monkeypatch.setenv(VARIABLE, value)

    message = (
        f"^Invalid configuration: {VARIABLE} is invalid: .*whole number from 131072 to 10485760"
    )
    with pytest.raises(SettingsError, match=message):
        load_settings()
    with pytest.raises(SettingsError, match=f"{VARIABLE} is invalid"):
        create_app()


@pytest.mark.parametrize("value", [0, 131_071, 10_485_761, True, 2.5, None, "256k"])
def test_request_body_limit_given_in_code_must_be_in_range(value):
    with pytest.raises(ValueError, match="whole number from 131072 to 10485760"):
        _settings(request_body_max_bytes=value)


def test_request_body_limit_range_keeps_the_largest_valid_request():
    """The largest valid body, a summary edit of 10,000 escaped emoji, fits the minimum."""
    largest = ('{"text":"' + "\\ud83c\\udf89" * 10_000 + '"}').encode()

    assert len(largest) == 120_011
    assert MIN_REQUEST_BODY_MAX_BYTES == 131_072 > len(largest)
    assert MAX_REQUEST_BODY_MAX_BYTES == 10 * 1024 * 1024


def _comment_above(lines: list[str], line: str) -> str:
    """The comment lines right above `line` in .env.example, as one text."""
    end = lines.index(line)
    start = end
    while lines[start - 1].startswith("#"):
        start -= 1
    return " ".join(comment.removeprefix("#").strip() for comment in lines[start:end])


def test_request_body_limit_is_documented_in_env_example():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    variables = [line for line in lines if re.match(r"[A-Z_]+=", line)]

    # Right after DATABASE_QUERY_TIMEOUT_SECONDS, with the default as its value.
    position = variables.index("DATABASE_QUERY_TIMEOUT_SECONDS=10")
    assert variables[position + 1] == f"{VARIABLE}=262144"
    comment = _comment_above(lines, f"{VARIABLE}=262144")
    assert comment.startswith("Optional, default 262144 (256 KiB). ")
    for phrase in (
        "largest request body",
        "413 request_too_large",
        "Whole number from 131072 to 10485760.",
        "10,000-character summary edit",
        "about 120 KB",
    ):
        assert phrase in comment


def test_request_body_limit_is_passed_by_docker_compose():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["backend"]["environment"]
    names = list(environment)

    assert environment[VARIABLE] == "${REQUEST_BODY_MAX_BYTES:-262144}"
    position = names.index("DATABASE_QUERY_TIMEOUT_SECONDS")
    assert names[position + 1] == VARIABLE


# --- The contract ------------------------------------------------------------------------


def test_request_body_limit_is_a_contract_error_with_a_shared_413_response(contract):
    assert (
        "request_too_large"
        in OPENAPI["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
    )
    response = OPENAPI["components"]["responses"]["RequestTooLarge"]
    example = response["content"]["application/json"]["example"]
    assert example == TOO_LARGE
    contract("Error").validate(example)


def test_request_body_limit_413_is_listed_on_every_operation_with_a_body():
    with_body = {
        operation["operationId"]: operation["responses"]
        for path in OPENAPI["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "requestBody" in operation
    }

    assert set(with_body) == {
        "register",
        "login",
        "deleteAccount",
        "createEntry",
        "updateEntry",
        "suggestCategoryAndTags",
        "generateSummary",
        "updateSummary",
    }
    for responses in with_body.values():
        assert responses["413"] == {"$ref": "#/components/responses/RequestTooLarge"}


def test_request_body_limit_is_described_in_the_contract():
    description = " ".join(OPENAPI["info"]["description"].split())

    assert "`REQUEST_BODY_MAX_BYTES` environment variable (default 262,144)" in description
    assert "413 `request_too_large` on every path and method" in description
    assert "before authentication and validation" in description
    assert "16 KiB" in description and "plain-text 400" in description
    assert "returns 413 with `code: request_too_large`" in description


# --- Through the app ---------------------------------------------------------------------


@pytest.mark.parametrize("chunked", [False, True])
def test_request_body_limit_body_of_exactly_the_limit_reaches_the_app(api, chunked):
    body = _padded(DEFAULT)
    content = _chunks(body) if chunked else body

    response = api.post("/test-only/echo", content=content)

    assert response.status_code == 200, response.text
    assert response.json() == {"bytes": DEFAULT, "start": body[:20].decode()}


@pytest.mark.parametrize("chunked", [False, True])
def test_request_body_limit_one_byte_more_is_413(api, chunked):
    body = _padded(DEFAULT + 1)

    response = api.post("/test-only/echo", content=_chunks(body) if chunked else body)

    _assert_too_large(response)
    assert api.app.state.reached == []


def test_request_body_limit_chunked_request_has_no_content_length():
    """The test client sends a generator without Content-Length, as a chunked body."""
    seen: list[dict] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append({key.decode(): value.decode() for key, value in scope["headers"]})
        await receive()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    TestClient(app).post("/", content=_chunks(b"x" * 100))

    assert "content-length" not in seen[0]
    assert seen[0]["transfer-encoding"] == "chunked"


def test_request_body_limit_uses_the_setting():
    api = TestClient(_app(_settings(request_body_max_bytes=131_072)))

    assert api.post("/test-only/echo", content=_padded(131_072)).status_code == 200
    _assert_too_large(api.post("/test-only/echo", content=_padded(131_073)))
    _assert_too_large(api.post("/test-only/echo", content=_chunks(_padded(131_073))))


@pytest.mark.parametrize(("method", "path"), PATHS)
@pytest.mark.parametrize("token", [None, "stand-in"])
def test_request_body_limit_content_length_over_the_limit_is_413_on_every_path_and_method(
    api, method, path, token
):
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    response = api.request(method, path, content=_padded(DEFAULT + 1), headers=headers)

    _assert_too_large(response)
    # Neither authentication nor any route ran.
    assert api.app.state.reached == []


@pytest.mark.parametrize(("method", "path"), PATHS)
def test_request_body_limit_chunked_body_over_the_limit_is_413_on_every_path_and_method(
    api, method, path
):
    response = api.request(
        method,
        path,
        content=_chunks(_padded(DEFAULT + 1)),
        headers={"Authorization": "Bearer stand-in"},
    )

    _assert_too_large(response)
    assert api.app.state.reached == []


def test_request_body_limit_413_validates_against_the_contract(api, contract):
    response = api.post("/entries", content=_padded(DEFAULT + 1))

    contract("Error").validate(response.json())


def _cors_headers(response) -> dict[str, str]:
    return {
        name: value
        for name, value in response.headers.items()
        if name.startswith("access-control-") or name == "vary"
    }


def test_request_body_limit_413_has_the_cors_headers_of_other_errors(api):
    origin = {"Origin": ALLOWED_ORIGIN}
    other_error = api.get("/no-such-path", headers=origin)

    for content in (_padded(DEFAULT + 1), _chunks(_padded(DEFAULT + 1))):
        response = api.post("/entries", content=content, headers=origin)

        _assert_too_large(response)
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert _cors_headers(response) == _cors_headers(other_error)


def test_request_body_limit_413_for_another_origin_has_no_cors_headers(api):
    response = api.post(
        "/entries", content=_padded(DEFAULT + 1), headers={"Origin": "https://evil.example"}
    )

    _assert_too_large(response)
    assert not [name for name in response.headers if name.startswith("access-control-")]


def test_request_body_limit_requests_within_the_limit_behave_as_before(api):
    response = api.post("/test-only/echo", content=b"")
    assert response.json() == {"bytes": 0, "start": ""}
    # A bodiless request still reaches the API and gets its usual answers.
    assert api.get("/no-such-path").json()["code"] == "not_found"
    assert api.post("/health").json()["code"] == "method_not_allowed"
    response = api.post(
        "/entries", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.json()["code"] == "validation_failed"


def test_request_body_limit_413_has_a_request_finished_line_and_nothing_of_the_body(
    settings, capsys
):
    captured = CapturedTelemetry()
    api = TestClient(_app(settings, captured))
    capsys.readouterr()

    for content in (_padded(DEFAULT + 1), _chunks(_padded(DEFAULT + 1))):
        _assert_too_large(api.post("/entries", content=content))

    output = capsys.readouterr().out
    lines = [line for line in json_lines(output) if line["message"] == "request finished"]
    assert [line["http.response.status_code"] for line in lines] == [413, 413]
    for line in lines:
        assert set(line) - {"timestamp", "level", "logger", "message", "trace_id", "span_id"} == {
            "http.request.method",
            "http.response.status_code",
            "duration_ms",
        }
        assert line["level"] == "INFO"
    logs = [log for log in captured.logs() if log.log_record.body == "request finished"]
    assert [log.log_record.attributes["http.response.status_code"] for log in logs] == [413, 413]
    servers = captured.server_spans()
    assert [dict(span.attributes) for span in servers] == [
        {"http.request.method": "POST", "http.response.status_code": 413}
    ] * 2
    for where, key in captured.attribute_keys():
        assert key in (ALLOWED_RESOURCE_KEYS if where == "resource" else ALLOWED_ATTRIBUTE_KEYS)
    assert SECRET not in output
    assert SECRET not in captured.everything_as_text()


# --- The middleware on its own -----------------------------------------------------------


class _Run:
    """One request through the middleware alone, with a scripted server."""

    def __init__(self, limit: int, headers: list[tuple[bytes, bytes]] | None = None) -> None:
        self.limit = limit
        self.scope: Scope = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": headers or [],
        }
        self.sent: list[Message] = []
        self.app_received: list[Message] = []
        self.app_called = False
        self.receive_calls = 0

    async def app(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.app_called = True
        while True:
            message = await receive()
            self.app_received.append(message)
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        if message["type"] == "http.request":
            # A server's receive after the body: the disconnect at the end.
            self.app_received.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    def run(self, messages: list[Message], *, endless_chunk: bytes | None = None) -> None:
        script = list(messages)

        async def receive() -> Message:
            self.receive_calls += 1
            if script:
                return script.pop(0)
            if endless_chunk is not None:
                return {"type": "http.request", "body": endless_chunk, "more_body": True}
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            self.sent.append(message)

        middleware = RequestBodyLimitMiddleware(self.app, max_body_bytes=self.limit)
        asyncio.run(middleware(self.scope, receive, send))

    @property
    def status(self) -> int:
        return self.sent[0]["status"]


def test_request_body_limit_rejects_a_content_length_over_the_limit_without_reading():
    run = _Run(100, headers=[(b"content-length", b"101")])

    run.run([])

    assert run.status == 413
    assert run.receive_calls == 0
    assert not run.app_called
    assert dict(run.sent[0]["headers"])[b"content-type"] == b"application/json"


def test_request_body_limit_stops_reading_a_chunked_body_once_over_the_limit():
    run = _Run(100)

    run.run([], endless_chunk=b"x" * 30)

    assert run.status == 413
    # 30, 60, 90, 120: the fourth chunk crosses the limit, and nothing more is read.
    assert run.receive_calls == 4
    assert not run.app_called


def test_request_body_limit_counts_the_bytes_even_when_content_length_is_lower():
    """A wrong Content-Length cannot get a larger body past the limit."""
    run = _Run(100, headers=[(b"content-length", b"10")])

    run.run([{"type": "http.request", "body": b"x" * 101}])

    assert run.status == 413
    assert not run.app_called


def test_request_body_limit_passes_a_body_within_the_limit_on_as_one_message():
    run = _Run(100, headers=[(b"content-length", b"100")])

    run.run(
        [
            {"type": "http.request", "body": b"a" * 40, "more_body": True},
            {"type": "http.request", "body": b"", "more_body": True},
            {"type": "http.request", "body": b"b" * 60, "more_body": False},
        ]
    )

    assert run.status == 200
    assert run.app_received == [
        {"type": "http.request", "body": b"a" * 40 + b"b" * 60, "more_body": False},
        {"type": "http.disconnect"},
    ]


def test_request_body_limit_passes_a_disconnect_on_to_the_app():
    run = _Run(100)

    run.run(
        [{"type": "http.request", "body": b"part", "more_body": True}, {"type": "http.disconnect"}]
    )

    assert run.app_received == [
        {"type": "http.request", "body": b"part", "more_body": True},
        {"type": "http.disconnect"},
    ]


@pytest.mark.parametrize("value", [b"abc", b"-5", b""])
def test_request_body_limit_counts_the_body_when_content_length_is_not_a_number(value):
    run = _Run(100, headers=[(b"content-length", value)])

    run.run([{"type": "http.request", "body": b"x" * 100}])
    assert run.status == 200

    over = _Run(100, headers=[(b"content-length", value)])
    over.run([{"type": "http.request", "body": b"x" * 101}])
    assert over.status == 413


def test_request_body_limit_leaves_other_connection_types_alone():
    calls: list[str] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        calls.append(scope["type"])

    middleware = RequestBodyLimitMiddleware(app, max_body_bytes=100)
    for kind in ("lifespan", "websocket"):
        asyncio.run(
            middleware({"type": kind, "headers": [(b"content-length", b"999")]}, None, None)
        )

    assert calls == ["lifespan", "websocket"]
