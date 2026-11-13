"""Telemetry: traces, metrics and structured logs with OpenTelemetry (issue #74).

All telemetry setup lives in this module, and so does the privacy allowlist
(`docs/observability.md`). Every request gets a SERVER span, an `http.server.request.duration`
measurement and a `request finished` log line. The key user journey, generating a summary
(FR-R3), adds child spans, an outcome counter and the AI duration histogram. Spans, metrics
and log records of one request share its trace ID.

Export: with `OTEL_EXPORTER_OTLP_ENDPOINT` set, the signals go over OTLP/HTTP to a collector
(the `lgtm` service in Docker Compose). The exporters are created only when the app starts
(its lifespan) and are flushed and shut down when it stops. So importing `app.main`, or a
test client that does not run the lifespan, never opens a connection. Empty or not set, nothing
is exported; the JSON log lines on stdout still carry `trace_id` and `span_id`. Tests pass
in-memory exporters to `Telemetry` instead, and never need a collector.

Each app has its own providers. None of them is set as OpenTelemetry's global provider, which
can be set only once per process, so `create_app` can run any number of times. The middleware
makes the app's `Telemetry` current for the request through a context variable; FastAPI copies
it into the thread pool that runs sync endpoints.

Privacy (allowlist): telemetry holds only the keys in `ALLOWED_ATTRIBUTE_KEYS`, the resource
attributes in `ALLOWED_RESOURCE_KEYS`, span and metric names, fixed log messages, and trace and
span IDs. Never entry text, Result/Impact, tag names, summary text, AI request or response
content, passwords, tokens, email addresses, user, entry or summary ids, IP addresses, user
agents, query strings, request or response bodies, exception messages or stack traces. How:

- Only the `app` loggers are printed as JSON and exported. Third-party loggers (httpx, openai,
  SQLAlchemy, uvicorn) never reach telemetry.
- `_TelemetryLogHandler` keeps only the allowlisted `extra` fields of a record, drops
  `exc_info` and `stack_info`, and keeps only the exception's class name as `error.type`.
- Spans are started with `record_exception=False` and `set_status_on_exception=False`, because
  the SDK's defaults add the exception message and stack trace. A span's status description is
  at most the exception's class name.
- Span and metric attributes go through `_allowed`, which drops any key not on the allowlist.
- No auto-instrumentation: it records full URLs, client addresses, SQL and exception messages.
- Incoming `traceparent`, `tracestate` and `baggage` headers are ignored: every request starts
  a new trace, so a client can neither choose the trace ID nor add data to the trace.
- Uvicorn's access log, which writes query strings and client addresses, is turned off.
"""

import datetime as dt
import json
import logging
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry._logs import SeverityNumber
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    LogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.sdk.version import __version__ as SDK_VERSION
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.settings import Settings

SERVICE_NAME = "winlog-backend"
SERVICE_VERSION = "0.1.0"
INSTRUMENTATION_SCOPE = "app"

# Fixed for the local stack (issue #74, decision 7).
METRIC_EXPORT_INTERVAL_MILLIS = 10_000
# Short, so a missing or slow collector cannot hold up a request or the shutdown. Each export
# waits at most this long, retries included.
EXPORT_TIMEOUT_SECONDS = 2

# --- Privacy allowlist (docs/observability.md) ---------------------------------------------

ALLOWED_RESOURCE_KEYS = frozenset(
    {
        "service.name",
        "service.version",
        "telemetry.sdk.language",
        "telemetry.sdk.name",
        "telemetry.sdk.version",
    }
)

ALLOWED_ATTRIBUTE_KEYS = frozenset(
    {
        "http.request.method",
        "http.route",
        "http.response.status_code",
        "error.type",
        "winlog.outcome",
        "winlog.entry_count",
        "winlog.ai.operation",
        "winlog.ai.provider",
        "winlog.ai.outcome",
        "duration_ms",
    }
)
"""The only attribute keys of spans, metrics and log records (and log fields on stdout)."""

# The keys every JSON log line on stdout has, besides the allowlisted fields.
LOG_LINE_KEYS = ("timestamp", "level", "logger", "message", "trace_id", "span_id")

SummaryOutcome = Literal[
    "created",
    "no_matching_entries",
    "summary_input_too_large",
    "limit_reached",
    "ai_unavailable",
]
AIOutcome = Literal["success", "timeout", "provider_error"]

# HTTP methods recorded as they are; any other is recorded as `_OTHER` (OTel semantic
# conventions), so a client cannot put its own text into telemetry through the method.
_KNOWN_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}
)

# Bucket boundaries in seconds: OTel's recommendation for HTTP durations, up to the longest AI
# timeout (600 s) for the AI calls.
_HTTP_DURATION_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10,
)  # fmt: skip
_AI_DURATION_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300, 600,
)  # fmt: skip

_APP_LOGGER = "app"
logger = logging.getLogger(__name__)


def _allowed(attributes: Mapping[str, object]) -> dict[str, str | int | float | bool]:
    """Only the allowlisted keys with plain values; everything else is dropped."""
    return {
        key: value
        for key, value in attributes.items()
        if key in ALLOWED_ATTRIBUTE_KEYS and isinstance(value, str | int | float | bool)
    }


def _resource() -> Resource:
    """The service's resource. Built by hand: no environment, host or process detectors."""
    return Resource(
        {
            "service.name": SERVICE_NAME,
            "service.version": SERVICE_VERSION,
            "telemetry.sdk.language": "python",
            "telemetry.sdk.name": "opentelemetry",
            "telemetry.sdk.version": SDK_VERSION,
        }
    )


class _Metrics:
    """A meter provider and the three instruments made from it."""

    def __init__(self, meter_provider: MeterProvider) -> None:
        self.meter_provider = meter_provider
        meter = meter_provider.get_meter(INSTRUMENTATION_SCOPE)
        self.http_duration = meter.create_histogram(
            "http.server.request.duration",
            unit="s",
            description="Duration of HTTP server requests.",
            explicit_bucket_boundaries_advisory=_HTTP_DURATION_BUCKETS,
        )
        self.summary_requests = meter.create_counter(
            "winlog.summary.generate.requests",
            unit="{request}",
            description="Summary generation requests, by outcome.",
        )
        self.ai_duration = meter.create_histogram(
            "winlog.ai.request.duration",
            unit="s",
            description="Duration of AI provider calls.",
            explicit_bucket_boundaries_advisory=_AI_DURATION_BUCKETS,
        )


class Telemetry:
    """One app's tracer, meter and logger providers, and its instruments.

    `otlp_endpoint` turns on the OTLP/HTTP export, which `start` sets up. The exporters given
    here (tests use in-memory ones) receive the signals synchronously from the start.
    """

    def __init__(
        self,
        *,
        otlp_endpoint: str | None = None,
        span_exporter: SpanExporter | None = None,
        metric_reader: MetricReader | None = None,
        log_exporter: LogRecordExporter | None = None,
    ) -> None:
        self.otlp_endpoint = otlp_endpoint
        self._started = False
        self._resource = _resource()
        self.tracer_provider = TracerProvider(
            sampler=ALWAYS_ON, resource=self._resource, shutdown_on_exit=False
        )
        if span_exporter is not None:
            self.tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        self.logger_provider = LoggerProvider(resource=self._resource, shutdown_on_exit=False)
        if log_exporter is not None:
            self.logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
        self._metrics = self._build_metrics([metric_reader] if metric_reader is not None else [])
        self.tracer = self.tracer_provider.get_tracer(INSTRUMENTATION_SCOPE)

    @classmethod
    def from_settings(cls, settings: Settings) -> "Telemetry":
        return cls(otlp_endpoint=settings.otel_exporter_otlp_endpoint)

    def _build_metrics(self, readers: Sequence[MetricReader]) -> _Metrics:
        return _Metrics(
            MeterProvider(
                metric_readers=list(readers), resource=self._resource, shutdown_on_exit=False
            )
        )

    @property
    def meter_provider(self) -> MeterProvider:
        return self._metrics.meter_provider

    def start(self) -> None:
        """Start the OTLP export, if an endpoint is set. Called once, when the app starts."""
        if self.otlp_endpoint is None or self._started:
            return
        self._started = True
        base = self.otlp_endpoint.rstrip("/")
        # An endpoint passed in code is the full URL: the signal path is not added for us.
        self.tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=f"{base}/v1/traces", timeout=EXPORT_TIMEOUT_SECONDS)
            )
        )
        self.logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=f"{base}/v1/logs", timeout=EXPORT_TIMEOUT_SECONDS)
            )
        )
        # A MeterProvider takes its readers only when it is made, so the meter provider and
        # its instruments are made again, with the exporting reader. No request has run yet.
        old = self._metrics
        self._metrics = self._build_metrics(
            [
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=f"{base}/v1/metrics", timeout=EXPORT_TIMEOUT_SECONDS
                    ),
                    export_interval_millis=METRIC_EXPORT_INTERVAL_MILLIS,
                    export_timeout_millis=EXPORT_TIMEOUT_SECONDS * 1000,
                )
            ]
        )
        old.meter_provider.shutdown()

    def shutdown(self) -> None:
        """Flush and stop the export. Called when the app stops."""
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
        self.logger_provider.shutdown()

    @contextmanager
    def activate(self) -> Iterator[None]:
        """Make this the current telemetry, outside a request (the middleware does it inside)."""
        token = _current.set(_RequestTelemetry(self))
        try:
            yield
        finally:
            _current.reset(token)

    def _emit_log(self, record: logging.LogRecord, message: str, fields: dict) -> None:
        self.logger_provider.get_logger(record.name).emit(
            timestamp=round(record.created * 1e9),
            context=otel_context.get_current(),
            severity_number=_severity(record.levelno),
            severity_text=record.levelname,
            body=message,
            attributes=fields,
        )


@dataclass(slots=True)
class _RequestTelemetry:
    telemetry: Telemetry
    server_span: Span | None = None


_current: ContextVar[_RequestTelemetry | None] = ContextVar("winlog_telemetry", default=None)


def _current_telemetry() -> Telemetry | None:
    state = _current.get()
    return state.telemetry if state is not None else None


# --- Spans ----------------------------------------------------------------------------------


class SpanHandle:
    """A span that accepts only allowlisted attributes."""

    def __init__(self, span: Span) -> None:
        self._span = span

    def set(self, key: str, value: str | int | float | bool) -> None:
        self._span.set_attributes(_allowed({key: value}))


@contextmanager
def span(name: str, attributes: Mapping[str, object] | None = None) -> Iterator[SpanHandle]:
    """An INTERNAL span under the current one, in the current app's telemetry.

    An exception inside sets status Error with only the exception's class name: no exception
    event, no message, no stack trace. Outside a request it does nothing.
    """
    telemetry = _current_telemetry()
    tracer = telemetry.tracer if telemetry is not None else trace.NoOpTracer()
    with tracer.start_as_current_span(
        name,
        kind=SpanKind.INTERNAL,
        attributes=_allowed(attributes or {}),
        record_exception=False,
        set_status_on_exception=False,
    ) as current:
        try:
            yield SpanHandle(current)
        except Exception as error:
            current.set_status(Status(StatusCode.ERROR, type(error).__name__))
            raise


# --- Journey helpers --------------------------------------------------------------------------


def record_ai_call(
    operation: str, provider: str, outcome: AIOutcome, duration_seconds: float
) -> None:
    """Record one AI provider call in `winlog.ai.request.duration`."""
    telemetry = _current_telemetry()
    if telemetry is None:
        return
    telemetry._metrics.ai_duration.record(
        duration_seconds,
        _allowed(
            {
                "winlog.ai.operation": operation,
                "winlog.ai.provider": provider,
                "winlog.ai.outcome": outcome,
            }
        ),
    )


def summary_generation_finished(outcome: SummaryOutcome, entry_count: int | None) -> None:
    """Record the outcome of one summary generation (FR-R3).

    Counts it in `winlog.summary.generate.requests`, sets `winlog.outcome` on the request's
    SERVER span and logs `summary generation finished`.
    """
    fields: dict[str, object] = {"winlog.outcome": outcome}
    if entry_count is not None:
        fields["winlog.entry_count"] = entry_count
    state = _current.get()
    if state is not None:
        state.telemetry._metrics.summary_requests.add(1, _allowed({"winlog.outcome": outcome}))
        if state.server_span is not None:
            state.server_span.set_attribute("winlog.outcome", outcome)
    logger.info("summary generation finished", extra=fields)


# --- Every request ----------------------------------------------------------------------------


class TelemetryMiddleware:
    """One SERVER span, one duration measurement and one `request finished` line per request.

    Add it last, so it is the outermost middleware and sees every response, including the
    shared 500 response. The span is named `{METHOD} {route template}` (never the actual path),
    or just the method when no route matches. Incoming trace headers are ignored.
    """

    def __init__(self, app: ASGIApp, telemetry: Telemetry) -> None:
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        telemetry = self.telemetry
        method = scope["method"] if scope["method"] in _KNOWN_METHODS else "_OTHER"
        status_code: int | None = None

        async def send_and_track_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        state = _RequestTelemetry(telemetry)
        token = _current.set(state)
        started = time.perf_counter()
        try:
            # An empty context: the span is the root of a new trace, whatever the client sent.
            with telemetry.tracer.start_as_current_span(
                method,
                context=otel_context.Context(),
                kind=SpanKind.SERVER,
                attributes={"http.request.method": method},
                record_exception=False,
                set_status_on_exception=False,
            ) as server_span:
                state.server_span = server_span
                error_type: str | None = None
                try:
                    await self.app(scope, receive, send_and_track_status)
                except Exception as error:
                    error_type = type(error).__name__
                    raise
                finally:
                    _finish_request(
                        telemetry,
                        server_span,
                        scope,
                        method,
                        status_code,
                        error_type,
                        time.perf_counter() - started,
                    )
        finally:
            _current.reset(token)


def _route_template(scope: Scope) -> str | None:
    """The matched route's template, such as `/entries/{entryId}`, or None."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else None


def _finish_request(
    telemetry: Telemetry,
    server_span: Span,
    scope: Scope,
    method: str,
    status_code: int | None,
    error_type: str | None,
    duration_seconds: float,
) -> None:
    route = _route_template(scope)
    server_span.update_name(f"{method} {route}" if route else method)
    attributes: dict[str, object] = {"http.request.method": method}
    if route:
        attributes["http.route"] = route
    if status_code is not None:
        attributes["http.response.status_code"] = status_code
    is_server_error = error_type is not None or (status_code is not None and status_code >= 500)
    if is_server_error and error_type is None:
        # No exception reached this point: the status code is the error type (OTel convention).
        error_type = str(status_code)
    server_span.set_attributes(_allowed(attributes))
    if is_server_error:
        server_span.set_attribute("error.type", error_type)
        server_span.set_status(Status(StatusCode.ERROR))
    telemetry._metrics.http_duration.record(duration_seconds, _allowed(attributes))
    fields = {**attributes, "duration_ms": round(duration_seconds * 1000)}
    if is_server_error:
        fields["error.type"] = error_type
    logger.log(logging.ERROR if is_server_error else logging.INFO, "request finished", extra=fields)


# --- Logs -------------------------------------------------------------------------------------


def _severity(level: int) -> SeverityNumber:
    if level >= logging.CRITICAL:
        return SeverityNumber.FATAL
    if level >= logging.ERROR:
        return SeverityNumber.ERROR
    if level >= logging.WARNING:
        return SeverityNumber.WARN
    if level >= logging.INFO:
        return SeverityNumber.INFO
    return SeverityNumber.DEBUG


def log_fields(record: logging.LogRecord) -> dict[str, str | int | float | bool]:
    """A record's allowlisted `extra` fields, plus `error.type` from its exception, if any."""
    present = vars(record)
    fields = _allowed({key: present[key] for key in ALLOWED_ATTRIBUTE_KEYS if key in present})
    if record.exc_info and record.exc_info[1] is not None:
        fields["error.type"] = type(record.exc_info[1]).__name__
    return fields


class _TelemetryLogHandler(logging.Handler):
    """Prints each `app` log record as one JSON line on stdout and exports it.

    Only allowlisted fields are kept. The exception and stack (`exc_info`, `stack_info`) are
    never printed or exported; only the exception's class name is kept, as `error.type`.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            fields = log_fields(record)
            line: dict[str, object] = {
                "timestamp": dt.datetime.fromtimestamp(record.created, dt.UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
            }
            span_context = trace.get_current_span().get_span_context()
            if span_context.is_valid:
                line["trace_id"] = trace.format_trace_id(span_context.trace_id)
                line["span_id"] = trace.format_span_id(span_context.span_id)
            line.update(fields)
            sys.stdout.write(json.dumps(line, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            telemetry = _current_telemetry()
            if telemetry is not None:
                telemetry._emit_log(record, message, fields)
        except Exception:
            self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802 (logging's name)
        # logging's default prints the record's arguments, which this module never does.
        if logging.raiseExceptions:
            sys.stderr.write("A log record could not be written.\n")


def configure_logging() -> None:
    """Set up the `app` loggers and turn off uvicorn's access log. Safe to call many times.

    Uvicorn configures its logging before it imports the app, so turning its access log off
    here works however the backend is started (the `AGENTS.md` dev command, the Docker image).
    The `request finished` line replaces it.
    """
    app_logger = logging.getLogger(_APP_LOGGER)
    if not any(isinstance(handler, _TelemetryLogHandler) for handler in app_logger.handlers):
        app_logger.addHandler(_TelemetryLogHandler())
    app_logger.setLevel(logging.INFO)
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
