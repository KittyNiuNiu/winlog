import time
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url

from app.db import sqlalchemy_url
from app.main import create_app
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN
from tests.integration.pausable_proxy import PausableProxy

TIMEOUT_SECONDS = 2


def test_health_returns_200_against_the_real_test_database(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "commit": None}


def _wait_until(condition: Callable[[], bool], seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.05)


@pytest.fixture
def proxy(test_database_url: str) -> Iterator[PausableProxy]:
    url = make_url(sqlalchemy_url(test_database_url))
    proxy = PausableProxy(url.host or "localhost", url.port or 5432)
    yield proxy
    proxy.close()


@pytest.fixture
def proxied_client(test_database_url: str, proxy: PausableProxy) -> Iterator[TestClient]:
    """The app, connected to the test database through the proxy."""
    url = make_url(sqlalchemy_url(test_database_url)).set(host="127.0.0.1", port=proxy.port)
    settings = Settings(
        _env_file=None,
        database_url=url.render_as_string(hide_password=False),
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        database_connect_timeout_seconds=TIMEOUT_SECONDS,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def _get_health_and_time_it(client: TestClient) -> tuple[int, dict, float]:
    started = time.monotonic()
    response = client.get("/health")
    return response.status_code, response.json(), time.monotonic() - started


@pytest.mark.parametrize("database_comes_back", ["unpaused", "restarted"])
def test_health_gives_up_when_a_pooled_connection_stops_answering(
    proxy: PausableProxy, proxied_client: TestClient, contract, database_comes_back: str
):
    pool = proxied_client.app.state.engine.pool
    assert proxied_client.get("/health").status_code == 200
    assert pool.checkedin() == 1  # an idle connection now waits in the pool

    proxy.pause()
    # The first check gets the pooled connection, the second one a new connection.
    for _ in range(2):
        status, body, elapsed = _get_health_and_time_it(proxied_client)

        assert status == 503
        assert body["code"] == "database_unreachable"
        contract("Error").validate(body)
        assert elapsed < TIMEOUT_SECONDS + 3

    if database_comes_back == "restarted":
        proxy.drop_connections()
    proxy.resume()

    # The check that gave up finishes in the background and gives its connection back (or
    # SQLAlchemy discards it, if it broke). The pool then works again.
    _wait_until(lambda: pool.checkedout() == 0)
    for _ in range(3):
        assert proxied_client.get("/health").status_code == 200
