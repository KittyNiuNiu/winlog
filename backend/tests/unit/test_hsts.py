"""The HSTS header on every response, without a database (issue #99).

`HSTS_MAX_AGE_SECONDS` (H, app/settings.py, default 31,536,000) and the middleware that adds
`Strict-Transport-Security: max-age=<H>; includeSubDomains` (app/hsts.py). The header has no
requirement ID, so every test starts with `test_hsts_`. The responses that need a database
(`GET /entries` 200, `POST /entries` 201, the Markdown export) and a real uvicorn server are
tested against PostgreSQL in tests/integration/test_hsts.py.
"""

import asyncio
import re
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.health import check_database
from app.hsts import StrictTransportSecurityMiddleware, hsts_header_value
from app.main import create_app
from app.settings import MAX_HSTS_MAX_AGE_SECONDS, Settings, SettingsError, load_settings
from app.telemetry import ALLOWED_ATTRIBUTE_KEYS, ALLOWED_RESOURCE_KEYS
from tests.telemetry_capture import CapturedTelemetry, json_lines
from tests.unit.conftest import ALLOWED_ORIGIN, FakeAttempts

ROOT = Path(__file__).resolve().parents[3]
VARIABLE = "HSTS_MAX_AGE_SECONDS"
DEFAULT = 31_536_000
HEADER = "strict-transport-security"
EXPECTED = "max-age=31536000; includeSubDomains"
OTHER_ORIGIN = "https://not-allowed.example"
CRASH_PATH = "/test-only/crash"
# Log fields that differ from one request to the next.
VARYING_LOG_FIELDS = {"timestamp", "trace_id", "span_id", "duration_ms"}
BODY_LIMIT = 262_144
PREFLIGHT = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Accept"}
ALLOWED_PREFLIGHT = {"Origin": ALLOWED_ORIGIN, **PREFLIGHT}
OTHER_PREFLIGHT = {"Origin": OTHER_ORIGIN, **PREFLIGHT}
JSON = {"Content-Type": "application/json"}
LOGIN = b'{"email":"a@b.c","password":"x"}'

# Every response the issue names that needs no database, as (id, method, path, request
# headers, body, expected status). `_send` sets up the 503 and the 429 by their ids.
REQUESTS = [
    ("health_200", "GET", "/health", {}, None, 200),
    ("health_503", "GET", "/health", {}, None, 503),
    ("not_authenticated_401", "GET", "/entries", {}, None, 401),
    ("unknown_path_404", "GET", "/no-such-path", {}, None, 404),
    ("wrong_method_405", "HEAD", "/health", {}, None, 405),
    ("validation_failed_422", "POST", "/auth/login", JSON, b"{}", 422),
    ("request_too_large_413", "POST", "/entries", {}, b"x" * (BODY_LIMIT + 1), 413),
    ("too_many_attempts_429", "POST", "/auth/login", JSON, LOGIN, 429),
    ("internal_error_500", "GET", CRASH_PATH, {}, None, 500),
    ("preflight_allowed_origin", "OPTIONS", "/entries", ALLOWED_PREFLIGHT, None, 200),
    ("preflight_other_origin", "OPTIONS", "/entries", OTHER_PREFLIGHT, None, 400),
    ("docs", "GET", "/docs", {}, None, 200),
    ("openapi_json", "GET", "/openapi.json", {}, None, 200),
]
# The error code in the body of each error response above (HEAD has no body).
ERROR_CODES = {
    "health_503": "database_unreachable",
    "not_authenticated_401": "not_authenticated",
    "unknown_path_404": "not_found",
    "validation_failed_422": "validation_failed",
    "request_too_large_413": "request_too_large",
    "too_many_attempts_429": "too_many_attempts",
    "internal_error_500": "internal_error",
}
REQUEST_IDS = [request[0] for request in REQUESTS]


def _settings(**values) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://winlog:unit-test-secret@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        **values,
    )


def _app(settings: Settings, telemetry: CapturedTelemetry | None = None) -> FastAPI:
    """The real app, with a database check the test controls and a route that crashes."""
    app = create_app(settings, telemetry=telemetry.telemetry if telemetry else None)
    app.state.database_ok = True
    app.dependency_overrides[check_database] = lambda: app.state.database_ok

    @app.get(CRASH_PATH)
    def crash_route() -> dict:
        raise RuntimeError("boom")

    return app


def _client(telemetry: CapturedTelemetry | None = None, **values) -> TestClient:
    # The crash still reaches the server (test_errors.py); only the response matters here.
    return TestClient(_app(_settings(**values), telemetry), raise_server_exceptions=False)


def _send(client: TestClient, attempts: FakeAttempts, request: tuple, origin: str | None = None):
    name, method, path, headers, body, _status = request
    client.app.state.database_ok = name != "health_503"
    attempts.retry_after = 61 if name == "too_many_attempts_429" else None
    if origin is not None and "Origin" not in headers:
        headers = {**headers, "Origin": origin}
    return client.request(method, path, headers=headers, content=body)


def _hsts(response) -> list[str]:
    """Every `Strict-Transport-Security` value of the response (names match in any case)."""
    return response.headers.get_list(HEADER)


# --- The setting -------------------------------------------------------------------------


@pytest.fixture
def required_env(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")


def test_hsts_max_age_defaults_to_one_year(required_env):
    assert load_settings().hsts_max_age_seconds == DEFAULT == 365 * 24 * 60 * 60


def test_hsts_max_age_upper_bound_is_two_years():
    assert MAX_HSTS_MAX_AGE_SECONDS == 63_072_000 == 2 * DEFAULT


@pytest.mark.parametrize(
    ("value", "expected"),
    [("0", 0), ("1", 1), ("31536000", 31_536_000), (" 86400 ", 86_400), ("63072000", 63_072_000)],
)
def test_hsts_max_age_comes_from_the_environment(required_env, monkeypatch, value, expected):
    monkeypatch.setenv(VARIABLE, value)

    assert load_settings().hsts_max_age_seconds == expected


@pytest.mark.parametrize(
    "value",
    ["", " ", "-1", "63072001", "1.5", "abc", "+5", "1_0", "10.0", "1e3", "0x10", "1 year", "٣"],
)
def test_hsts_max_age_invalid_value_stops_the_backend_naming_the_variable(
    required_env, monkeypatch, value
):
    monkeypatch.setenv(VARIABLE, value)

    message = f"^Invalid configuration: {VARIABLE} is invalid: .*whole number from 0 to 63072000"
    with pytest.raises(SettingsError, match=message):
        load_settings()
    with pytest.raises(SettingsError, match=f"{VARIABLE} is invalid"):
        create_app()


@pytest.mark.parametrize("value", [-1, 63_072_001, True, 1.5, 10.0, None, "abc"])
def test_hsts_max_age_given_in_code_must_be_in_range(value):
    with pytest.raises(ValueError, match="whole number from 0 to 63072000"):
        _settings(hsts_max_age_seconds=value)


# --- The header --------------------------------------------------------------------------


def test_hsts_header_value_has_max_age_and_include_subdomains_but_no_preload():
    assert hsts_header_value(DEFAULT) == EXPECTED
    assert hsts_header_value(5) == "max-age=5; includeSubDomains"
    assert "preload" not in EXPECTED


def test_hsts_header_with_the_default_setting(client: TestClient):
    """The `settings` fixture sets no H, so the default applies."""
    response = client.get("/health")

    assert response.status_code == 200
    assert _hsts(response) == [EXPECTED]


@pytest.mark.parametrize("request_", REQUESTS, ids=REQUEST_IDS)
@pytest.mark.parametrize("max_age", [1, DEFAULT, 63_072_000])
def test_hsts_header_is_on_every_response_exactly_once(attempts, request_, max_age):
    client = _client(hsts_max_age_seconds=max_age)

    response = _send(client, attempts, request_)

    assert response.status_code == request_[-1], response.text
    if request_[0] in ERROR_CODES:
        assert response.json()["code"] == ERROR_CODES[request_[0]]
    assert _hsts(response) == [f"max-age={max_age}; includeSubDomains"]


@pytest.mark.parametrize("request_", REQUESTS, ids=REQUEST_IDS)
def test_hsts_header_is_on_no_response_with_zero(attempts, request_):
    client = _client(hsts_max_age_seconds=0)

    response = _send(client, attempts, request_)

    assert response.status_code == request_[-1], response.text
    assert _hsts(response) == []
    assert not [name for name in response.headers if "strict" in name.lower()]


@pytest.mark.parametrize("origin", [None, ALLOWED_ORIGIN, OTHER_ORIGIN])
@pytest.mark.parametrize("request_", REQUESTS, ids=REQUEST_IDS)
def test_hsts_header_is_the_only_change_to_a_response(attempts, request_, origin):
    """Status, body and every other header (CORS, Retry-After, ...) are as with H = 0."""
    with_header = _send(_client(hsts_max_age_seconds=DEFAULT), attempts, request_, origin)
    without = _send(_client(hsts_max_age_seconds=0), attempts, request_, origin)

    assert with_header.status_code == without.status_code == request_[-1]
    assert with_header.content == without.content
    others = [(name, value) for name, value in with_header.headers.multi_items() if name != HEADER]
    assert others == without.headers.multi_items()
    assert _hsts(with_header) == [EXPECTED]


def test_hsts_header_keeps_retry_after_and_the_cors_headers(attempts):
    client = _client(hsts_max_age_seconds=DEFAULT)

    blocked = _send(client, attempts, REQUESTS[REQUEST_IDS.index("too_many_attempts_429")])
    preflight = _send(client, attempts, REQUESTS[REQUEST_IDS.index("preflight_allowed_origin")])
    other = _send(client, attempts, REQUESTS[REQUEST_IDS.index("preflight_other_origin")])

    assert blocked.headers["retry-after"] == "61"
    assert _hsts(blocked) == [EXPECTED]
    assert preflight.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert _hsts(preflight) == [EXPECTED]
    assert not [name for name in other.headers if name.startswith("access-control-")]
    assert other.text == "Disallowed CORS origin"
    assert _hsts(other) == [EXPECTED]


@pytest.mark.parametrize(
    ("base_url", "forwarded_proto"),
    [("http://testserver", None), ("http://testserver", "http"), ("https://testserver", "https")],
)
def test_hsts_depends_only_on_the_setting_not_on_the_scheme(base_url, forwarded_proto):
    headers = {"X-Forwarded-Proto": forwarded_proto} if forwarded_proto else {}
    on = TestClient(_app(_settings(hsts_max_age_seconds=DEFAULT)), base_url=base_url)
    off = TestClient(_app(_settings(hsts_max_age_seconds=0)), base_url=base_url)

    assert _hsts(on.get("/health", headers=headers)) == [EXPECTED]
    assert _hsts(off.get("/health", headers=headers)) == []


def test_hsts_adds_no_log_or_span_field(attempts, capsys):
    """The `request finished` lines and the spans are the same with and without the header."""

    def run(max_age: int) -> tuple[list[dict], list[dict], CapturedTelemetry]:
        captured = CapturedTelemetry()
        client = _client(captured, hsts_max_age_seconds=max_age)
        capsys.readouterr()
        for request in REQUESTS:
            _send(client, attempts, request, ALLOWED_ORIGIN)
        lines = [
            {key: value for key, value in line.items() if key not in VARYING_LOG_FIELDS}
            for line in json_lines(capsys.readouterr().out)
        ]
        spans = [dict(span.attributes) for span in captured.server_spans()]
        return lines, spans, captured

    lines_on, spans_on, captured = run(DEFAULT)
    lines_off, spans_off, _ = run(0)

    assert lines_on == lines_off
    assert len([line for line in lines_on if line["message"] == "request finished"]) == len(
        REQUESTS
    )
    assert spans_on == spans_off
    for where, key in captured.attribute_keys():
        assert key in (ALLOWED_RESOURCE_KEYS if where == "resource" else ALLOWED_ATTRIBUTE_KEYS)
    text = captured.everything_as_text() + str(lines_on)
    assert "includeSubDomains" not in text
    assert "strict-transport-security" not in text.lower()


# --- The middleware on its own -----------------------------------------------------------


def _run(
    middleware_max_age: int, start: Message, scope_type: str = "http"
) -> tuple[list[Message], list]:
    """One response through the middleware alone. Returns the messages sent and the sends."""
    sent: list[Message] = []
    sends_seen: list = []
    body = {"type": "http.response.body", "body": b"ok"}

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        sends_seen.append(send)
        await send(start)
        await send(body)

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    middleware = StrictTransportSecurityMiddleware(app, max_age_seconds=middleware_max_age)
    asyncio.run(middleware({"type": scope_type}, receive, send))
    sends_seen.append(send)
    return sent, sends_seen


def test_hsts_middleware_appends_the_header_and_keeps_the_rest():
    original = [(b"content-type", b"text/plain"), (b"x-other", b"1")]
    start = {"type": "http.response.start", "status": 201, "headers": original}

    sent, _ = _run(DEFAULT, start)

    assert sent == [
        {
            "type": "http.response.start",
            "status": 201,
            "headers": [*original, (b"strict-transport-security", EXPECTED.encode())],
        },
        {"type": "http.response.body", "body": b"ok"},
    ]
    # The app's own message and header list are not changed.
    assert start["headers"] == [(b"content-type", b"text/plain"), (b"x-other", b"1")]


def test_hsts_middleware_adds_the_header_to_a_response_without_headers():
    sent, _ = _run(DEFAULT, {"type": "http.response.start", "status": 204})

    assert sent[0]["headers"] == [(b"strict-transport-security", EXPECTED.encode())]


@pytest.mark.parametrize(
    "name",
    [b"strict-transport-security", b"Strict-Transport-Security", b"STRICT-TRANSPORT-SECURITY"],
)
def test_hsts_middleware_never_adds_a_second_header(name):
    own = [(name, b"max-age=5"), (b"content-type", b"text/plain")]

    sent, _ = _run(DEFAULT, {"type": "http.response.start", "status": 200, "headers": own})

    assert sent[0]["headers"] == own


def test_hsts_middleware_with_zero_adds_nothing_and_passes_the_send_through():
    start = {"type": "http.response.start", "status": 200, "headers": [(b"x-other", b"1")]}

    sent, (send_given_to_app, server_send) = _run(0, start)

    assert sent[0] is start
    assert start["headers"] == [(b"x-other", b"1")]
    assert send_given_to_app is server_send


@pytest.mark.parametrize("scope_type", ["lifespan", "websocket"])
def test_hsts_middleware_passes_other_scopes_through(scope_type):
    start = {"type": "http.response.start", "status": 200, "headers": []}

    sent, (send_given_to_app, server_send) = _run(DEFAULT, start, scope_type)

    assert send_given_to_app is server_send
    assert sent[0] is start


# --- Configuration and documentation ----------------------------------------------------


def _comment_above(lines: list[str], line: str) -> str:
    """The comment lines right above `line`, as one text."""
    end = lines.index(line)
    start = end
    while lines[start - 1].lstrip().startswith("#"):
        start -= 1
    return " ".join(comment.strip().removeprefix("#").strip() for comment in lines[start:end])


def test_hsts_is_documented_in_env_example_with_zero():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    variables = [line for line in lines if re.match(r"[A-Z_]+=", line)]

    # In the Backend part, right after REQUEST_BODY_MAX_BYTES.
    position = variables.index("REQUEST_BODY_MAX_BYTES=262144")
    assert variables[position + 1] == f"{VARIABLE}=0"
    comment = _comment_above(lines, f"{VARIABLE}=0")
    assert comment.startswith("Optional, default 31536000 (one year). ")
    for phrase in (
        "Strict-Transport-Security header",
        "a browser that has reached the backend over HTTPS then uses only HTTPS for it, for that "
        "many seconds",
        "0 sends no header",
        "The value is 0 here because the backend on your computer and in Docker Compose serves "
        "plain HTTP, where the header must not be sent and browsers ignore it",
        "Whole number from 0 to 63072000",
    ):
        assert phrase in comment


def test_hsts_is_passed_by_docker_compose_with_zero():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["backend"]["environment"]
    names = list(environment)

    assert environment[VARIABLE] == "${HSTS_MAX_AGE_SECONDS:-0}"
    assert names[names.index("REQUEST_BODY_MAX_BYTES") + 1] == VARIABLE


def test_hsts_render_yaml_sets_one_year_on_both_backends_and_nothing_on_the_static_sites():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    blueprint = yaml.safe_load(text)
    services = {service["name"]: service for service in blueprint["services"]}

    for name in ("winlog-api", "winlog-api-dev"):
        keys = [var["key"] for var in services[name]["envVars"]]
        values = {var["key"]: var.get("value") for var in services[name]["envVars"]}
        assert keys[keys.index("REQUEST_BODY_MAX_BYTES") + 1] == VARIABLE
        assert values[VARIABLE] == "31536000"
    # Each with a one-line comment right above it, after a blank line.
    lines = text.splitlines()
    key_lines = [
        number for number, line in enumerate(lines) if line.strip() == f"- key: {VARIABLE}"
    ]
    assert len(key_lines) == 2
    for number in key_lines:
        assert lines[number - 1].strip().startswith("# ")
        assert lines[number - 2].strip() == ""
        assert "(#99)" in lines[number - 1]
    # The static sites get their header from Render, so they stay without `headers`.
    for name in ("winlog-app", "winlog-app-dev"):
        assert "headers" not in services[name]
        assert VARIABLE not in {var["key"] for var in services[name]["envVars"]}


def test_hsts_render_yaml_value_is_the_settings_default():
    """So each backend sends the header with the new image, before any Blueprint sync."""
    assert str(Settings.model_fields["hsts_max_age_seconds"].default) == "31536000"


def test_hsts_deploy_guide_documents_the_setting_https_and_the_live_check():
    guide = (ROOT / "ops" / "deployment.md").read_text(encoding="utf-8")
    flat = " ".join(guide.split())

    assert "\n| `HSTS_MAX_AGE_SECONDS` | `31536000` | `render.yaml` | no |\n" in guide
    dev = flat[flat.index("### Dev backend") : flat.index("### Static sites")]
    assert "`HSTS_MAX_AGE_SECONDS`" in dev and "are the same as production's" in dev
    https = flat[flat.index("**HTTPS (#99)**") : flat.index("### Dev backend")]
    for phrase in (
        "Render redirects every plain `http://` request to `https://` for all four services",
        "(https://render.com/docs/tls)",
        "(https://render.com/docs/web-services)",
        "#38 saw the redirect on production",
        "Nobody has checked it on dev, because a cloud session cannot send plain HTTP",
        "`max-age=315360000; includeSubdomains; preload` on 15 November 2026",
        "The backends set their own header from `HSTS_MAX_AGE_SECONDS`",
        "Render's redirect and its own error pages, and uvicorn's plain-text 400 for request "
        "headers over 16 KiB",
        "Setting the value to 0 does not make browsers forget the header",
        "until `max-age` runs out",
    ):
        assert phrase in https, phrase
    checks = flat[flat.index("## Live checks after a deploy") :]
    assert (
        "`curl -sS -D - -o /dev/null https://winlog-api-dev.onrender.com/health` shows "
        "`strict-transport-security: max-age=31536000; includeSubDomains`" in checks
    )
    assert "`https://winlog-api.onrender.com/health` after the production deploy" in checks
