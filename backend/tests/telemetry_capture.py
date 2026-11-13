"""In-memory telemetry for tests (issue #74). Tests never need a running collector.

`CapturedTelemetry` builds an `app.telemetry.Telemetry` whose spans, metrics and log records
go to in-memory exporters, and reads them back. Pass `captured.telemetry` to `create_app`.
"""

import json
from collections.abc import Iterator

from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, Metric
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.telemetry import Telemetry


class CapturedTelemetry:
    def __init__(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        self.metric_reader = InMemoryMetricReader()
        self.log_exporter = InMemoryLogRecordExporter()
        self.telemetry = Telemetry(
            span_exporter=self.span_exporter,
            metric_reader=self.metric_reader,
            log_exporter=self.log_exporter,
        )

    # --- Spans ---

    def spans(self) -> list[ReadableSpan]:
        """The finished spans, in the order they started."""
        return sorted(self.span_exporter.get_finished_spans(), key=lambda span: span.start_time)

    def server_spans(self) -> list[ReadableSpan]:
        return [span for span in self.spans() if span.parent is None]

    def span(self, name: str) -> ReadableSpan:
        """The only finished span with this name."""
        matching = [span for span in self.spans() if span.name == name]
        assert len(matching) == 1, f"expected one span {name!r}, got {len(matching)}"
        return matching[0]

    def trace(self, server_span: ReadableSpan) -> list[ReadableSpan]:
        """The spans of the server span's trace, in the order they started."""
        trace_id = server_span.context.trace_id
        return [span for span in self.spans() if span.context.trace_id == trace_id]

    # --- Metrics ---

    def metrics(self) -> list[Metric]:
        data = self.metric_reader.get_metrics_data()
        if data is None:
            return []
        return [
            metric
            for resource_metrics in data.resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        ]

    def metric(self, name: str) -> Metric:
        matching = [metric for metric in self.metrics() if metric.name == name]
        assert len(matching) == 1, f"expected one metric {name!r}, got {len(matching)}"
        return matching[0]

    def points(self, name: str) -> list:
        return list(self.metric(name).data.data_points)

    # --- Logs ---

    def logs(self) -> list[ReadableLogRecord]:
        return list(self.log_exporter.get_finished_logs())

    def logs_of_trace(self, trace_id: int) -> list[ReadableLogRecord]:
        return [log for log in self.logs() if log.log_record.trace_id == trace_id]

    # --- Everything, for the privacy checks ---

    def everything_as_text(self) -> str:
        """Every exported span, metric and log record, with resources, as one JSON text."""
        parts = [span.to_json() for span in self.span_exporter.get_finished_spans()]
        data = self.metric_reader.get_metrics_data()
        if data is not None:
            parts.append(data.to_json())
        parts.extend(log.to_json() for log in self.log_exporter.get_finished_logs())
        return "\n".join(parts)

    def attribute_keys(self) -> Iterator[tuple[str, str]]:
        """(where, key) for every attribute key of every exported signal."""
        for span in self.span_exporter.get_finished_spans():
            for key in span.attributes or {}:
                yield f"span {span.name}", key
            for event in span.events:
                yield f"span event {event.name}", "<event>"
            for key in span.resource.attributes:
                yield "resource", key
        for metric in self.metrics():
            for point in metric.data.data_points:
                for key in point.attributes or {}:
                    yield f"metric {metric.name}", key
        for log in self.logs():
            for key in log.log_record.attributes or {}:
                yield f"log {log.log_record.body}", key
            for key in log.resource.attributes:
                yield "resource", key


def json_lines(output: str) -> list[dict]:
    """The JSON log lines in captured stdout. Every non-empty line must be one JSON object."""
    lines = [line for line in output.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]
