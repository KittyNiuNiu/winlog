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

The hosted dev and production backends send theirs to one Grafana Cloud stack, marked by
environment ([Hosted telemetry](#hosted-telemetry-dev-and-production)).

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

Metrics are exported every 10 seconds (`OTEL_METRIC_EXPORT_INTERVAL`, default 10000 ms), so a
new measurement can take that long to appear.

Every signal carries the resource attribute `deployment.environment.name` (`local` here). The
local stack makes it the label `deployment_environment_name` on every Prometheus series and every
Loki stream, and Tempo shows it as `resource.deployment.environment.name`.

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
   `OTLP_HTTP_HOST_PORT`). Keep `TELEMETRY_ENVIRONMENT=local` and `OTEL_METRIC_EXPORT_INTERVAL`
   at its default, 10000, which the [alert timings](#make-it-fire-on-purpose) expect. Leave
   `OTEL_EXPORTER_OTLP_HEADERS` empty: the local collector needs no credential, and with an
   `http://` endpoint any headers value stops the backend at startup, because headers carry a
   credential and go only over `https://`.
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

## Hosted telemetry (dev and production)

Both hosted backends, `winlog-api-dev` and `winlog-api` on Render, send their traces, metrics
and JSON log records over OTLP/HTTP to **one Grafana Cloud stack**, the product owner's (#92).
`render.yaml` sets the same endpoint on both:

```
https://otlp-gateway-prod-eu-west-4.grafana.net/otlp
```

The backend adds `/v1/traces`, `/v1/metrics` and `/v1/logs`, as locally. No collector or
Grafana Alloy runs in between. The product owner's account steps (tokens, the Render
Dashboard, the Blueprint sync) are in `ops/deployment.md`, "Hosted telemetry: Grafana Cloud".

**Why the endpoint URL is committed.** It names Grafana Cloud's shared gateway for the region,
not the account. Knowing it lets nobody read the data, which needs the product owner's Grafana
login, or send data in, which needs an access token. The tokens are only in Render, as the
secret `OTEL_EXPORTER_OTLP_HEADERS` (`sync: false`, one write-only token per environment), and
the backend sends them only over `https://`.

**Environments.** Every span, metric and log record carries the resource attribute
`deployment.environment.name`: `dev` or `production` (`TELEMETRY_ENVIRONMENT` in `render.yaml`),
and `local` on a computer, Docker Compose included. It is the only thing that tells dev from
production in the one stack.

**Where to find each signal.** In Grafana Cloud, open the stack's Grafana → **Explore**, and
choose the stack's data source for traces (Tempo), logs (Loki) or metrics (Prometheus). The
queries are the same as [locally](#open-grafana), with the environment added:

- Traces: TraceQL
  `{resource.service.name="winlog-backend" && resource.deployment.environment.name="dev" && name="POST /summaries"}`.
- Logs: `{service_name="winlog-backend", deployment_environment_name="dev"}`, and
  `| trace_id="<trace ID>"` for one request's lines.
- Metrics: `winlog_summary_generate_requests_total{deployment_environment_name="dev"}`, and the
  same label on `http_server_request_duration_seconds_count` and the AI histogram.

Locally, `deployment_environment_name` is a label of every Loki stream and Prometheus series
(checked on #92). Grafana Cloud does the same, as checked on #92 after the merge (its section E
records 6922675242 and 6924332073): in Grafana Cloud, logs and metrics carry the label
`deployment_environment_name`, and traces the attribute `resource.deployment.environment.name`.

**Metric interval.** The hosted backends export metrics every 60 seconds
(`OTEL_METRIC_EXPORT_INTERVAL=60000`): one data point per series per minute. Locally it stays
10 seconds.

**The free plan.** The product owner approved Grafana Cloud's free plan for dev and production
on 16 November 2026: no paid plan or add-on, $0. It keeps the data for 14 days. Its limits, per
Grafana Cloud's pricing page as found by search (the product owner's stack is the authority):
10,000 active metric series, 50 GB of logs and 50 GB of traces per month. Over a limit, Grafana
Cloud drops the data; the app works the same.

The estimate stays far below that. About 1,600 active series per environment: 20 operations ×
a few status codes × 17 series per HTTP duration histogram (15 buckets, `_count` and `_sum`),
plus the AI duration histogram (20 series per operation and outcome) and the outcome counter.
Even one request per second would be about 2.6 GB per month per signal and environment. No
sampling, and `GET /health` stays in: it carries the 503 `database_unreachable` signal.

**Privacy.** Hosted telemetry holds exactly what local telemetry holds: only the
[allowlist](#privacy-allowlist), nothing that identifies a user. That matters because Grafana
Cloud keeps it for 14 days after an account is deleted (FR-D2).

**Failed exports.** Exports never hold up a request. When one fails, the backend's log on
Render shows a line from the OpenTelemetry exporter on stderr, such as
`Failed to export spans batch code: 401, reason: Unauthorized`:

- `401` (or `403`): the token is wrong, revoked or lacks a write scope. Create a new token and
  replace the value in Render (`ops/deployment.md`, "Hosted telemetry: Grafana Cloud").
- `429` (Too Many Requests): a free-plan limit was hit, and Grafana Cloud drops the data. The
  exporter retries a 429, so the log does not show `code: 429`, and searching it for `429` finds
  nothing. It shows `Transient error Too Many Requests encountered while exporting … retrying
  in …`, and then `Failed to export … due to timeout, max retries or shutdown.` Check the
  stack's usage page; do not choose a paid plan without the product owner's approval.
- A connection error or timeout: Grafana Cloud did not answer within 2 seconds. Exports resume
  by themselves.

The exporter logs the status code and reason, never the headers. A malformed
`OTEL_EXPORTER_OTLP_HEADERS` never reaches the exporter: the backend stops at startup with
`OTEL_EXPORTER_OTLP_HEADERS is invalid`, a message that never contains the value, because the
OpenTelemetry SDK would otherwise print the whole value in a "Header format invalid" warning.

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

### Hosted alerts (dev and production)

The hosted dev and production backends ([Hosted telemetry](#hosted-telemetry-dev-and-production))
each have the same alert in the product owner's Grafana Cloud stack, and it emails the product
owner when it fires (issue #117).

**Rules and file.** Two rules, in folder `Winlog`, group `user-impact`:

| Title | UID | Environment |
|---|---|---|
| `Server errors above 5% in production` | `winlog-server-errors-production` | `production` |
| `Server errors above 5% in dev` | `winlog-server-errors-dev` | `dev` |

Each measures what the local rule measures, with the local query, but only for its own
environment: both selectors add `deployment_environment_name="production"` (or `"dev"`) after
`service_name="winlog-backend"`. Each fires when the share is above 5% (` > 0.05` at the end of
the query), is evaluated every minute, is Pending for 1 minute before it is Firing, and is
Normal when there is no data. They are defined in `ops/grafana-cloud/alert-rules.yaml`, in
Prometheus rule-file format, and the product owner imports them in Grafana Cloud's UI
(`ops/deployment.md`, "Hosted alerts: Grafana Cloud"). `docker-compose.yml` does not mount that
file, so the local stack does not load it. `backend/tests/unit/test_hosted_alert_rules.py`
checks that its query stays the local query with the environment and the threshold added.

**How the import converts them.** The import (**Import alert rules**, source **YAML file**;
in older versions **Import to Grafana-managed rules** → **Prometheus YAML file**) turns them into Grafana-managed rules. Grafana runs the query with a
1-minute offset (it looks at the data up to 1 minute before each evaluation), treats no data
and query errors as Normal, and keeps the labels, the annotations and the 1-minute pending
period. An alert that stops matching resolves at the next evaluation. Why this format: Grafana
Cloud has no file provisioning, and an import in the UI needs no API token in a terminal.

**Timings.** The hosted backends export metrics every 60 seconds, so the first minute of a new
error series is not counted (`increase()`, [above](#make-it-fire-on-purpose)), and the query
looks 1 minute back. The rule fires about 3 to 6 minutes after server errors start, and
resolves within about 10 minutes after they stop.

What the live check on #117 showed (2026-11-16, the file imported into the local Grafana as
below, the backend on the host as dev with a 60-second export, one request every 2 seconds):
about 30 `GET /health` answering 200 (18:12:03 to 18:13:04) left both rules Normal for over
3 minutes. After `docker compose stop db`, the first 503 was at 18:16:23. The dev rule was
Pending at the evaluation at 18:19:50 (3 min 27 s later, share 1) and Firing at 18:20:50
(4 min 27 s). The production rule stayed Normal the whole time. After `docker compose start db`,
the last 503 was at 18:21:06, and the dev rule was Normal again at 18:26:50 (5 min 44 s later).
The local rule also saw this backend (it has no environment matcher) and, on the same data but
with no query offset, went Pending, Firing and Normal 70 seconds earlier each time (18:18:40,
18:19:40 and 18:25:40).

**Health checks.** Render calls `GET /health` every few seconds while a backend is awake, and
these requests count in the share. A single failing user request among them can therefore stay
below 5%. When the database is unreachable, `/health` itself answers 503, and the rule fires.
The threshold stays 5%, the same as locally.

**What it cannot see.** A backend that is asleep (a free instance after 15 minutes without
requests), not started or crashed sends no telemetry. The rule is then Normal (no data). It
detects server errors only while the backend runs.

**Notifications.** The rules route by the label `service=winlog-backend` to the contact point
`Winlog email`, through a child of the default notification policy that the product owner sets
up. The email address is entered only in Grafana Cloud and is never written in the repository.
An email holds only the rule's fixed labels and annotations, Grafana's own values (the share)
and links to the stack.

**Privacy.** As for the local rule: the rules use only the allowlisted metric
`http.server.request.duration`, its allowlisted labels and `deployment_environment_name`, and
aggregate with `sum(...)` and no `by`, so an alert carries no label from the data. Their labels
(`severity: critical`, `service: winlog-backend`, `environment`) and annotations (a summary and
a pointer to this section) are fixed text, with no template.

**Check the file locally.** Anyone can run the hosted rules in the local stack before
importing them. No Grafana Cloud access and no AI call is needed. The import lands in a
separate folder, `Winlog hosted check`, so the local `Winlog` folder is not touched.

```sh
# Repo root: the database and the local stack (copy .env.example to .env first if it is missing).
docker compose up -d --wait db lgtm
# Import the file's one group (groups[0]) through the convert API, as the UI's import does.
# The answer is 202 with "status":"success".
(cd backend && uv run python -c 'import sys, yaml; sys.stdout.write(yaml.safe_dump(yaml.safe_load(open("../ops/grafana-cloud/alert-rules.yaml"))["groups"][0], sort_keys=False))') \
  | curl -sS -X POST 'http://127.0.0.1:3000/api/convert/prometheus/config/v1/rules/Winlog%20hosted%20check' \
      -H 'Content-Type: application/yaml' -H 'X-Grafana-Alerting-Datasource-UID: prometheus' --data-binary @-
# backend/: run the backend as dev runs on Render, with the mock AI.
uv run alembic upgrade head
AI_PROVIDER=mock OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 TELEMETRY_ENVIRONMENT=dev \
  OTEL_METRIC_EXPORT_INTERVAL=60000 uv run uvicorn app.main:app --port 8000
```

Then watch `curl http://127.0.0.1:3000/api/prometheus/grafana/api/v1/rules` (for example every
10 seconds), and make the dev rule fire as [above](#make-it-fire-on-purpose): `docker compose
stop db`, `GET /health` every 2 seconds, then `docker compose start db`. The dev rule goes to
Pending and Firing, the production rule stays Normal, and
`curl http://127.0.0.1:3000/api/alertmanager/grafana/api/v2/alerts` shows the alert's fixed
labels and annotations. Afterwards remove the check folder's rules (the answer is 202):

```sh
curl -sS -X DELETE 'http://127.0.0.1:3000/api/convert/prometheus/config/v1/rules/Winlog%20hosted%20check'
```

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

- the resource attributes `service.name` (`winlog-backend`), `service.version`,
  `deployment.environment.name` and the SDK's `telemetry.sdk.language`, `telemetry.sdk.name`
  and `telemetry.sdk.version`. `deployment.environment.name` (`local`, `dev` or `production`,
  from `TELEMETRY_ENVIRONMENT`, #92) tells dev from production in one hosted stack; it is a
  fixed value from configuration, never user data;
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
- the database URL, the AI API key;
- the OTLP export headers (`OTEL_EXPORTER_OTLP_HEADERS`). They are a credential, the Grafana
  Cloud token: sent only to the export endpoint over `https://`, never in telemetry, the JSON
  lines or any log, also not in the error that a malformed value stops the backend with.

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
- The resource is built by hand: no environment, host or process detectors, and no
  `service.instance.id` (a new id on every start would make new metric series on every wake of
  a free instance).
- No OpenTelemetry auto-instrumentation: it records full URLs with query strings, client
  addresses, user agents, SQL and exception messages.
- Tests check all of this: `backend/tests/unit/test_telemetry.py` and
  `backend/tests/integration/test_telemetry.py`, including
  `test_telemetry_contains_no_customer_data_or_credentials`, which runs every endpoint with
  marker strings, a marker export headers value among them.

When you add telemetry, use `app.telemetry.span` and the `app` loggers with allowlisted
`extra` fields only. Adding a new key to the allowlist is a privacy decision: say why in the
issue.
