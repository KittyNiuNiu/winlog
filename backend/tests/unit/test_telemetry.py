"""Telemetry for every request and the privacy allowlist (issue #74), without a database.

The summary journey itself is tested against PostgreSQL in
tests/integration/test_telemetry.py. Every test captures telemetry with in-memory exporters;
none needs a collector.
"""

import logging
import re
import socket
import time

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.trace import SpanKind, StatusCode

from app import telemetry as telemetry_module
from app.health import check_database
from app.main import create_app
from app.settings import Settings, SettingsError, load_settings
from app.telemetry import (
    ALLOWED_ATTRIBUTE_KEYS,
    ALLOWED_RESOURCE_KEYS,
    LOG_LINE_KEYS,
    Telemetry,
    configure_logging,
    span,
)
from tests.telemetry_capture import CapturedTelemetry, json_lines
from tests.unit.conftest import ALLOWED_ORIGIN

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
SPAN_ID = re.compile(r"^[0-9a-f]{16}$")
ENTRY_ID = "3f2a6c1e-8f5b-4d2a-9c3e-1b2d3e4f5a6b"
SECRET = "telemetry-marker-7d1c"


def _app(settings: Settings, captured: CapturedTelemetry) -> FastAPI:
    app = create_app(settings, telemetry=captured.telemetry)
    app.dependency_overrides[check_database] = lambda: True
    return app


@pytest.fixture
def captured() -> CapturedTelemetry:
    return CapturedTelemetry()


@pytest.fixture
def api(settings: Settings, captured: CapturedTelemetry) -> TestClient:
    return TestClient(_app(settings, captured), raise_server_exceptions=False)


def _finished_lines(output: str) -> list[dict]:
    return [line for line in json_lines(output) if line["message"] == "request finished"]


# --- Every request ----------------------------------------------------------------------------


def test_every_request_gets_one_server_span_named_after_the_route_template(api, captured, capsys):
    capsys.readouterr()
    response = api.put(f"/entries/{ENTRY_ID}", json={"text": SECRET})

    assert response.status_code == 401
    [server] = captured.server_spans()
    assert server.name == "PUT /entries/{entryId}"
    assert server.kind == SpanKind.SERVER
    assert dict(server.attributes) == {
        "http.request.method": "PUT",
        "http.route": "/entries/{entryId}",
        "http.response.status_code": 401,
    }
    assert server.status.status_code == StatusCode.UNSET
    [point] = captured.points("http.server.request.duration")
    assert dict(point.attributes) == {
        "http.request.method": "PUT",
        "http.route": "/entries/{entryId}",
        "http.response.status_code": 401,
    }
    assert point.count == 1
    [line] = _finished_lines(capsys.readouterr().out)
    assert line["level"] == "INFO"
    assert line["http.request.method"] == "PUT"
    assert line["http.route"] == "/entries/{entryId}"
    assert line["http.response.status_code"] == 401
    assert isinstance(line["duration_ms"], int)
    assert ENTRY_ID not in captured.everything_as_text()
    assert ENTRY_ID not in str(line)
    assert SECRET not in captured.everything_as_text()


def test_a_method_the_route_does_not_allow_still_uses_the_route_template(api, captured):
    # Entries are changed with PUT; PATCH matches the path but not the method (405).
    response = api.patch(f"/entries/{ENTRY_ID}", json={"text": SECRET})

    assert response.status_code == 405
    [server] = captured.server_spans()
    assert server.name == "PATCH /entries/{entryId}"
    assert server.attributes["http.route"] == "/entries/{entryId}"
    assert ENTRY_ID not in captured.everything_as_text()


def test_every_endpoint_and_request_gets_its_own_trace(api, captured):
    api.get("/health")
    api.get("/tags")
    api.post("/auth/logout")

    names = [server.name for server in captured.server_spans()]
    assert names == ["GET /health", "GET /tags", "POST /auth/logout"]
    trace_ids = {server.context.trace_id for server in captured.server_spans()}
    assert len(trace_ids) == 3
    points = captured.points("http.server.request.duration")
    assert sum(point.count for point in points) == 3


def test_a_path_without_a_route_is_named_by_its_method_only(api, captured, capsys):
    capsys.readouterr()
    response = api.get(f"/no-such-path/{SECRET}?tag={SECRET}")

    assert response.status_code == 404
    [server] = captured.server_spans()
    assert server.name == "GET"
    assert "http.route" not in server.attributes
    assert server.attributes["http.response.status_code"] == 404
    [line] = _finished_lines(capsys.readouterr().out)
    assert "http.route" not in line
    assert SECRET not in captured.everything_as_text()


def test_an_unknown_method_is_recorded_as_other(api, captured):
    api.request(SECRET.upper(), "/health")

    [server] = captured.server_spans()
    assert server.name == "_OTHER /health"
    assert server.attributes["http.request.method"] == "_OTHER"
    assert SECRET.upper() not in captured.everything_as_text()


def test_no_log_line_contains_a_query_string_or_client_address(api, captured, capsys):
    capsys.readouterr()
    api.get(f"/entries?tag={SECRET}", headers={"X-Forwarded-For": "198.51.100.23"})

    output = capsys.readouterr().out
    assert _finished_lines(output)
    assert SECRET not in output
    assert "198.51.100.23" not in output
    assert "testclient" not in output
    assert SECRET not in captured.everything_as_text()


def test_incoming_trace_headers_are_ignored(api, captured):
    client_trace_id = "0af7651916cd43dd8448eb211c80319c"
    api.get(
        "/health",
        headers={
            "traceparent": f"00-{client_trace_id}-b7ad6b7169203331-01",
            "tracestate": f"vendor={SECRET}",
            "baggage": f"user.email={SECRET}",
        },
    )

    [server] = captured.server_spans()
    assert server.parent is None
    assert f"{server.context.trace_id:032x}" != client_trace_id
    assert client_trace_id not in captured.everything_as_text()
    assert SECRET not in captured.everything_as_text()


def test_an_unexpected_error_gives_status_error_and_the_class_name_only(settings, captured, capsys):
    app = _app(settings, captured)

    @app.get("/test-only/crash")
    def crash() -> dict:
        raise RuntimeError(f"the message {SECRET}")

    client = TestClient(app, raise_server_exceptions=False)
    capsys.readouterr()

    response = client.get("/test-only/crash")

    assert response.status_code == 500
    [server] = captured.server_spans()
    assert server.status.status_code == StatusCode.ERROR
    assert server.status.description is None
    assert server.attributes["error.type"] == "RuntimeError"
    assert server.attributes["http.response.status_code"] == 500
    assert server.events == ()
    output = capsys.readouterr()
    [line] = _finished_lines(output.out)
    assert line["level"] == "ERROR"
    assert line["error.type"] == "RuntimeError"
    assert SECRET not in output.out
    assert "Traceback" not in output.out
    text = captured.everything_as_text()
    assert SECRET not in text
    assert "Traceback" not in text
    [log] = [log for log in captured.logs() if log.log_record.body == "request finished"]
    assert log.log_record.severity_text == "ERROR"
    assert log.log_record.attributes["error.type"] == "RuntimeError"


def test_a_5xx_response_without_an_exception_gives_status_error(settings, captured):
    app = _app(settings, captured)

    @app.get("/test-only/unavailable")
    def unavailable():
        from app.suggestions import ai_unavailable

        raise ai_unavailable()

    TestClient(app).get("/test-only/unavailable")

    [server] = captured.server_spans()
    assert server.status.status_code == StatusCode.ERROR
    assert server.attributes["error.type"] == "503"


def test_an_exception_inside_a_span_adds_no_event_and_only_the_class_name(captured):
    with captured.telemetry.activate():
        with pytest.raises(ValueError):
            with span("test.work", {"winlog.entry_count": 3}):
                raise ValueError(f"entry text {SECRET}")

    recorded = captured.span("test.work")
    assert recorded.events == ()
    assert recorded.status.status_code == StatusCode.ERROR
    assert recorded.status.description == "ValueError"
    assert dict(recorded.attributes) == {"winlog.entry_count": 3}
    assert SECRET not in captured.everything_as_text()
    assert "Traceback" not in captured.everything_as_text()


def test_span_attributes_outside_the_allowlist_are_dropped(captured):
    with captured.telemetry.activate():
        with span("test.work", {"user.email": SECRET, "winlog.outcome": "created"}) as current:
            current.set("enduser.id", SECRET)
            current.set("winlog.entry_count", 2)

    assert dict(captured.span("test.work").attributes) == {
        "winlog.outcome": "created",
        "winlog.entry_count": 2,
    }


def test_a_span_outside_a_request_does_nothing():
    with span("test.work") as current:
        current.set("winlog.entry_count", 1)


# --- Logs -------------------------------------------------------------------------------------


def test_app_logs_keep_only_allowlisted_fields_and_the_error_type(captured, capsys):
    configure_logging()
    capsys.readouterr()

    with captured.telemetry.activate():
        with captured.telemetry.tracer.start_as_current_span("test.request") as current:
            try:
                raise ValueError(f"exception message {SECRET}")
            except ValueError:
                logging.getLogger("app.test").error(
                    "something failed",
                    exc_info=True,
                    stack_info=True,
                    extra={
                        "user.email": f"{SECRET}@example.com",
                        "entry_text": SECRET,
                        "winlog.outcome": "ai_unavailable",
                        "winlog.entry_count": 4,
                        "duration_ms": 12,
                        "http.route": ["not", "a", "plain", "value"],
                    },
                )

    output = capsys.readouterr().out
    [line] = json_lines(output)
    span_context = current.get_span_context()
    assert line == {
        "timestamp": line["timestamp"],
        "level": "ERROR",
        "logger": "app.test",
        "message": "something failed",
        "trace_id": f"{span_context.trace_id:032x}",
        "span_id": f"{span_context.span_id:016x}",
        "winlog.outcome": "ai_unavailable",
        "winlog.entry_count": 4,
        "duration_ms": 12,
        "error.type": "ValueError",
    }
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", line["timestamp"])
    assert SECRET not in output
    assert "Traceback" not in output and "Stack" not in output
    [log] = captured.logs()
    assert log.log_record.body == "something failed"
    assert dict(log.log_record.attributes) == {
        "winlog.outcome": "ai_unavailable",
        "winlog.entry_count": 4,
        "duration_ms": 12,
        "error.type": "ValueError",
    }
    assert log.log_record.trace_id == span_context.trace_id
    assert log.log_record.span_id == span_context.span_id
    assert log.instrumentation_scope.name == "app.test"
    assert SECRET not in captured.everything_as_text()


def test_json_log_lines_have_trace_and_span_ids_of_the_request(api, captured, capsys):
    capsys.readouterr()
    api.get("/health")

    [line] = _finished_lines(capsys.readouterr().out)
    [server] = captured.server_spans()
    assert set(line) <= set(LOG_LINE_KEYS) | ALLOWED_ATTRIBUTE_KEYS
    assert TRACE_ID.fullmatch(line["trace_id"])
    assert SPAN_ID.fullmatch(line["span_id"])
    assert line["trace_id"] == f"{server.context.trace_id:032x}"
    assert line["span_id"] == f"{server.context.span_id:016x}"
    [log] = captured.logs()
    assert log.log_record.trace_id == server.context.trace_id


def test_other_loggers_are_neither_printed_nor_exported(api, captured, capsys):
    capsys.readouterr()
    with captured.telemetry.activate():
        logging.getLogger("sqlalchemy.engine").warning("SELECT %s", SECRET)
        logging.getLogger("uvicorn.error").error("error %s", SECRET)
        logging.getLogger("httpx").warning("GET %s", SECRET)

    assert SECRET not in capsys.readouterr().out
    assert captured.logs() == []


def test_resource_holds_only_the_service_and_sdk_attributes(api, captured):
    api.get("/health")

    [server] = captured.server_spans()
    assert set(server.resource.attributes) <= ALLOWED_RESOURCE_KEYS
    assert server.resource.attributes["service.name"] == "winlog-backend"
    for where, key in captured.attribute_keys():
        allowed = ALLOWED_RESOURCE_KEYS if where == "resource" else ALLOWED_ATTRIBUTE_KEYS
        assert key in allowed, f"{key} in {where}"


# --- create_app many times --------------------------------------------------------------------


def test_create_app_runs_many_times_without_duplicate_handlers(settings, capsys):
    runs = [CapturedTelemetry() for _ in range(3)]
    clients = [TestClient(_app(settings, run)) for run in runs]
    capsys.readouterr()

    for client in clients:
        assert client.get("/health").status_code == 200

    handlers = [
        handler
        for handler in logging.getLogger("app").handlers
        if type(handler).__name__ == "_TelemetryLogHandler"
    ]
    assert len(handlers) == 1
    assert len(_finished_lines(capsys.readouterr().out)) == 3
    for run in runs:
        assert [server.name for server in run.server_spans()] == ["GET /health"]
        assert [log.log_record.body for log in run.logs()] == ["request finished"]
        [point] = run.points("http.server.request.duration")
        assert point.count == 1


# --- Uvicorn's access log ---------------------------------------------------------------------


def test_uvicorns_access_log_is_off_after_uvicorn_configures_logging(settings):
    # Uvicorn configures its loggers first, then imports the app, as `uvicorn app.main:app`
    # and the Docker image's command do.
    uvicorn.Config("app.main:app").configure_logging()
    assert logging.getLogger("uvicorn.access").isEnabledFor(logging.INFO)

    create_app(settings)

    access_logger = logging.getLogger("uvicorn.access")
    assert not access_logger.isEnabledFor(logging.INFO)
    assert not access_logger.hasHandlers()


# --- Settings and export ----------------------------------------------------------------------


@pytest.fixture
def base_env(no_env_file, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    monkeypatch.setenv("AI_PROVIDER", "mock")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_otlp_endpoint_empty_or_not_set_turns_export_off(base_env, monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", value)

    assert load_settings().otel_exporter_otlp_endpoint is None


def test_otlp_endpoint_is_read_from_the_environment(base_env, monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", " http://localhost:4318 ")

    assert load_settings().otel_exporter_otlp_endpoint == "http://localhost:4318"


@pytest.mark.parametrize("value", ["localhost:4318", "ftp://collector", "collector"])
def test_otlp_endpoint_must_be_an_http_url(base_env, monkeypatch, value):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", value)

    with pytest.raises(SettingsError, match="OTEL_EXPORTER_OTLP_ENDPOINT is invalid") as error:
        load_settings()
    assert value not in str(error.value)


class _ExporterRecorder:
    """Stands in for the OTLP exporters and records each one made."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.endpoints: list[str] = []
        for name in ("OTLPSpanExporter", "OTLPMetricExporter", "OTLPLogExporter"):
            real = getattr(telemetry_module, name)
            monkeypatch.setattr(telemetry_module, name, self._recording(real))

    def _recording(self, real):
        recorder = self

        def make(*, endpoint: str, timeout: float):
            recorder.endpoints.append(endpoint)
            assert timeout <= 5
            return real(endpoint=endpoint, timeout=timeout)

        return make


@pytest.fixture
def no_connections(monkeypatch: pytest.MonkeyPatch) -> list:
    """Records every outgoing socket connection the code tries to open."""
    attempts: list = []
    real_connect = socket.socket.connect

    def connect(self, address):
        attempts.append(address)
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    return attempts


def test_without_an_endpoint_nothing_is_exported_or_connected(
    settings, monkeypatch, no_connections, capsys
):
    recorder = _ExporterRecorder(monkeypatch)
    app = create_app(settings)
    app.dependency_overrides[check_database] = lambda: True
    capsys.readouterr()

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert recorder.endpoints == []
    assert no_connections == []
    [line] = _finished_lines(capsys.readouterr().out)
    assert TRACE_ID.fullmatch(line["trace_id"])
    assert SPAN_ID.fullmatch(line["span_id"])


def test_with_an_endpoint_export_starts_only_with_the_app(settings, monkeypatch):
    recorder = _ExporterRecorder(monkeypatch)
    settings = settings.model_copy(update={"otel_exporter_otlp_endpoint": "http://collector:4318/"})
    app = create_app(settings)
    app.dependency_overrides[check_database] = lambda: True

    # Built, and even used, without its lifespan (as tests do): no exporter exists.
    assert TestClient(app).get("/health").status_code == 200
    assert recorder.endpoints == []

    telemetry = Telemetry.from_settings(settings)
    telemetry.start()
    telemetry.start()
    assert sorted(recorder.endpoints) == [
        "http://collector:4318/v1/logs",
        "http://collector:4318/v1/metrics",
        "http://collector:4318/v1/traces",
    ]
    telemetry.shutdown()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_with_an_endpoint_and_nothing_listening_requests_work_and_shutdown_is_quick(settings):
    endpoint = f"http://127.0.0.1:{_free_port()}"
    settings = settings.model_copy(update={"otel_exporter_otlp_endpoint": endpoint})
    app = create_app(settings)
    app.dependency_overrides[check_database] = lambda: True

    with TestClient(app) as client:
        for _ in range(5):
            started = time.monotonic()
            assert client.get("/health").status_code == 200
            assert time.monotonic() - started < 1
        stopping = time.monotonic()

    assert time.monotonic() - stopping < 10
