import socket
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.health import check_database
from app.main import create_app
from app.settings import Settings
from tests.unit.conftest import ALLOWED_ORIGIN


def _client_for(database_url: str, timeout_seconds: int = 2) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        database_connect_timeout_seconds=timeout_seconds,
    )
    return TestClient(create_app(settings))


@pytest.fixture
def closed_port() -> int:
    """A local port with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def silent_port() -> Iterator[int]:
    """A local port that accepts TCP connections but never answers, like a stuck database."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(5)
        yield sock.getsockname()[1]


def test_health_returns_documented_body_when_database_is_up(client: TestClient, contract):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    contract("Health").validate(response.json())


def test_health_reports_unreachable_database(closed_port: int, contract):
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{closed_port}/winlog")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    contract("Error").validate(response.json())


def test_health_gives_up_after_the_timeout_instead_of_hanging(silent_port: int):
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{silent_port}/winlog", 2)

    started = time.monotonic()
    response = client.get("/health")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    assert elapsed < 10


def test_health_gives_up_when_an_open_connection_never_answers(
    closed_port: int, monkeypatch: pytest.MonkeyPatch
):
    """Like a pooled connection to a paused database: no error, no answer, no time limit.

    The integration tests reproduce this with real PostgreSQL behind a paused proxy.
    """
    client = _client_for(f"postgresql://winlog:x@127.0.0.1:{closed_port}/winlog", 2)
    answer = threading.Event()

    def connect_that_never_answers():
        answer.wait(15)  # the test fails instead of hanging if nothing gives up earlier
        raise OperationalError("SELECT 1", {}, ConnectionError("no answer"))

    monkeypatch.setattr(client.app.state.engine, "connect", connect_that_never_answers)
    try:
        started = time.monotonic()
        response = client.get("/health")
        elapsed = time.monotonic() - started
    finally:
        answer.set()

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    assert elapsed < 5


def test_module_level_app_serves_health():
    """`uvicorn app.main:app` uses this object."""
    from app.main import app

    app.dependency_overrides[check_database] = lambda: True
    try:
        assert TestClient(app).get("/health").status_code == 200
    finally:
        app.dependency_overrides.clear()
