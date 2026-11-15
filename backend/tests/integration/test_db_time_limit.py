"""The time limit for each database call (`DATABASE_QUERY_TIMEOUT_SECONDS`, issue #95).

Against real PostgreSQL. The paused-database tests go through `PausableProxy`: a paused proxy
keeps the TCP connections open and accepts new ones, but sends nothing back, like
`docker compose pause db`. It resumes by itself after a while, so code without the time limit
makes these tests fail instead of hang.

Q is `DATABASE_QUERY_TIMEOUT_SECONDS` and C is `DATABASE_CONNECT_TIMEOUT_SECONDS`.
"""

import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Annotated, Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db import create_db_engine, get_session, sqlalchemy_url
from app.main import create_app
from app.settings import Settings
from app.telemetry import ALLOWED_ATTRIBUTE_KEYS, ALLOWED_RESOURCE_KEYS, LOG_LINE_KEYS, Telemetry
from tests.integration.conftest import ALLOWED_ORIGIN
from tests.integration.pausable_proxy import PausableProxy
from tests.telemetry_capture import CapturedTelemetry, json_lines

Q = 2
C = 2
INTERNAL_ERROR = {"code": "internal_error", "message": "Something went wrong."}
PASSWORD = "Correct-Horse-7"
# What TestClient returns.
Response = Any
# For tests that check the pool while the database is still paused: the proxy must not resume
# by itself before that check.
LONG_PAUSE_SECONDS = 30


# --- Helpers ------------------------------------------------------------------------------


@pytest.fixture
def proxy(test_database_url: str) -> Iterator[PausableProxy]:
    url = make_url(sqlalchemy_url(test_database_url))
    proxy = PausableProxy(url.host or "localhost", url.port or 5432)
    yield proxy
    proxy.close()


@pytest.fixture
def proxied_url(test_database_url: str, proxy: PausableProxy) -> str:
    """The test database's URL, through the proxy."""
    url = make_url(sqlalchemy_url(test_database_url)).set(host="127.0.0.1", port=proxy.port)
    return url.render_as_string(hide_password=False)


def _settings(database_url: str, query_timeout: int = Q, connect_timeout: int = C) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        database_query_timeout_seconds=query_timeout,
        database_connect_timeout_seconds=connect_timeout,
    )


@pytest.fixture
def make_client(proxied_url: str, migrated_db: Engine) -> Iterator[Callable[..., TestClient]]:
    """Started apps on the test database through the proxy. 500 responses are not raised."""
    clients: list[TestClient] = []

    def make(
        query_timeout: int = Q, connect_timeout: int = C, telemetry: Telemetry | None = None
    ) -> TestClient:
        app = create_app(_settings(proxied_url, query_timeout, connect_timeout), telemetry)
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def direct_engine(test_database_url: str) -> Iterator[Engine]:
    """The app's engine on the test database, without the proxy."""
    engine = create_db_engine(_settings(test_database_url))
    yield engine
    engine.dispose()


@pytest.fixture
def proxied_engine(proxied_url: str) -> Iterator[Engine]:
    """The app's engine on the test database, through the proxy."""
    engine = create_db_engine(_settings(proxied_url))
    yield engine
    engine.dispose()


@dataclass
class _User:
    email: str
    password: str
    token: str
    entry_text: str

    @classmethod
    def register(cls, client: TestClient, marker: str = "") -> "_User":
        """A registered, logged-in user with one entry. These requests leave idle connections
        in the pool."""
        email = f"user-{marker or uuid.uuid4().hex}@example.com"
        password = f"{PASSWORD}-{marker}" if marker else PASSWORD
        entry_text = f"entry-text-{marker or uuid.uuid4().hex}"
        body = {"email": email, "password": password}
        assert client.post("/auth/register", json=body).status_code == 201
        token = client.post("/auth/login", json=body).json()["token"]
        user = cls(email, password, token, entry_text)
        assert client.post("/entries", json=user.entry(), headers=user.auth()).status_code == 201
        return user

    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def entry(self, text: str | None = None) -> dict:
        return {"text": text or self.entry_text, "date": "2026-11-14", "category": "Achievement"}


def _send(client: TestClient, user: _User, request: str) -> Response:
    if request == "GET /entries":
        return client.get("/entries", headers=user.auth())
    if request == "POST /entries":
        return client.post("/entries", json=user.entry("written-while-paused"), headers=user.auth())
    assert request == "POST /auth/login"
    return client.post("/auth/login", json={"email": user.email, "password": user.password})


def _timed(send: Callable[[], Response]) -> tuple[Response, float]:
    started = time.monotonic()
    response = send()
    return response, time.monotonic() - started


def _wait_until(condition: Callable[[], bool], seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.1)


def _assert_internal_error(response: Response, contract) -> None:
    assert response.status_code == 500
    assert response.json() == INTERNAL_ERROR
    contract("Error").validate(response.json())


def _busy_sessions(engine: Engine) -> int:
    """Sessions in the test database, other than this one, that run or hold a transaction."""
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() "
                "AND (state = 'active' OR state LIKE 'idle in transaction%')"
            )
        ).scalar_one()


def _entry_texts(response: Response) -> list[str]:
    return [entry["text"] for entry in response.json()["entries"]]


def _cors_header_values(response: Response) -> dict[str, str | None]:
    """The CORS response headers (Access-Control-*) and Vary, with their values."""
    names = sorted(
        name.lower() for name in response.headers if name.lower().startswith("access-control-")
    )
    return {name: response.headers.get(name) for name in [*names, "vary"]}


# --- The whole database stops answering ---------------------------------------------------


@pytest.mark.parametrize("request_name", ["GET /entries", "POST /entries", "POST /auth/login"])
def test_db_time_limit_requests_answer_500_when_the_database_stops_answering(
    make_client, proxy: PausableProxy, contract, request_name: str
):
    client = make_client()
    user = _User.register(client)
    pool = client.app.state.engine.pool
    assert pool.checkedout() == 0 and pool.checkedin() >= 1  # an idle connection in the pool

    proxy.pause()
    # The first request gets the idle pooled connection, the second one a new connection.
    for _ in range(2):
        response, elapsed = _timed(lambda: _send(client, user, request_name))

        _assert_internal_error(response, contract)
        assert elapsed < Q + C + 1


@pytest.mark.parametrize("call", ["statement", "commit", "rollback"])
def test_db_time_limit_cuts_off_a_call_that_stops_getting_answers(
    proxied_engine: Engine, proxy: PausableProxy, call: str
):
    connection = proxied_engine.connect()
    connection.execute(text("SELECT 1"))  # the connection now has an open transaction
    calls = {
        "statement": lambda: connection.execute(text("SELECT 2")),
        "commit": connection.commit,
        "rollback": connection.rollback,
    }

    proxy.pause()
    started = time.monotonic()
    with pytest.raises(DBAPIError):
        calls[call]()
    elapsed = time.monotonic() - started

    assert elapsed < Q + 1
    assert connection.invalidated  # closed: SQLAlchemy never hands it out again
    connection.close()
    proxy.resume()
    with proxied_engine.connect() as next_connection:
        assert next_connection.execute(text("SELECT 3")).scalar_one() == 3


def test_db_time_limit_concurrent_requests_all_answer_500_in_time(
    make_client, proxy: PausableProxy, contract
):
    client = make_client()
    user = _User.register(client)

    def get_entries(_: int) -> tuple[Response, float]:
        return _timed(lambda: client.get("/entries", headers=user.auth()))

    proxy.pause()
    with ThreadPoolExecutor(max_workers=30) as executor:
        results = list(executor.map(get_entries, range(30)))

    for response, _ in results:
        _assert_internal_error(response, contract)
    # More requests than the pool has connections: some wait for a free one, at most Q.
    assert max(elapsed for _, elapsed in results) < 2 * (Q + C)


@pytest.mark.parametrize("database_comes_back", ["unpaused", "restarted"])
def test_db_time_limit_frees_every_connection_and_recovers_without_a_restart(
    make_client, proxy: PausableProxy, migrated_db: Engine, contract, database_comes_back: str
):
    client = make_client()
    user = _User.register(client)
    engine = client.app.state.engine
    handed_out = []  # every connection the pool hands out, after its pre-ping
    event.listen(engine, "checkout", lambda connection, *_: handed_out.append(connection))
    # A transaction that waits for an answer when the database stops answering.
    open_transaction = engine.connect()
    open_transaction.execute(text("SELECT 1"))
    cut_off = open_transaction.connection.driver_connection

    proxy.pause(resume_after=LONG_PAUSE_SECONDS)
    for _ in range(2):
        response, elapsed = _timed(lambda: client.get("/health"))
        assert response.status_code == 503
        assert elapsed < C + 1
    with pytest.raises(DBAPIError):
        open_transaction.execute(text("SELECT 2"))
    assert open_transaction.invalidated and cut_off.closed
    open_transaction.close()
    for request in ("GET /entries", "POST /entries"):
        _assert_internal_error(_send(client, user, request), contract)
    last_answer = time.monotonic()

    # Still paused: nothing stays checked out, also not the health checks that gave up.
    time.sleep(max(0.0, last_answer + Q + C + 1 - time.monotonic()))
    assert engine.pool.checkedout() == 0

    if database_comes_back == "restarted":
        proxy.drop_connections()
    handed_out.clear()
    proxy.resume()

    # The cut-off connections were closed: their sessions end once the database answers.
    _wait_until(lambda: _busy_sessions(migrated_db) == 0, seconds=5)
    assert client.get("/health").status_code == 200
    entries = client.get("/entries", headers=user.auth())
    assert entries.status_code == 200
    assert _entry_texts(entries) == [user.entry_text]
    created = client.post("/entries", json=user.entry("written-later"), headers=user.auth())
    assert created.status_code == 201
    assert cut_off not in handed_out
    assert not [connection for connection in handed_out if connection.closed]


# --- One connection stops answering, the database is fine -----------------------------------


def test_db_time_limit_replaces_a_pooled_connection_that_stops_answering(
    make_client, proxy: PausableProxy
):
    client = make_client()
    user = _User.register(client)
    assert client.app.state.engine.pool.checkedin() >= 1

    proxy.pause_open_connections()
    response, elapsed = _timed(lambda: client.get("/entries", headers=user.auth()))

    assert response.status_code == 200
    assert _entry_texts(response) == [user.entry_text]
    assert elapsed < Q + 2


# --- What the limit does not cut ------------------------------------------------------------


def test_db_time_limit_lets_a_slow_call_finish_within_the_limit(direct_engine: Engine):
    with direct_engine.connect() as connection:
        connection.execute(text("SELECT pg_sleep(1)"))
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_db_time_limit_cuts_off_a_call_that_takes_longer_than_the_limit(direct_engine: Engine):
    with direct_engine.connect() as connection:
        started = time.monotonic()
        with pytest.raises(DBAPIError):
            connection.execute(text("SELECT pg_sleep(4)"))
        elapsed = time.monotonic() - started

    assert elapsed < Q + 1
    with direct_engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_db_time_limit_does_not_count_time_between_calls(direct_engine: Engine):
    with direct_engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        time.sleep(Q + 1)  # as while a password is hashed
        assert connection.execute(text("SELECT 2")).scalar_one() == 2


def test_db_time_limit_health_still_answers_within_the_connect_timeout(
    make_client, proxy: PausableProxy, contract
):
    """With a query limit longer than the connect limit, as in production (Q = 10, C = 3)."""
    query_timeout, connect_timeout = 10, 2
    client = make_client(query_timeout=query_timeout, connect_timeout=connect_timeout)
    assert client.get("/health").status_code == 200

    proxy.pause(resume_after=LONG_PAUSE_SECONDS)
    # The first check gets the pooled connection, the second one a new connection.
    for _ in range(2):
        response, elapsed = _timed(lambda: client.get("/health"))

        assert response.status_code == 503
        assert response.json()["code"] == "database_unreachable"
        contract("Error").validate(response.json())
        assert elapsed < connect_timeout + 1
    last_answer = time.monotonic()

    # Still paused: the checks that gave up have freed their connections, after the limits.
    time.sleep(max(0.0, last_answer + query_timeout + connect_timeout + 1 - time.monotonic()))
    assert client.app.state.engine.pool.checkedout() == 0


# --- Errors, logs and contract --------------------------------------------------------------


def test_db_time_limit_error_is_the_shared_500_with_cors_headers_and_safe_telemetry(
    make_client, proxy: PausableProxy, proxied_url: str, contract, capsys
):
    captured = CapturedTelemetry()
    client = make_client(telemetry=captured.telemetry)
    marker = uuid.uuid4().hex[:12]
    statement_value = f"statement-value-{marker}"

    @client.app.get("/test-only/slow-statement")
    def slow_statement(session: Annotated[Session, Depends(get_session)]) -> dict:
        session.execute(
            text("SELECT pg_sleep(:seconds), :value"),
            {"seconds": Q + 2, "value": statement_value},
        )
        return {}

    origin = {"Origin": ALLOWED_ORIGIN}
    healthy = client.get("/health", headers=origin)
    user = _User.register(client, marker)

    # A statement that runs longer than the limit, and a request while the database is paused.
    slow = client.get("/test-only/slow-statement", headers=origin)
    proxy.pause()
    paused = client.get("/entries", headers={**user.auth(), **origin})
    proxy.resume()

    for response in (slow, paused):
        _assert_internal_error(response, contract)
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert _cors_header_values(response) == _cors_header_values(healthy)

    # The `request finished` lines of both: status 500 and the error's class name.
    printed = capsys.readouterr().out
    lines = json_lines(printed)
    failed = [
        line
        for line in lines
        if line["message"] == "request finished" and line["http.response.status_code"] == 500
    ]
    assert [(line["http.route"], line["level"], line["error.type"]) for line in failed] == [
        ("/test-only/slow-statement", "ERROR", "OperationalError"),
        ("/entries", "ERROR", "OperationalError"),
    ]
    exported = [
        dict(log.log_record.attributes)
        for log in captured.logs()
        if log.log_record.body == "request finished"
        and log.log_record.attributes["http.response.status_code"] == 500
    ]
    assert [attributes["error.type"] for attributes in exported] == ["OperationalError"] * 2
    failed_spans = [
        span
        for span in captured.server_spans()
        if span.attributes.get("http.response.status_code") == 500
    ]
    assert [span.name for span in failed_spans] == [
        "GET /test-only/slow-statement",
        "GET /entries",
    ]
    for span in failed_spans:
        assert span.attributes["error.type"] == "OperationalError"
        assert span.status.description is None
        assert span.events == ()

    # No new fields, and no SQL, statement values or exception messages.
    for where, key in captured.attribute_keys():
        allowed = ALLOWED_RESOURCE_KEYS if where == "resource" else ALLOWED_ATTRIBUTE_KEYS
        assert key in allowed, f"{key} in {where}"
    for line in lines:
        assert set(line) <= set(LOG_LINE_KEYS) | ALLOWED_ATTRIBUTE_KEYS, line
    telemetry = captured.everything_as_text() + "\n" + printed
    for forbidden in (
        "SELECT",
        "pg_sleep",
        "[SQL",
        statement_value,
        marker,
        user.token,
        proxied_url,
        "DATABASE_QUERY_TIMEOUT_SECONDS",
        "did not answer",
        "timeout expired",
        "Traceback",
    ):
        assert forbidden not in telemetry, forbidden
