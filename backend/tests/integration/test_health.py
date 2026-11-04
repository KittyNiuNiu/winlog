import socket
import threading
import time
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url

from app.db import sqlalchemy_url
from app.main import create_app
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

TIMEOUT_SECONDS = 2
# A paused proxy resumes by itself after this long, so a health check without a time limit
# makes the test fail instead of hang.
PAUSE_LIMIT_SECONDS = 15


def test_health_returns_200_against_the_real_test_database(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


class PausableProxy:
    """A TCP proxy in front of the test database that can stop answering.

    While paused, it keeps every connection open and accepts new ones, but passes no bytes
    on, like `docker compose pause db`: the TCP connection stays up and nothing replies.
    """

    def __init__(self, host: str, port: int) -> None:
        self._target = (host, port)
        self._forwarding = threading.Event()
        self._forwarding.set()
        self._resume_timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._sockets: list[socket.socket] = []
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self._closed = False
        self.port: int = self._listener.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def pause(self) -> None:
        self._forwarding.clear()
        self._resume_timer = threading.Timer(PAUSE_LIMIT_SECONDS, self.resume)
        self._resume_timer.start()

    def resume(self) -> None:
        if self._resume_timer is not None:
            self._resume_timer.cancel()
        self._forwarding.set()

    def drop_connections(self) -> None:
        """Close every open connection, as a database restart does."""
        with self._lock:
            sockets, self._sockets = self._sockets, []
        for sock in sockets:
            _close(sock)

    def close(self) -> None:
        self._closed = True
        self.drop_connections()
        self.resume()

    def _accept(self) -> None:
        while not self._closed:
            try:
                client, _ = self._listener.accept()
            except TimeoutError:
                continue
            upstream = socket.create_connection(self._target)
            with self._lock:
                self._sockets += [client, upstream]
            for source, destination in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pump, args=(source, destination), daemon=True).start()
        self._listener.close()

    def _pump(self, source: socket.socket, destination: socket.socket) -> None:
        try:
            while data := source.recv(65536):
                self._forwarding.wait()  # hold the bytes while paused
                destination.sendall(data)
        except OSError:
            pass  # the connection was dropped
        finally:
            _close(source)
            _close(destination)


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)  # wakes up a thread blocked in recv()
    except OSError:
        pass
    sock.close()


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
