"""The HSTS header against real PostgreSQL and a real server (issue #99).

`HSTS_MAX_AGE_SECONDS` (H, default 31,536,000) and app/hsts.py, for the responses that need a
database: `GET /health` 200 and 503, `GET /entries` 200, `POST /entries` 201 and the Markdown
download. A real uvicorn server (h11, as `start.sh` starts it) shows that the header goes out
exactly once on the wire, and that uvicorn's own 400 for an over-long request head, which never
reaches the app, has none. The header has no requirement ID, so every test starts with
`test_hsts_`. The responses without a database are in tests/unit/test_hsts.py. No AI call.
"""

import socket
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.main import create_app
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN
from tests.integration.test_entries import _token, _user
from tests.integration.test_request_body_limit import LiveServer, _raw_request

DEFAULT = 31_536_000
HEADER = "strict-transport-security"
EXPECTED = "max-age=31536000; includeSubDomains"
ENTRY = {
    "text": "Shipped the release.",
    "date": "2026-10-20",
    "category": "Achievement",
    "tags": ["Release"],
    "result_impact": "Two teams use it.",
}
# Fields of a new entry that differ from one entry to the next.
GENERATED = {"id", "created_at", "updated_at"}


def _settings(database_url: str, max_age: int, **values) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        hsts_max_age_seconds=max_age,
        **values,
    )


@pytest.fixture
def make_client(test_database_url: str, migrated_db: Engine) -> Callable[[int], TestClient]:
    """A client for the app with the given H, connected to the migrated test database."""

    def make(max_age: int) -> TestClient:
        return TestClient(create_app(_settings(test_database_url, max_age)))

    return make


@pytest.fixture
def token(migrated_db: Engine) -> str:
    return _token(migrated_db, _user(migrated_db, "alice@example.com"))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Origin": ALLOWED_ORIGIN}


def _hsts(response) -> list[str]:
    return response.headers.get_list(HEADER)


def _others(response) -> list[tuple[str, str]]:
    """Every header but `Strict-Transport-Security`, in order."""
    return [(name, value) for name, value in response.headers.multi_items() if name != HEADER]


def _create(client: TestClient, token: str):
    return client.post("/entries", json=ENTRY, headers=_auth(token))


def _reads(client: TestClient, token: str) -> dict:
    """The responses the issue names that need the database and only read it."""
    return {
        "health_200": client.get("/health", headers={"Origin": ALLOWED_ORIGIN}),
        "list_entries_200": client.get("/entries", headers=_auth(token)),
        "export_markdown_200": client.get("/export/markdown", headers=_auth(token)),
    }


@pytest.mark.parametrize(
    ("max_age", "expected"),
    [(DEFAULT, [EXPECTED]), (1, ["max-age=1; includeSubDomains"]), (0, [])],
)
def test_hsts_header_on_responses_that_need_the_database(make_client, token, max_age, expected):
    client = make_client(max_age)
    responses = {"create_entry_201": _create(client, token), **_reads(client, token)}

    assert {name: response.status_code for name, response in responses.items()} == {
        "create_entry_201": 201,
        "health_200": 200,
        "list_entries_200": 200,
        "export_markdown_200": 200,
    }
    assert responses["health_200"].json() == {"status": "ok", "database": "ok"}
    assert [entry["text"] for entry in responses["list_entries_200"].json()["entries"]] == [
        ENTRY["text"]
    ]
    export = responses["export_markdown_200"]
    assert export.headers["content-disposition"].startswith('attachment; filename="winlog-export-')
    assert ENTRY["text"] in export.text
    for name, response in responses.items():
        assert _hsts(response) == expected, name


def test_hsts_header_is_the_only_change_to_responses_that_need_the_database(make_client, token):
    """Status, body, CORS headers and Content-Disposition are as with H = 0."""
    on_client, off_client = make_client(DEFAULT), make_client(0)

    # Two new entries: the same but for their ids and times.
    on, off = _create(on_client, token), _create(off_client, token)
    assert on.status_code == off.status_code == 201
    assert {k: v for k, v in on.json().items() if k not in GENERATED} == {
        k: v for k, v in off.json().items() if k not in GENERATED
    }
    assert [name for name, _ in _others(on)] == [name for name, _ in off.headers.multi_items()]
    assert _hsts(on) == [EXPECTED] and _hsts(off) == []

    # Both apps read the same data, so everything but the header is the same.
    with_header, without = _reads(on_client, token), _reads(off_client, token)
    for name in with_header:
        on, off = with_header[name], without[name]
        assert on.status_code == off.status_code == 200, name
        assert on.content == off.content, name
        assert _others(on) == off.headers.multi_items(), name
        assert _hsts(on) == [EXPECTED] and _hsts(off) == [], name
    assert len(without["list_entries_200"].json()["entries"]) == 2
    export = with_header["export_markdown_200"]
    assert export.headers["content-disposition"].startswith('attachment; filename="winlog-export-')
    assert export.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "content-disposition" in export.headers["access-control-expose-headers"].lower()


def _closed_port() -> int:
    """A local port that nothing listens on, so a connection to it is refused at once."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.parametrize(("max_age", "expected"), [(DEFAULT, [EXPECTED]), (0, [])])
def test_hsts_header_on_health_503_when_the_database_is_unreachable(max_age, expected, contract):
    url = f"postgresql://winlog:unused@127.0.0.1:{_closed_port()}/winlog"
    app = create_app(_settings(url, max_age, database_connect_timeout_seconds=2))
    try:
        response = TestClient(app).get("/health")
    finally:
        app.state.engine.dispose()

    assert response.status_code == 503
    assert response.json()["code"] == "database_unreachable"
    contract("Error").validate(response.json())
    assert _hsts(response) == expected


# --- A real server ------------------------------------------------------------------------


@pytest.fixture
def serve(test_database_url: str, migrated_db: Engine) -> Iterator[Callable[[int], LiveServer]]:
    """Start the app with the given H on a real uvicorn server; stopped after the test."""
    servers: list[LiveServer] = []

    def start(max_age: int) -> LiveServer:
        server = LiveServer(create_app(_settings(test_database_url, max_age))).__enter__()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.__exit__()
        server.app.state.engine.dispose()


def _head_lines(answer: bytes) -> tuple[bytes, list[tuple[str, str]]]:
    """The status line and the headers of a raw HTTP/1.1 answer, names in lower case."""
    head = answer.partition(b"\r\n\r\n")[0].decode("latin-1")
    status_line, *lines = head.split("\r\n")
    headers = [line.split(":", 1) for line in lines]
    return status_line.encode(), [(name.strip().lower(), value.strip()) for name, value in headers]


def _request_head(method: str, path: str, extra: str = "") -> bytes:
    return (
        f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n{extra}Connection: close\r\n\r\n".encode()
    )


@pytest.mark.parametrize(("max_age", "expected"), [(DEFAULT, [EXPECTED]), (0, [])])
def test_hsts_header_goes_over_the_wire_exactly_once_from_a_real_server(serve, max_age, expected):
    server = serve(max_age)
    preflight = (
        f"Origin: {ALLOWED_ORIGIN}\r\nAccess-Control-Request-Method: POST\r\n"
        "Access-Control-Request-Headers: Content-Type\r\n"
    )

    for head, status in (
        (_request_head("GET", "/health"), b"HTTP/1.1 200 OK"),
        (_request_head("GET", "/no-such-path"), b"HTTP/1.1 404 Not Found"),
        (_request_head("OPTIONS", "/entries", preflight), b"HTTP/1.1 200 OK"),
    ):
        status_line, headers = _head_lines(_raw_request(server, head, split_at=None))

        assert status_line == status
        assert [value for name, value in headers if name == HEADER] == expected


def test_hsts_header_is_not_on_uvicorns_own_400_for_an_over_long_request_head(serve):
    """More than 16 KiB of head before it is complete: uvicorn answers before the app runs."""
    server = serve(DEFAULT)
    head = _request_head("GET", "/health", f"X-Padding: {'x' * 17_000}\r\n")

    answer = _raw_request(server, head, split_at=16_500)

    status_line, headers = _head_lines(answer)
    assert status_line == b"HTTP/1.1 400 Bad Request"
    assert answer.endswith(b"Invalid HTTP request received.")
    assert HEADER not in [name for name, _ in headers]
    # The app itself still sends it.
    _, headers = _head_lines(_raw_request(server, _request_head("GET", "/health"), None))
    assert [value for name, value in headers if name == HEADER] == [EXPECTED]
