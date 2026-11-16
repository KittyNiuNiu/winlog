# Observability

Winlog's backend sends traces, metrics and structured logs with OpenTelemetry (issue #74).
One key user journey is instrumented in detail: **generating a summary** (`POST /summaries`,
FR-R3). The spans, metrics and log records of a request share one trace ID. Every other
request also gets a SERVER span, an HTTP duration measurement and a `request finished` log
line.

Locally, Docker Compose runs Grafana's all-in-one `grafana/otel-lgtm:0.39.0` image as the
`lgtm` service. It contains the OpenTelemetry Collector, Prometheus (metrics), Tempo (traces),
Loki (logs) and Grafana (the UI). The data is kept in the `lgtm-data` volume, so it survives
`docker compose restart lgtm`. `docker compose down -v` deletes it.

Deployed environments send no telemetry yet: they leave `OTEL_EXPORTER_OTLP_ENDPOINT` empty and
only print the JSON logs. Hosted telemetry is planned in #92.

All telemetry setup is in `backend/app/telemetry.py`, which also holds the allowlist below.

## Open Grafana

1. Start the full system in the repository root: `docker compose up --build`.
2. Generate a summary in the app (http://localhost:8080 → Review).
3. Open http://localhost:3000. There is no login and no sign-up.

Local Grafana has anonymous access. Its ports are therefore published on **127.0.0.1 only**
(`GRAFANA_HOST_PORT`, default 3000, and the OTLP/HTTP port `OTLP_HTTP_HOST_PORT`, default
4318), so other computers on your network cannot reach them. Do not publish them on other
addresses.

Use **Explore** (compass icon) and choose a data source. There are no custom dashboards.

### The trace (Tempo)

- Data source **Tempo**, query type **Search**: service name `winlog-backend`, span name
  `POST /summaries`. Or use TraceQL:
  `{resource.service.name="winlog-backend" && name="POST /summaries"}`.
- Open a trace. A successful summary has the SERVER span `POST /summaries` with four child
  spans, in this order: `summary.select_entries`, `ai.limits.reserve`, `ai.summarise` and
  `summary.save`.
- Copy the trace ID for the logs.

### The logs (Loki)

- Data source **Loki**, query:
  `{service_name="winlog-backend"} | trace_id="<trace ID>"`.
- For a summary you see the AI adapter's line (`AI summarise with provider mock succeeded …`),
  `summary generation finished` with `winlog.outcome`, and `request finished`.
- Without the filter, `{service_name="winlog-backend"}` shows every request's
  `request finished` line.

### The metrics (Prometheus)

Data source **Prometheus**. Prometheus turns the OTel names into these names:

| Query | What it shows |
|---|---|
| `winlog_summary_generate_requests_total` | Summary generations by `winlog_outcome` |
| `winlog_ai_request_duration_seconds_bucket` (also `_count`, `_sum`) | AI call durations by `winlog_ai_operation`, `winlog_ai_provider` and `winlog_ai_outcome` |
| `http_server_request_duration_seconds_bucket` (also `_count`, `_sum`) | HTTP request durations by `http_request_method`, `http_route` and `http_response_status_code` |

Metrics are exported every 10 seconds, so a new measurement can take that long to appear.

### Over the HTTP API

Grafana's data source proxy answers without a login, which is how CI checks the stack:

```sh
G=http://127.0.0.1:3000/api/datasources/proxy/uid
curl "$G/tempo/api/traces/<trace ID>"
curl -G "$G/loki/loki/api/v1/query_range" \
  --data-urlencode 'query={service_name="winlog-backend"} | trace_id="<trace ID>"'
curl -G "$G/prometheus/api/v1/query" \
  --data-urlencode 'query=winlog_summary_generate_requests_total'
```

## Run the backend on your computer against the stack

1. In the repository root: `docker compose up -d db lgtm`.
2. In `.env`, set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` (the port is
   `OTLP_HTTP_HOST_PORT`).
3. In `backend/`: `uv run alembic upgrade head`, then `uv run uvicorn app.main:app --reload`.

The endpoint is the collector's base URL; the backend adds `/v1/traces`, `/v1/metrics` and
`/v1/logs`. It exports only while the app runs (its lifespan). Empty or not set, nothing is
exported and no connection is opened, but the JSON log lines still carry `trace_id` and
`span_id`.

The backend works the same when no collector is running. Requests never wait for the export.
The exporter may print warnings such as `Failed to export … batch` on stderr. Each export
gives up after 2 seconds, so the backend still stops within a few seconds.

The tests never need a collector. They capture telemetry with in-memory exporters
(`backend/tests/telemetry_capture.py`) and never use `OTEL_EXPORTER_OTLP_ENDPOINT`.

## Alerts

Local Grafana has one alert rule on user impact (issue #112):

| | |
|---|---|
| Title | `Server errors above 5%` |
| UID | `winlog-server-errors` |
| Folder, rule group | `Winlog`, `user-impact` |
| Measures | the share of the backend's HTTP requests answered with a server error (5xx) among all of its requests over the last 5 minutes |
| Fires when | the share is above 5% (`0.05`) |
| Evaluated | every minute; the condition must hold for 1 minute (Pending) before the rule is Firing |
| No data | Normal: no request, or no 5xx answer at all, in the last 5 minutes is not user impact |

The query, on the Prometheus data source (uid `prometheus`):

```promql
sum(increase(http_server_request_duration_seconds_count{service_name="winlog-backend", http_response_status_code=~"5.."}[5m]))
/ sum(increase(http_server_request_duration_seconds_count{service_name="winlog-backend"}[5m]))
```

**Why 5xx and not 4xx or 429.** A 5xx answer is what a user feels as "it is broken": the
database is unreachable (`GET /health` answers 503 `database_unreachable`), an unexpected
error, or the AI is unavailable (`POST /summaries` and `POST /suggestions` answer 503
`ai_unavailable`, which is recorded in the HTTP metric with status `503`). 401, 422 and 429
(`limit_reached`) are expected answers to the user's own input or limits, so they do not count.

**Where it is defined.** The rule is code in `ops/grafana/alerting/user-impact.yaml`, in
Grafana's file-provisioning format. `docker-compose.yml` mounts that one file read-only into
the `lgtm` service's alerting provisioning folder, and Grafana loads it on every start, also
on an existing `lgtm-data` volume. It shows as provisioned and cannot be edited in the UI.
After changing the file, run `docker compose restart lgtm`.

**Where to see it.** In Grafana (http://localhost:3000), **Alerting → Alert rules**, folder
`Winlog`. Or over the HTTP API, without a login:

```sh
# The rule as provisioned: folder, group, query, threshold, pending period, no-data state.
curl http://127.0.0.1:3000/api/v1/provisioning/alert-rules/winlog-server-errors
# The rule's state (inactive, pending or firing), health and last evaluation.
curl http://127.0.0.1:3000/api/prometheus/grafana/api/v1/rules
# The alerts that are firing now.
curl http://127.0.0.1:3000/api/alertmanager/grafana/api/v2/alerts
```

### Make it fire on purpose

No AI call is needed. Run the system (or the backend on your computer against the stack, as
above) with `AI_PROVIDER=mock`, then:

1. Stop the database: `docker compose stop db`. `GET /health` now answers 503.
2. Send `GET /health` repeatedly for a few minutes, for example one request every 2 seconds:
   `while true; do curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health; sleep 2; done`.
3. Watch the rule in **Alerting → Alert rules**: it goes to **Pending** at its next
   evaluation and to **Firing** one minute later.
4. Start the database again: `docker compose start db`, and keep sending `GET /health` (now
   200).
5. The rule goes back to **Normal** once the 5xx share of the last 5 minutes is 5% or less.

The timings: the backend exports metrics every 10 seconds, the rule is evaluated every minute,
it is Pending for 1 minute, and it looks at a 5-minute window. So it fires about 1 to 3
minutes after the first 5xx, and resolves up to about 6 minutes after the last one, depending
on how many good requests follow.

`increase()` does not count the first export of a series that has just appeared, such as the
first 503s after a start: it only counts what was added between two exports. Errors sent in
one short burst, inside one 10-second export, may therefore not fire the rule at all. Spread
them over more than one export, as the steps above do.

What the live check on #112 showed (2026-11-15, the backend on the host, one request every
2 seconds): the first 503 at 22:45:30, Pending at the evaluation at 22:46:20 (share 0.52),
Firing at 22:47:20 (share 1, the first 2 requests of the new 503 series were not counted).
After `docker compose start db` at 22:47:33, the rule was Normal again at 22:52:20 (share 0).
About 30 requests answering 200, and then about 30 answering 401, left it Normal (no data,
because there was no 5xx series). With the backend running and no request in the last
5 minutes, the share is `NaN` (0 / 0), and the rule stayed Normal with health ok (22:58:20).
It still loaded after `docker compose restart lgtm` and on an `lgtm-data` volume created
without it.

**No contact point.** No contact point, notification policy or mute timing is provisioned:
the alert shows in Grafana only, and nothing is sent anywhere. Grafana's default notification
policy may log a failed delivery to its unconfigured default contact point, which is expected.
In `grafana/otel-lgtm:0.39.0` the default policy routes to a receiver named `empty`, with no
integration.

**Privacy.** The rule uses only the allowlisted metric `http.server.request.duration` and its
allowlisted labels (below), and it aggregates them with `sum(...)` and no `by`, so an alert
carries no label from the data. Its labels (`severity: critical`) and annotations (a summary,
and a description with the share and a pointer to this section) are fixed text.

**Hosted telemetry (#92).** The same query and threshold can be created in the hosted Grafana,
for example through its alerting provisioning HTTP API or with Terraform, using the hosted
Prometheus data source's uid instead of `prometheus`. The threshold may need tuning there,
because the platform's health checks add `GET /health` traffic. Nothing for #92 is built here.

## Signals

### Spans

Only these attributes. A status Error carries at most an exception's class name.

| Span | Kind | Attributes |
|---|---|---|
| `{METHOD} {route template}`, for example `POST /summaries` or `PUT /entries/{entryId}` | SERVER | `http.request.method`, `http.route`, `http.response.status_code`, `winlog.outcome` (summary journey only), `error.type` (5xx only) |
| `summary.select_entries` | INTERNAL | `winlog.entry_count` |
| `ai.limits.reserve` | INTERNAL | `winlog.ai.operation`, `winlog.outcome` (`allowed` or `limit_reached`) |
| `ai.summarise`, `ai.suggest` | INTERNAL | `winlog.ai.operation` (`suggest`, `summarise`), `winlog.ai.provider` (`mock`, `openai-compatible`), `winlog.ai.outcome` (`success`, `timeout`, `provider_error`), `winlog.entry_count` (summarise only) |
| `summary.save` | INTERNAL | none |

- The SERVER span is named after the route template, never the actual path. A path that
  matches no route is named by its method only and has no `http.route`. A non-standard
  method is recorded as `_OTHER`.
- A 5xx response gives the SERVER span status Error. Its `error.type` is the exception's class
  name, or the status code (such as `503`) when the error was answered without an exception.
- Every request starts a new trace. Incoming `traceparent`, `tracestate` and `baggage` headers
  are ignored.

The outcomes of `POST /summaries`, in its trace and in the outcome metric:

| `winlog.outcome` | Status | Child spans |
|---|---|---|
| `created` | 201 | all four |
| `no_matching_entries` | 422 | `summary.select_entries` only |
| `summary_input_too_large` | 422 | `summary.select_entries` only |
| `limit_reached` | 429 | `summary.select_entries`, then `ai.limits.reserve` with status Error |
| `ai_unavailable` | 503 | up to `ai.summarise`, which has status Error and `winlog.ai.outcome` `timeout` or `provider_error`; the SERVER span has status Error |

A request that fails validation (422 `validation_failed`) or authentication (401) never
reaches the journey. It shows only in the HTTP metric.

### Metrics

| Name | Type, unit | Attributes |
|---|---|---|
| `http.server.request.duration` | histogram, `s` | `http.request.method`, `http.route`, `http.response.status_code` |
| `winlog.summary.generate.requests` | counter, `{request}` | `winlog.outcome` (the five outcomes above) |
| `winlog.ai.request.duration` | histogram, `s` | `winlog.ai.operation`, `winlog.ai.provider`, `winlog.ai.outcome` |

### Logs

Only the `app` loggers are printed and exported. Each record is one JSON object per line on
stdout, and goes over OTLP when export is on:

```json
{"timestamp": "2026-11-13T19:56:48.927Z", "level": "INFO", "logger": "app.telemetry", "message": "request finished", "trace_id": "6b9033254883c5b7b440b43630dff18e", "span_id": "ca79049417be8842", "http.request.method": "POST", "http.route": "/summaries", "http.response.status_code": 201, "duration_ms": 32}
```

- `timestamp` (ISO 8601, UTC), `level`, `logger`, `message`, `trace_id` (32 hex characters) and
  `span_id` (16 hex characters, both only inside a request), plus the record's allowlisted
  fields.
- `request finished` (INFO; ERROR for 5xx): method, route, status, `duration_ms` and, for 5xx,
  `error.type`. It replaces uvicorn's access log, which is turned off however the backend is
  started, because it wrote query strings (tag names) and client addresses.
- `summary generation finished` (INFO): `winlog.outcome` and `winlog.entry_count`.
- The AI adapter's line for each AI call (`app.ai.adapter`), and the OpenAI-compatible
  provider's line with the model id, the provider's HTTP status and the time taken
  (`app.ai.openai_compatible`).

Uvicorn's own error log on stderr keeps its traceback for unexpected errors, as before. It is
not JSON and is never exported. Database errors in it never show parameter values
(`hide_parameters=True`).

## Privacy allowlist

Telemetry is span names, attributes, events and status descriptions; metric attributes; log
bodies and attributes; resource attributes; and the JSON lines on stdout. It contains only:

- the resource attributes `service.name` (`winlog-backend`), `service.version` and the SDK's
  `telemetry.sdk.language`, `telemetry.sdk.name` and `telemetry.sdk.version`;
- the attribute keys `http.request.method`, `http.route`, `http.response.status_code`,
  `error.type`, `winlog.outcome`, `winlog.entry_count`, `winlog.ai.operation`,
  `winlog.ai.provider`, `winlog.ai.outcome` and `duration_ms`;
- span and metric names;
- fixed log messages, and the AI model id and provider HTTP status in the OpenAI-compatible
  provider's log line;
- trace and span IDs.

Never, also not in names or messages:

- entry text, Result/Impact, tag names, summary text, filter values;
- AI request or response content;
- passwords, password hashes, tokens, `Authorization` headers;
- email addresses (including `DEMO_EMAIL`), user ids, entry and summary ids;
- IP addresses (including `X-Forwarded-For`), user agents;
- query strings, request or response bodies;
- exception messages, stack traces;
- the database URL, the AI API key.

Telemetry outlives account deletion (FR-D2), so it must hold nothing that identifies a user.

How it is enforced, in `backend/app/telemetry.py`:

- Only the `app` loggers are printed as JSON and exported. Third-party loggers (httpx, openai,
  SQLAlchemy, uvicorn) never reach telemetry.
- One log handler keeps only the allowlisted fields of each record, drops `exc_info` and
  `stack_info`, and keeps only the exception's class name as `error.type`. Log messages are
  fixed text; only allowlisted values may be put into them.
- Span and metric attributes outside the allowlist are dropped.
- Spans use `record_exception=False` and `set_status_on_exception=False`, because the SDK's
  defaults add the exception message and stack trace.
- The resource is built by hand: no environment, host or process detectors.
- No OpenTelemetry auto-instrumentation: it records full URLs with query strings, client
  addresses, user agents, SQL and exception messages.
- Tests check all of this: `backend/tests/unit/test_telemetry.py` and
  `backend/tests/integration/test_telemetry.py`, including
  `test_telemetry_contains_no_customer_data_or_credentials`, which runs every endpoint with
  marker strings.

When you add telemetry, use `app.telemetry.span` and the `app` loggers with allowlisted
`extra` fields only. Adding a new key to the allowlist is a privacy decision: say why in the
issue.
