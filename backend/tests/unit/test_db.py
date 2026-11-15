import inspect
import re
import socket
import struct
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import DatabaseCallTimeout, TimeLimitedConnection, create_db_engine, sqlalchemy_url
from app.settings import Settings
from tests.unit.conftest import ALLOWED_ORIGIN


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
    ],
)
def test_plain_postgres_urls_use_the_psycopg_driver(given, expected):
    assert sqlalchemy_url(given) == expected


def test_database_errors_hide_the_values_of_the_statement(settings):
    """AGENTS.md: never log entry text, summaries or passwords, also not through a traceback."""
    engine = create_db_engine(settings)

    assert engine.hide_parameters is True


# --- The time limit for each database call (issue #95) ---------------------------------------

ROOT = Path(__file__).resolve().parents[3]
# A connection the fake database does not answer is closed after this long, so a test of code
# without a time limit fails instead of hanging.
SILENCE_LIMIT_SECONDS = 10
# The shortest DATABASE_QUERY_TIMEOUT_SECONDS.
CALL_TIMEOUT_SECONDS = 1


def _message(kind: bytes, body: bytes = b"") -> bytes:
    return kind + struct.pack("!i", len(body) + 4) + body


class FakeDatabase:
    """A local server that speaks just enough of PostgreSQL's protocol for psycopg.

    It accepts connections and completes the start-up without a password. While `answering` is
    set, it answers each query with an empty result inside a transaction, after
    `answer_delay` seconds. Otherwise it reads the queries but never answers, like a database
    that keeps the connection open and has stopped answering. Unit tests need no PostgreSQL.
    """

    _SSL_OR_GSS_REQUESTS = (80877103, 80877104)

    def __init__(self) -> None:
        self.answering = threading.Event()
        self.answering.set()
        self.answer_delay = 0.0
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self._closed = False
        self.port: int = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    @property
    def url(self) -> str:
        return f"postgresql://fake@127.0.0.1:{self.port}/fake?sslmode=disable&gssencmode=disable"

    @property
    def conninfo(self) -> str:
        return (
            f"host=127.0.0.1 port={self.port} user=fake dbname=fake sslmode=disable "
            "gssencmode=disable connect_timeout=2"
        )

    def close(self) -> None:
        self._closed = True

    def _accept(self) -> None:
        while not self._closed:
            try:
                sock, _ = self._listener.accept()
            except TimeoutError:
                continue
            threading.Thread(target=self._serve, args=(sock,), daemon=True).start()
        self._listener.close()

    def _serve(self, sock: socket.socket) -> None:
        sock.settimeout(SILENCE_LIMIT_SECONDS)
        try:
            self._start_up(sock)
            pending = b""
            while True:
                kind = _receive(sock, 1)
                (length,) = struct.unpack("!i", _receive(sock, 4))
                _receive(sock, length - 4)
                if kind == b"X":  # Terminate
                    return
                if not self.answering.is_set():
                    continue
                if kind == b"Q":  # a simple query
                    time.sleep(self.answer_delay)
                    sock.sendall(_message(b"C", b"OK\0") + _message(b"Z", b"T"))
                elif kind in self._EXTENDED_ANSWERS:
                    pending += self._EXTENDED_ANSWERS[kind]
                elif kind == b"S":  # Sync: the end of an extended query
                    time.sleep(self.answer_delay)
                    sock.sendall(pending + _message(b"Z", b"T"))
                    pending = b""
        except OSError:
            pass  # the client closed the connection, or it was silent for too long
        finally:
            sock.close()

    # Parse, Bind, Describe and Execute, each with its answer.
    _EXTENDED_ANSWERS = {
        b"P": _message(b"1"),
        b"B": _message(b"2"),
        b"D": _message(b"n"),
        b"E": _message(b"C", b"OK\0"),
    }

    def _start_up(self, sock: socket.socket) -> None:
        while True:
            (length,) = struct.unpack("!i", _receive(sock, 4))
            (code,) = struct.unpack("!i", _receive(sock, length - 4)[:4])
            if code not in self._SSL_OR_GSS_REQUESTS:
                break
            sock.sendall(b"N")  # no TLS, no GSSAPI encryption
        answer = _message(b"R", struct.pack("!i", 0))  # authentication OK
        for name, value in (
            ("server_version", "18.0"),
            ("server_encoding", "UTF8"),
            ("client_encoding", "UTF8"),
            ("standard_conforming_strings", "on"),
            ("integer_datetimes", "on"),
            ("DateStyle", "ISO, MDY"),
            ("TimeZone", "UTC"),
        ):
            answer += _message(b"S", f"{name}\0{value}\0".encode())
        answer += _message(b"K", struct.pack("!ii", 1, 1)) + _message(b"Z", b"I")
        sock.sendall(answer)


def _receive(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionResetError
        data += chunk
    return data


@pytest.fixture
def fake_database() -> Iterator[FakeDatabase]:
    database = FakeDatabase()
    yield database
    database.close()


def _time_limited_connection(database: FakeDatabase) -> TimeLimitedConnection:
    """A connection to the fake database, as `create_db_engine` opens it."""
    connection = TimeLimitedConnection.connect(database.conninfo)
    connection.call_timeout_seconds = CALL_TIMEOUT_SECONDS
    return connection


def _settings_for(database_url: str, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        **overrides,
    )


def test_db_time_limit_relies_on_psycopg_internals_that_an_upgrade_may_change():
    """`TimeLimitedConnection` uses parts of psycopg that are not public API.

    psycopg's `Connection.wait(gen, interval, timeout)` raises `errors._WaitTimeout` (an
    `OperationalError`) when `timeout` runs out. If an upgrade renames or changes either, this
    test fails; the tests below fail when psycopg stops running its calls through `wait`.
    """
    assert issubclass(psycopg.errors._WaitTimeout, psycopg.OperationalError)
    parameters = inspect.signature(psycopg.Connection.wait).parameters
    assert list(parameters) == ["self", "gen", "interval", "timeout"]
    assert parameters["timeout"].default is None


def test_db_time_limit_engine_opens_time_limited_connections(settings: Settings):
    engine = create_db_engine(settings.model_copy(update={"database_query_timeout_seconds": 7}))

    # Waiting for a free connection in the pool has the same limit.
    assert engine.pool.timeout() == 7


def test_db_time_limit_engine_cuts_off_a_database_that_stops_answering(
    fake_database: FakeDatabase,
):
    fake_database.answering.clear()
    engine = create_db_engine(
        _settings_for(fake_database.url, database_query_timeout_seconds=CALL_TIMEOUT_SECONDS)
    )

    started = time.monotonic()
    with pytest.raises(OperationalError) as error:
        # The first call on a new connection gets no answer.
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    elapsed = time.monotonic() - started

    assert isinstance(error.value.orig, DatabaseCallTimeout)
    assert elapsed < CALL_TIMEOUT_SECONDS + 1
    assert engine.pool.checkedout() == 0
    engine.dispose()


@pytest.mark.parametrize("call", ["statement", "commit", "rollback", "pre-ping"])
def test_db_time_limit_cuts_off_each_kind_of_call_and_closes_the_connection(
    fake_database: FakeDatabase, settings: Settings, call: str
):
    connection = _time_limited_connection(fake_database)
    if call != "pre-ping":
        connection.execute("SELECT 1")  # starts a transaction
        assert connection.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS
    dialect = create_db_engine(settings).dialect
    fake_database.answering.clear()

    started = time.monotonic()
    with pytest.raises(DatabaseCallTimeout) as error:
        if call == "statement":
            connection.execute("SELECT 2")
        elif call == "commit":
            connection.commit()
        elif call == "rollback":
            connection.rollback()
        else:
            dialect.do_ping(connection)  # what the pool runs before handing a connection out
    elapsed = time.monotonic() - started

    assert elapsed < CALL_TIMEOUT_SECONDS + 1
    # Closed, so SQLAlchemy counts the error as a disconnect and discards the connection.
    assert connection.closed and connection.broken
    assert dialect.is_disconnect(error.value, connection, None)
    # The message names the setting, and never the statement.
    assert "DATABASE_QUERY_TIMEOUT_SECONDS" in str(error.value)
    assert "SELECT" not in str(error.value)


def test_db_time_limit_counts_only_the_wait_for_each_answer(fake_database: FakeDatabase):
    connection = _time_limited_connection(fake_database)
    # The first statement of a transaction waits twice: for psycopg's BEGIN and for itself.
    fake_database.answer_delay = CALL_TIMEOUT_SECONDS * 0.3

    # A slow answer within the limit is not cut off.
    connection.execute("SELECT 1")
    # Time between calls does not count.
    time.sleep(CALL_TIMEOUT_SECONDS + 0.5)
    connection.execute("SELECT 2")
    connection.commit()

    assert not connection.closed
    connection.close()


def test_db_time_limit_without_a_limit_set_waits_like_psycopg(fake_database: FakeDatabase):
    """A connection that is not opened by `create_db_engine` keeps psycopg's behaviour."""
    connection = TimeLimitedConnection.connect(fake_database.conninfo)
    fake_database.answer_delay = 0.2

    connection.execute("SELECT 1")

    assert connection.call_timeout_seconds is None
    connection.close()


def test_db_time_limit_migrations_keep_their_own_engine_without_the_limit():
    """A deploy or a wake-up is never cut off halfway through a migration."""
    env = (ROOT / "backend" / "migrations" / "env.py").read_text(encoding="utf-8")

    assert "create_db_engine" not in env
    assert "TimeLimitedConnection" not in env
    assert "engine = create_engine(_database_url(), poolclass=pool.NullPool)" in env


def _comment_above(lines: list[str], line: str) -> str:
    """The comment lines right above `line` in .env.example, as one text."""
    end = lines.index(line)
    start = end
    while lines[start - 1].startswith("#"):
        start -= 1
    return " ".join(comment.removeprefix("#").strip() for comment in lines[start:end])


def test_db_time_limit_setting_is_documented_in_env_example():
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    variables = [line for line in lines if re.match(r"[A-Z_]+=", line)]

    # Right after DATABASE_CONNECT_TIMEOUT_SECONDS, with the default as its value.
    position = variables.index("DATABASE_CONNECT_TIMEOUT_SECONDS=3")
    assert variables[position + 1] == "DATABASE_QUERY_TIMEOUT_SECONDS=10"
    query = _comment_above(lines, "DATABASE_QUERY_TIMEOUT_SECONDS=10")
    assert query.startswith("Optional, default 10. ")
    for phrase in (
        "one database call",
        "a statement with its result, a commit or a rollback",
        "free connection in the pool",
        '"Something went wrong" error',
        "Whole number from 1 to 600.",
        "Opening a connection and the health check use DATABASE_CONNECT_TIMEOUT_SECONDS.",
    ):
        assert phrase in query
    connect = _comment_above(lines, "DATABASE_CONNECT_TIMEOUT_SECONDS=3")
    assert "limits opening every new connection" in connect


def test_db_time_limit_setting_is_passed_by_docker_compose():
    """Through the backend's `env_file` (issue #61), with the default from .env.example."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    backend = compose["services"]["backend"]
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()

    assert backend["env_file"] == ".env"
    assert "DATABASE_QUERY_TIMEOUT_SECONDS" not in backend["environment"]
    assert "DATABASE_QUERY_TIMEOUT_SECONDS=10" in lines
