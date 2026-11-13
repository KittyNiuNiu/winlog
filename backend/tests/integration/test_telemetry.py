"""The key user journey's telemetry: generating a summary (FR-R3, issue #74).

Against real PostgreSQL, with the mock AI provider and in-memory exporters: no collector is
needed. Covers the spans, metrics and log records of each outcome of `POST /summaries`, and
checks that telemetry contains no customer data or credentials (`docs/observability.md`).
"""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from app.ai import MockProvider, Suggestion
from app.auth import hash_token
from app.demo_seed import reset_demo_account
from app.main import create_app
from app.models import Token, User
from app.settings import Settings
from app.telemetry import ALLOWED_ATTRIBUTE_KEYS, ALLOWED_RESOURCE_KEYS, LOG_LINE_KEYS
from tests.integration.conftest import ALLOWED_ORIGIN
from tests.telemetry_capture import CapturedTelemetry, json_lines

JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
FEBRUARY = {"period_start": "2026-02-01", "period_end": "2026-02-28"}
JOURNEY_SPANS = ["summary.select_entries", "ai.limits.reserve", "ai.summarise", "summary.save"]


# --- Helpers ------------------------------------------------------------------------------


@pytest.fixture
def captured() -> CapturedTelemetry:
    return CapturedTelemetry()


@pytest.fixture
def make_client(
    test_database_url: str, migrated_db: Engine, captured: CapturedTelemetry
) -> Callable[..., TestClient]:
    """The app with the given settings and in-memory telemetry, on the test database."""

    def make(**overrides) -> TestClient:
        settings = Settings(
            _env_file=None,
            database_url=test_database_url,
            cors_allowed_origins=[ALLOWED_ORIGIN],
            ai_provider="mock",
            **overrides,
        )
        return TestClient(create_app(settings, telemetry=captured.telemetry))

    return make


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def _mock(client: TestClient) -> MockProvider:
    provider = client.app.state.ai_provider
    assert isinstance(provider, MockProvider)
    return provider


def _token(engine: Engine) -> str:
    """A new user with a login, without going through the password check."""
    token = f"test-token-{uuid.uuid4()}"
    with engine.begin() as connection:
        user_id = connection.execute(
            insert(User)
            .values(email=f"user-{uuid.uuid4()}@example.com", password_hash="hash")
            .returning(User.id)
        ).scalar_one()
        connection.execute(
            insert(Token).values(
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
            )
        )
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _entry(client: TestClient, token: str, date: str = "2026-01-15", **fields) -> dict:
    body = {"text": "Shipped the release", "date": date, "category": "Achievement", **fields}
    response = client.post("/entries", json=body, headers=_auth(token))
    assert response.status_code == 201
    return response.json()


def _generate(client: TestClient, token: str, period: dict = JANUARY):
    return client.post("/summaries", json=period, headers=_auth(token))


def _journey(captured: CapturedTelemetry) -> tuple:
    """The `POST /summaries` SERVER span and its children, in the order they started."""
    [server] = [span for span in captured.server_spans() if span.name == "POST /summaries"]
    children = [span for span in captured.trace(server) if span is not server]
    for child in children:
        assert child.parent.span_id == server.context.span_id
        assert child.kind == SpanKind.INTERNAL
    return server, children


def _outcome_counts(captured: CapturedTelemetry) -> dict[str, int]:
    return {
        point.attributes["winlog.outcome"]: point.value
        for point in captured.points("winlog.summary.generate.requests")
    }


# --- The journey --------------------------------------------------------------------------


def test_fr_r3_summary_trace_has_the_journey_spans_in_order(client, captured, migrated_db):
    token = _token(migrated_db)
    _entry(client, token)
    _entry(client, token, date="2026-01-20")

    assert _generate(client, token).status_code == 201

    server, children = _journey(captured)
    assert server.name == "POST /summaries"
    assert server.kind == SpanKind.SERVER
    assert server.resource.attributes["service.name"] == "winlog-backend"
    assert dict(server.attributes) == {
        "http.request.method": "POST",
        "http.route": "/summaries",
        "http.response.status_code": 201,
        "winlog.outcome": "created",
    }
    assert server.status.status_code == StatusCode.UNSET
    assert [span.name for span in children] == JOURNEY_SPANS
    select, reserve, summarise, save = children
    assert dict(select.attributes) == {"winlog.entry_count": 2}
    assert dict(reserve.attributes) == {
        "winlog.ai.operation": "summarise",
        "winlog.outcome": "allowed",
    }
    assert dict(summarise.attributes) == {
        "winlog.ai.operation": "summarise",
        "winlog.ai.provider": "mock",
        "winlog.ai.outcome": "success",
        "winlog.entry_count": 2,
    }
    assert dict(save.attributes) == {}
    for span in children:
        assert span.status.status_code == StatusCode.UNSET
        assert span.events == ()
    # Each child ends before the next starts.
    for earlier, later in zip(children, children[1:], strict=False):
        assert earlier.end_time <= later.start_time


def test_fr_r3_no_matching_entries_has_only_the_select_span(client, captured, migrated_db):
    token = _token(migrated_db)

    assert _generate(client, token).status_code == 422

    server, children = _journey(captured)
    assert [span.name for span in children] == ["summary.select_entries"]
    assert dict(children[0].attributes) == {"winlog.entry_count": 0}
    assert server.attributes["winlog.outcome"] == "no_matching_entries"
    assert server.attributes["http.response.status_code"] == 422
    assert server.status.status_code == StatusCode.UNSET
    assert _outcome_counts(captured) == {"no_matching_entries": 1}


def test_fr_r3_input_too_large_has_only_the_select_span(make_client, captured, migrated_db):
    client = make_client(ai_summary_max_input_characters=5)
    token = _token(migrated_db)
    _entry(client, token)

    response = _generate(client, token)

    assert response.json()["code"] == "summary_input_too_large"
    server, children = _journey(captured)
    assert [span.name for span in children] == ["summary.select_entries"]
    assert server.attributes["winlog.outcome"] == "summary_input_too_large"
    assert _outcome_counts(captured) == {"summary_input_too_large": 1}


def test_fr_r3_limit_reached_ends_at_the_reserve_span(make_client, captured, migrated_db):
    client = make_client(ai_daily_summaries_per_user=0)
    token = _token(migrated_db)
    _entry(client, token)

    assert _generate(client, token).status_code == 429

    server, children = _journey(captured)
    assert [span.name for span in children] == ["summary.select_entries", "ai.limits.reserve"]
    reserve = children[1]
    assert reserve.status.status_code == StatusCode.ERROR
    assert reserve.status.description == "AILimitReachedError"
    assert dict(reserve.attributes) == {
        "winlog.ai.operation": "summarise",
        "winlog.outcome": "limit_reached",
    }
    assert reserve.events == ()
    assert server.attributes["winlog.outcome"] == "limit_reached"
    assert server.status.status_code == StatusCode.UNSET
    assert _outcome_counts(captured) == {"limit_reached": 1}


@pytest.mark.parametrize(
    ("fail", "ai_outcome", "error_class"),
    [
        (MockProvider.raise_timeout, "timeout", "AITimeoutError"),
        (MockProvider.raise_provider_error, "provider_error", "AIProviderError"),
    ],
)
def test_fr_r3_ai_unavailable_marks_the_ai_span_and_the_server_span_as_errors(
    client, captured, migrated_db, fail, ai_outcome, error_class
):
    token = _token(migrated_db)
    _entry(client, token)
    fail(_mock(client))

    assert _generate(client, token).status_code == 503

    server, children = _journey(captured)
    assert [span.name for span in children] == JOURNEY_SPANS[:3]
    summarise = children[2]
    assert summarise.status.status_code == StatusCode.ERROR
    assert summarise.status.description == error_class
    assert summarise.attributes["winlog.ai.outcome"] == ai_outcome
    assert summarise.events == ()
    assert server.status.status_code == StatusCode.ERROR
    assert server.attributes["http.response.status_code"] == 503
    assert server.attributes["winlog.outcome"] == "ai_unavailable"
    assert server.attributes["error.type"] == "503"
    assert _outcome_counts(captured) == {"ai_unavailable": 1}
    [point] = captured.points("winlog.ai.request.duration")
    assert point.attributes["winlog.ai.outcome"] == ai_outcome


def test_fr_r3_request_validation_is_not_a_journey_outcome(client, captured, migrated_db):
    token = _token(migrated_db)

    backwards = {"period_start": "2026-02-01", "period_end": "2026-01-01"}
    assert _generate(client, token, backwards).status_code == 422
    assert client.post("/summaries", json=JANUARY).status_code == 401

    assert [span.name for span in captured.spans()] == ["POST /summaries", "POST /summaries"]
    assert all(m.name != "winlog.summary.generate.requests" for m in captured.metrics())
    statuses = [
        point.attributes["http.response.status_code"]
        for point in captured.points("http.server.request.duration")
        if point.attributes.get("http.route") == "/summaries"
    ]
    assert sorted(statuses) == [401, 422]


def test_fr_r3_summary_metrics_have_the_outcome_and_ai_labels(client, captured, migrated_db):
    token = _token(migrated_db)
    _entry(client, token)

    assert _generate(client, token).status_code == 201
    assert _generate(client, token, FEBRUARY).status_code == 422

    assert _outcome_counts(captured) == {"created": 1, "no_matching_entries": 1}
    counter = captured.metric("winlog.summary.generate.requests")
    assert counter.unit == "{request}"
    ai_duration = captured.metric("winlog.ai.request.duration")
    assert ai_duration.unit == "s"
    [point] = ai_duration.data.data_points
    assert dict(point.attributes) == {
        "winlog.ai.operation": "summarise",
        "winlog.ai.provider": "mock",
        "winlog.ai.outcome": "success",
    }
    assert point.count == 1
    http_duration = captured.metric("http.server.request.duration")
    assert http_duration.unit == "s"
    summary_points = {
        point.attributes["http.response.status_code"]: point.count
        for point in http_duration.data.data_points
        if point.attributes.get("http.route") == "/summaries"
    }
    assert summary_points == {201: 1, 422: 1}


def test_fr_r3_summary_logs_share_the_trace_id(client, captured, migrated_db, capsys):
    token = _token(migrated_db)
    _entry(client, token)
    capsys.readouterr()

    assert _generate(client, token).status_code == 201

    server, _ = _journey(captured)
    trace_id = server.context.trace_id
    exported = {log.log_record.body: log for log in captured.logs_of_trace(trace_id)}
    assert "request finished" in exported
    assert "summary generation finished" in exported
    ai_lines = [body for body in exported if body.startswith("AI summarise with provider mock")]
    assert len(ai_lines) == 1
    finished = exported["summary generation finished"].log_record
    assert dict(finished.attributes) == {"winlog.outcome": "created", "winlog.entry_count": 1}
    assert finished.severity_text == "INFO"
    ai_log = exported[ai_lines[0]].log_record
    assert dict(ai_log.attributes) == {
        "winlog.ai.operation": "summarise",
        "winlog.ai.provider": "mock",
        "winlog.ai.outcome": "success",
        "winlog.entry_count": 1,
        "duration_ms": ai_log.attributes["duration_ms"],
    }

    lines = json_lines(capsys.readouterr().out)
    messages = [line["message"] for line in lines]
    assert messages == [ai_lines[0], "summary generation finished", "request finished"]
    for line in lines:
        assert line["trace_id"] == f"{trace_id:032x}"
        assert len(line["span_id"]) == 16
        assert set(line) <= set(LOG_LINE_KEYS) | ALLOWED_ATTRIBUTE_KEYS
    assert lines[1]["winlog.outcome"] == "created"
    assert lines[2]["http.route"] == "/summaries"


# --- Privacy ------------------------------------------------------------------------------


def test_telemetry_contains_no_customer_data_or_credentials(
    test_database_url, migrated_db, captured, capsys
):
    marker = uuid.uuid4().hex[:12]
    email = f"mk-{marker}@example.com"
    password = f"Mk-Pass-{marker}-9"
    demo_email = f"demo-{marker}@example.com"
    visitor_ip = "198.51.100.173"
    entry_text = f"entry-text-{marker}"
    edited_text = f"edited-text-{marker}"
    result_impact = f"result-impact-{marker}"
    tag = f"tag-{marker}"
    suggested_tag = f"suggested-tag-{marker}"
    summary_text = f"summary-text-{marker}"
    edited_summary = f"edited-summary-{marker}"
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        demo_email=demo_email,
    )
    app = create_app(settings, telemetry=captured.telemetry)

    @app.get("/test-only/crash")
    def crash() -> dict:
        raise RuntimeError(f"exception-message-{marker}")

    client = TestClient(app, raise_server_exceptions=False)
    mock = _mock(client)
    with Session(migrated_db) as session:
        reset_demo_account(session, demo_email, dt.date(2026, 11, 13))
        session.commit()
    capsys.readouterr()

    # Register and log in, also with a wrong password.
    register = client.post("/auth/register", json={"email": email, "password": password})
    assert register.status_code == 201
    wrong = client.post("/auth/login", json={"email": email, "password": f"x{password}"})
    assert wrong.status_code == 401
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    with Session(migrated_db) as session:
        user_id = str(session.scalars(select(User.id).where(User.email == email)).one())
    headers = _auth(token)

    # Entries: create, edit, list (also by tag) and read.
    entry = client.post(
        "/entries",
        json={
            "text": entry_text,
            "date": "2026-01-15",
            "category": "Achievement",
            "result_impact": result_impact,
            "tags": [tag],
        },
        headers=headers,
    ).json()
    entry_id = entry["id"]
    assert (
        client.put(
            f"/entries/{entry_id}",
            json={
                "text": edited_text,
                "date": "2026-01-15",
                "category": "Learning",
                "result_impact": result_impact,
                "tags": [tag],
            },
            headers=headers,
        ).status_code
        == 200
    )
    assert client.get("/entries", headers=headers).status_code == 200
    assert client.get(f"/entries?tag={tag}", headers=headers).status_code == 200
    assert client.get(f"/entries/{entry_id}", headers=headers).status_code == 200
    assert client.get("/tags", headers=headers).status_code == 200

    # Suggestions, with a marker tag in the AI answer.
    mock.return_suggestion(Suggestion(category="Achievement", tags=[suggested_tag]))
    suggestion = client.post("/suggestions", json={"text": entry_text}, headers=headers)
    assert suggestion.status_code == 200
    mock.reset()

    # Summaries: created (marker AI answer), no_matching_entries, ai_unavailable, limit_reached.
    mock.return_summary(summary_text)
    with_tag = {**JANUARY, "tags": [tag], "categories": ["Learning"]}
    created = client.post("/summaries", json=with_tag, headers=headers)
    assert created.status_code == 201
    summary_id = created.json()["id"]
    no_match = client.post("/summaries", json={**FEBRUARY, "tags": [tag]}, headers=headers)
    assert no_match.status_code == 422
    mock.raise_provider_error()
    assert client.post("/summaries", json=with_tag, headers=headers).status_code == 503
    mock.reset()
    assert client.post("/summaries", json=with_tag, headers=headers).status_code == 429
    assert (
        client.patch(
            f"/summaries/{summary_id}", json={"text": edited_summary}, headers=headers
        ).status_code
        == 200
    )
    assert client.get("/summaries", headers=headers).status_code == 200
    assert client.get(f"/summaries/{summary_id}", headers=headers).status_code == 200

    # A demo login from a marker address.
    demo = client.post("/auth/demo", headers={"X-Forwarded-For": visitor_ip})
    assert demo.status_code == 200
    demo_token = demo.json()["token"]

    # An unexpected error with a marker message.
    assert client.get("/test-only/crash").status_code == 500

    # Export, log out and delete the account.
    assert client.get("/export/json", headers=headers).status_code == 200
    assert client.get("/export/markdown", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 204
    token2 = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    assert (
        client.request(
            "DELETE", "/account", json={"current_password": password}, headers=_auth(token2)
        ).status_code
        == 204
    )

    outcomes = _outcome_counts(captured)
    assert set(outcomes) == {"created", "no_matching_entries", "ai_unavailable", "limit_reached"}

    forbidden = {
        "marker": marker,
        "email": email,
        "password": password,
        "demo email": demo_email,
        "visitor ip": visitor_ip,
        "user id": user_id,
        "entry id": entry_id,
        "summary id": summary_id,
        "token": token,
        "second token": token2,
        "demo token": demo_token,
        "database url": test_database_url,
    }
    exported = captured.everything_as_text()
    printed = capsys.readouterr()
    lines = json_lines(printed.out)
    assert len(lines) > 30
    for name, value in forbidden.items():
        assert value not in exported, f"{name} in exported telemetry"
        assert value not in printed.out, f"{name} in the JSON log lines"
    assert "Traceback" not in exported
    assert "Traceback" not in printed.out

    for where, key in captured.attribute_keys():
        allowed = ALLOWED_RESOURCE_KEYS if where == "resource" else ALLOWED_ATTRIBUTE_KEYS
        assert key in allowed, f"{key} in {where}"
    for line in lines:
        assert set(line) <= set(LOG_LINE_KEYS) | ALLOWED_ATTRIBUTE_KEYS, line
    for span in captured.spans():
        assert span.events == ()
        assert span.status.description in (None, "AILimitReachedError", "AIProviderError")
