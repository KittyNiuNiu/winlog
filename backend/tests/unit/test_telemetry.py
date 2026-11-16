"""Telemetry for every request and the privacy allowlist (issue #74), without a database.

The summary journey itself is tested against PostgreSQL in
tests/integration/test_telemetry.py. Every test captures telemetry with in-memory exporters;
none needs a collector.
"""

import logging
import re
import socket
import time
import uuid

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util.re import parse_env_headers

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
from tests.whole_number_settings import (
    assert_range_applies_in_code,
    assert_stops_at_startup,
    refused_values,
    value_id,
)

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


def test_resource_holds_only_the_service_environment_and_sdk_attributes(api, captured):
    api.get("/health")

    [server] = captured.server_spans()
    assert set(server.resource.attributes) == ALLOWED_RESOURCE_KEYS
    assert server.resource.attributes["service.name"] == "winlog-backend"
    assert server.resource.attributes["deployment.environment.name"] == "local"
    # A new id on every start would make new metric series on every wake (issue #92).
    assert "service.instance.id" not in server.resource.attributes
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


class _NullMetricExporter(MetricExporter):
    """A metric exporter that sends nothing anywhere."""

    def export(self, metrics_data, timeout_millis: float = 10_000, **kwargs) -> MetricExportResult:
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


class _ExporterRecorder:
    """Stands in for the OTLP exporters and records what each one is made with.

    Each real exporter is made with the same arguments too, which checks them against its
    signature and opens no connection, and is shut down at once. The app gets an in-memory
    stand-in instead, so nothing is ever sent. The metric reader's interval is recorded as well.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # (signal path, endpoint, headers), in the order made.
        self.made: list[tuple[str, str, dict[str, str] | None]] = []
        self.metric_export_intervals: list[int] = []
        for name, stand_in in (
            ("OTLPSpanExporter", InMemorySpanExporter),
            ("OTLPMetricExporter", _NullMetricExporter),
            ("OTLPLogExporter", InMemoryLogRecordExporter),
        ):
            real = getattr(telemetry_module, name)
            monkeypatch.setattr(telemetry_module, name, self._recording(real, stand_in))
        real_reader = telemetry_module.PeriodicExportingMetricReader

        def reader(exporter, *, export_interval_millis: int, export_timeout_millis: int):
            self.metric_export_intervals.append(export_interval_millis)
            return real_reader(
                exporter,
                export_interval_millis=export_interval_millis,
                export_timeout_millis=export_timeout_millis,
            )

        monkeypatch.setattr(telemetry_module, "PeriodicExportingMetricReader", reader)

    @property
    def endpoints(self) -> list[str]:
        return [endpoint for _, endpoint, _ in self.made]

    def _recording(self, real, stand_in):
        recorder = self

        def make(*, endpoint: str, timeout: float, headers: dict[str, str] | None = None):
            recorder.made.append((endpoint.rsplit("/", 1)[-1], endpoint, headers))
            assert timeout <= 5
            real(endpoint=endpoint, timeout=timeout, headers=headers).shutdown()
            return stand_in()

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


# --- Hosted telemetry: headers, environment, metric interval (issue #92) -----------------------

# Clearly fake values: never a real instance ID or token.
HOSTED_ENDPOINT = "https://otlp-gateway.example.invalid/otlp"
FAKE_CREDENTIALS = "ZmFrZS1pbnN0YW5jZTpmYWtlLXRva2Vu"  # base64 of "fake-instance:fake-token"


def _marker() -> str:
    return f"m92hdr{uuid.uuid4().hex[:12]}"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_otlp_headers_empty_or_not_set_send_no_header(base_env, monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", value)

    settings = load_settings()

    assert settings.otel_exporter_otlp_headers is None
    assert settings.otlp_headers() == {}
    assert Telemetry.from_settings(settings)._otlp_headers == {}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Grafana Cloud's form, URL-encoded, with base64 padding.
        (
            f"Authorization=Basic%20{FAKE_CREDENTIALS}==",
            {"authorization": f"Basic {FAKE_CREDENTIALS}=="},
        ),
        # A literal space after Basic, which the SDK accepts too.
        (f"Authorization=Basic {FAKE_CREDENTIALS}", {"authorization": f"Basic {FAKE_CREDENTIALS}"}),
        (" a = 1 , X-Scope-OrgID=fake%2Dtenant ,", {"a": "1", "x-scope-orgid": "fake-tenant"}),
    ],
)
def test_otlp_headers_are_read_as_the_sdk_reads_them(
    base_env, monkeypatch, caplog, value, expected
):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", HOSTED_ENDPOINT)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", value)
    caplog.set_level(logging.DEBUG)

    assert load_settings().otlp_headers() == expected
    # The same as the OTLP/HTTP exporters' own reading, which logs nothing for these values.
    assert dict(parse_env_headers(value, liberal=True)) == expected
    assert caplog.records == []


def test_otlp_headers_from_the_env_file_are_read(no_env_file, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://winlog:placeholder@localhost:5432/winlog\n"
        f"CORS_ALLOWED_ORIGINS={ALLOWED_ORIGIN}\n"
        "AI_PROVIDER=mock\n"
        f"OTEL_EXPORTER_OTLP_ENDPOINT={HOSTED_ENDPOINT}\n"
        f"OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20{FAKE_CREDENTIALS}\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    settings = load_settings()

    assert settings.otlp_headers() == {"authorization": f"Basic {FAKE_CREDENTIALS}"}


def test_otlp_headers_are_a_secret(base_env, monkeypatch, caplog):
    marker = _marker()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", HOSTED_ENDPOINT)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic%20{marker}")
    settings = load_settings()

    logging.getLogger("test").warning("settings: %s / %r", settings, settings)

    assert marker not in str(settings)
    assert marker not in repr(settings)
    assert marker not in caplog.text
    assert marker not in repr(Telemetry.from_settings(settings))


@pytest.mark.parametrize(
    "template",
    [
        "Authorization:Basic {}",
        "Authorization Basic {}",
        "=Basic%20{}",
        "Author ization=Basic%20{}",
        "Authorization=Basic%20{},{}",
        "Authorization=Basic%0A{}",
        'Authorization="Basic {}"',
        "Authorization=Basic%20{};x",
    ],
)
def test_malformed_otlp_headers_stop_the_app_without_showing_the_value(
    base_env, monkeypatch, capsys, caplog, template
):
    marker = _marker()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", HOSTED_ENDPOINT)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", template.format(marker, marker))
    caplog.set_level(logging.DEBUG)

    with pytest.raises(SettingsError) as error:
        create_app()

    message = str(error.value)
    assert "OTEL_EXPORTER_OTLP_HEADERS is invalid: " in message
    assert "name=value pairs" in message
    assert marker not in message
    printed = capsys.readouterr()
    assert marker not in printed.out
    assert marker not in printed.err
    assert marker not in caplog.text
    assert all(marker not in str(record.args) for record in caplog.records)


def test_otlp_headers_with_an_http_endpoint_stop_the_app(base_env, monkeypatch, capsys, caplog):
    marker = _marker()
    endpoint = "http://collector.example.invalid:4318"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic%20{marker}")
    caplog.set_level(logging.DEBUG)

    with pytest.raises(SettingsError) as error:
        create_app()

    message = str(error.value)
    assert "OTEL_EXPORTER_OTLP_HEADERS is invalid: " in message
    assert "https:// OTEL_EXPORTER_OTLP_ENDPOINT" in message
    assert marker not in message
    assert endpoint not in message
    printed = capsys.readouterr()
    assert marker not in printed.out + printed.err
    assert marker not in caplog.text


def test_otlp_headers_without_an_endpoint_export_nothing_and_print_nothing(
    base_env, monkeypatch, no_connections, capsys, caplog
):
    marker = _marker()
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic%20{marker}")
    recorder = _ExporterRecorder(monkeypatch)
    caplog.set_level(logging.DEBUG)
    app = create_app()
    app.dependency_overrides[check_database] = lambda: True
    capsys.readouterr()

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    assert app.state.settings.otel_exporter_otlp_endpoint is None
    assert recorder.made == []
    assert no_connections == []
    printed = capsys.readouterr()
    for text in (printed.out, printed.err, caplog.text):
        assert marker not in text
        assert "OTEL_EXPORTER_OTLP_HEADERS" not in text
        assert "header" not in text.lower()


def test_hosted_export_sends_the_headers_to_all_three_exporters(monkeypatch, no_connections):
    recorder = _ExporterRecorder(monkeypatch)
    settings = Settings(
        _env_file=None,
        database_url="postgresql://winlog:placeholder@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        otel_exporter_otlp_endpoint=HOSTED_ENDPOINT,
        otel_exporter_otlp_headers=f"Authorization=Basic%20{FAKE_CREDENTIALS},X-Second=two",
        otel_metric_export_interval=60_000,
    )
    expected = {"authorization": f"Basic {FAKE_CREDENTIALS}", "x-second": "two"}

    telemetry = Telemetry.from_settings(settings)
    telemetry.start()

    assert sorted(recorder.made) == [
        ("logs", f"{HOSTED_ENDPOINT}/v1/logs", expected),
        ("metrics", f"{HOSTED_ENDPOINT}/v1/metrics", expected),
        ("traces", f"{HOSTED_ENDPOINT}/v1/traces", expected),
    ]
    assert recorder.metric_export_intervals == [60_000]
    telemetry.shutdown()
    assert no_connections == []


def test_metric_export_interval_defaults_to_ten_seconds(base_env, monkeypatch):
    recorder = _ExporterRecorder(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", HOSTED_ENDPOINT)
    settings = load_settings()

    assert settings.otel_metric_export_interval == 10_000
    telemetry = Telemetry.from_settings(settings)
    telemetry.start()
    assert recorder.metric_export_intervals == [10_000]
    assert [headers for _, _, headers in recorder.made] == [{}, {}, {}]
    telemetry.shutdown()


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1000", 1_000), ("300000", 300_000), (" 60000 ", 60_000), ("060000", 60_000)],
)
def test_metric_export_interval_takes_a_whole_number_from_1000_to_300000(
    base_env, monkeypatch, value, expected
):
    monkeypatch.setenv("OTEL_METRIC_EXPORT_INTERVAL", value)

    assert load_settings().otel_metric_export_interval == expected


@pytest.mark.parametrize("value", refused_values(1_000, 300_000), ids=value_id)
def test_metric_export_interval_stops_the_app_when_invalid(base_env, monkeypatch, value):
    assert_stops_at_startup(monkeypatch, "OTEL_METRIC_EXPORT_INTERVAL", value, 1_000, 300_000)


def test_metric_export_interval_range_applies_in_code(no_env_file):
    assert_range_applies_in_code(
        "otel_metric_export_interval",
        1_000,
        300_000,
        database_url="postgresql://winlog:placeholder@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "local"),
        ("", "local"),
        ("  ", "local"),
        ("dev", "dev"),
        (" production ", "production"),
    ],
)
def test_telemetry_environment_marks_the_resource(base_env, monkeypatch, value, expected):
    if value is not None:
        monkeypatch.setenv("TELEMETRY_ENVIRONMENT", value)

    settings = load_settings()

    assert settings.telemetry_environment == expected
    resource = Telemetry.from_settings(settings).tracer_provider.resource
    assert dict(resource.attributes) == {
        "service.name": "winlog-backend",
        "service.version": telemetry_module.SERVICE_VERSION,
        "deployment.environment.name": expected,
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
        "telemetry.sdk.version": resource.attributes["telemetry.sdk.version"],
    }
    assert set(resource.attributes) == ALLOWED_RESOURCE_KEYS


@pytest.mark.parametrize("value", ["staging", "Dev", "prod", "local,dev"])
def test_telemetry_environment_stops_the_app_when_invalid(base_env, monkeypatch, value):
    monkeypatch.setenv("TELEMETRY_ENVIRONMENT", value)

    with pytest.raises(SettingsError) as error:
        create_app()

    message = str(error.value)
    assert "TELEMETRY_ENVIRONMENT is invalid: " in message
    assert "must be one of local, dev, production" in message
