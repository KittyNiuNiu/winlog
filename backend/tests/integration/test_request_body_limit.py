"""The limit on the size of a request body, against real PostgreSQL (issue #88).

`REQUEST_BODY_MAX_BYTES` (L, default 262,144) and app/body_limit.py. Requests go through a
real uvicorn server, started as `start.sh` starts it (h11, because httptools is not
installed), so a body is sent with `Content-Length` or chunked exactly as a client sends it.
A padded body is a valid JSON body made exactly N bytes long with spaces after its closing
brace. An escaped body sends every character as a JSON `\\u` escape, so an emoji is 12 bytes.
The body limit has no requirement ID, so every test starts with `test_request_body_limit_`.
Every AI call goes to the mock provider.
"""

import datetime as dt
import http.client
import importlib.util
import json
import socket
import threading
import time
import urllib.parse
import uuid
from collections.abc import Callable, Iterator

import pytest
import uvicorn
from fastapi import FastAPI
from sqlalchemy import Engine, func, insert, select

from app.ai import MockProvider
from app.auth import hash_token
from app.main import create_app
from app.models import (
    AiUsage,
    AiUsageGlobal,
    Entry,
    EntryTag,
    LoginAttempt,
    Summary,
    Tag,
    Token,
    User,
)
from app.settings import Settings
from app.telemetry import Telemetry
from tests.integration.conftest import ALLOWED_ORIGIN
from tests.telemetry_capture import CapturedTelemetry

DEFAULT = 262_144
TOO_LARGE = {"code": "request_too_large", "message": "The request body is too large."}
DAY = "2026-01-10"
EMOJI = "🎉"
SECRET = "body-limit-marker-9c4d"


# --- A real server ------------------------------------------------------------------------


class LiveServer:
    """The app served by uvicorn on a free local port, in a background thread."""

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]
        # The server's own defaults, as start.sh runs it; no lifespan, so the test owns the app.
        self.server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_config=None))
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True
        )

    def __enter__(self) -> "LiveServer":
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.01)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(10)
        self.socket.close()

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        *,
        chunked: bool = False,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Send one request. A chunked body goes in 8 KiB chunks without Content-Length."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            all_headers = {"Content-Type": "application/json", **(headers or {})}
            if chunked:
                assert body is not None
                chunks = (body[start : start + 8192] for start in range(0, len(body), 8192))
                connection.request(method, path, chunks, all_headers, encode_chunked=True)
            else:
                connection.request(method, path, body, all_headers)
            response = connection.getresponse()
            return (
                response.status,
                {name.lower(): value for name, value in response.getheaders()},
                response.read(),
            )
        finally:
            connection.close()


@pytest.fixture
def serve(test_database_url: str, migrated_db: Engine) -> Iterator[Callable[..., LiveServer]]:
    """Start the app with the given settings on a real server; stopped after the test."""
    servers: list[LiveServer] = []

    def start(telemetry: Telemetry | None = None, **settings: int) -> LiveServer:
        app = create_app(
            Settings(
                _env_file=None,
                database_url=test_database_url,
                cors_allowed_origins=[ALLOWED_ORIGIN],
                ai_provider="mock",
                **settings,
            ),
            telemetry=telemetry,
        )
        server = LiveServer(app).__enter__()
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.__exit__()
        server.app.state.engine.dispose()


@pytest.fixture
def server(serve) -> LiveServer:
    return serve()


# --- Helpers ------------------------------------------------------------------------------


def _user(engine: Engine) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(User)
            .values(email=f"user-{uuid.uuid4()}@example.com", password_hash="hash")
            .returning(User.id)
        ).scalar_one()


def _token(engine: Engine, user_id: uuid.UUID) -> str:
    token = f"test-token-{uuid.uuid4()}"
    with engine.begin() as connection:
        connection.execute(
            insert(Token).values(
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
            )
        )
    return token


@pytest.fixture
def token(migrated_db: Engine) -> str:
    return _token(migrated_db, _user(migrated_db))


def _auth(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _padded(payload: dict, size: int) -> bytes:
    """`payload` as JSON, made exactly `size` bytes long with spaces after the closing brace."""
    body = json.dumps(payload).encode()
    assert len(body) <= size
    return body + b" " * (size - len(body))


def _entry(**fields) -> dict:
    return {"text": f"Shipped it. {SECRET}", "date": DAY, "category": "Achievement", **fields}


def _escaped(payload: dict) -> bytes:
    """`payload` as compact JSON with every character of every value sent as a `\\u` escape."""

    def escape(value: str) -> str:
        units = value.encode("utf-16-be")
        return "".join(
            f"\\u{int.from_bytes(units[i : i + 2], 'big'):04x}" for i in range(0, len(units), 2)
        )

    def encode(value: object) -> str:
        if isinstance(value, str):
            return f'"{escape(value)}"'
        if isinstance(value, list):
            return "[" + ",".join(encode(item) for item in value) + "]"
        if isinstance(value, dict):
            return "{" + ",".join(f"{json.dumps(k)}:{encode(v)}" for k, v in value.items()) + "}"
        return json.dumps(value)

    body = encode(payload).encode("ascii")
    assert json.loads(body) == payload
    return body


def _counts(engine: Engine) -> dict[str, int]:
    tables = {
        "entries": Entry,
        "tags": Tag,
        "entry_tags": EntryTag,
        "summaries": Summary,
        "tokens": Token,
        "users": User,
        "login_attempts": LoginAttempt,
        "ai_usage": AiUsage,
        "ai_usage_global": AiUsageGlobal,
    }
    with engine.connect() as connection:
        return {
            name: connection.execute(select(func.count()).select_from(model)).scalar_one()
            for name, model in tables.items()
        }


def _mock(server: LiveServer) -> MockProvider:
    provider = server.app.state.ai_provider
    assert isinstance(provider, MockProvider)
    return provider


def _assert_too_large(answer: tuple[int, dict[str, str], bytes]) -> None:
    status, headers, body = answer
    assert status == 413, body
    assert headers["content-type"] == "application/json"
    assert json.loads(body) == TOO_LARGE
    assert b"Content Too Large" not in body


# --- The server ---------------------------------------------------------------------------


def test_request_body_limit_server_runs_on_h11_as_in_production():
    """Without httptools, uvicorn uses h11 (do not add uvicorn[standard], issue #88)."""
    assert importlib.util.find_spec("httptools") is None
    config = uvicorn.Config(FastAPI())
    config.load()
    assert config.http_protocol_class.__name__ == "H11Protocol"


# --- Exactly at the limit, and one byte more ---------------------------------------------


@pytest.mark.parametrize("chunked", [False, True], ids=["content_length", "chunked"])
def test_request_body_limit_padded_entry_of_exactly_the_limit_is_created_and_one_more_is_413(
    server, migrated_db, token, contract, chunked
):
    status, _, body = server.request(
        "POST", "/entries", _padded(_entry(), DEFAULT), chunked=chunked, headers=_auth(token)
    )
    assert status == 201, body
    contract("Entry").validate(json.loads(body))
    before = _counts(migrated_db)

    answer = server.request(
        "POST", "/entries", _padded(_entry(), DEFAULT + 1), chunked=chunked, headers=_auth(token)
    )

    _assert_too_large(answer)
    contract("Error").validate(json.loads(answer[2]))
    assert _counts(migrated_db) == before


@pytest.mark.parametrize("chunked", [False, True], ids=["content_length", "chunked"])
def test_request_body_limit_uses_the_setting(serve, migrated_db, token, chunked):
    server = serve(request_body_max_bytes=131_072)

    status, _, body = server.request(
        "POST", "/entries", _padded(_entry(), 131_072), chunked=chunked, headers=_auth(token)
    )
    assert status == 201, body
    before = _counts(migrated_db)

    _assert_too_large(
        server.request(
            "POST", "/entries", _padded(_entry(), 131_073), chunked=chunked, headers=_auth(token)
        )
    )
    assert _counts(migrated_db) == before


# --- Content-Length over the limit ------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/entries"),
        ("POST", "/auth/logout"),
        ("POST", "/entries"),
        ("POST", "/summaries"),
        ("POST", "/suggestions"),
        ("DELETE", "/account"),
        ("GET", "/no-such-path"),
    ],
)
@pytest.mark.parametrize("with_token", [True, False], ids=["valid_token", "no_token"])
def test_request_body_limit_content_length_over_the_limit_is_413_on_every_method_and_path(
    server, migrated_db, token, method, path, with_token
):
    body = _padded(
        {"period_start": "2026-01-01", "period_end": "2026-01-31", "text": SECRET},
        DEFAULT + 1,
    )
    before = _counts(migrated_db)

    _assert_too_large(
        server.request(method, path, body, headers=_auth(token if with_token else None))
    )

    # Nothing saved or changed, and no AI call: the token still works after the logout.
    assert _counts(migrated_db) == before
    assert _mock(server).suggest_calls == [] and _mock(server).summarise_calls == []
    status, _, _ = server.request("GET", "/entries", headers=_auth(token))
    assert status == 200


def test_request_body_limit_413_has_the_cors_headers_of_other_errors(server, token):
    origin = {"Origin": ALLOWED_ORIGIN}
    _, other, _ = server.request("GET", "/no-such-path", headers=origin)

    for chunked in (False, True):
        answer = server.request(
            "POST",
            "/entries",
            _padded(_entry(), DEFAULT + 1),
            chunked=chunked,
            headers={**origin, **_auth(token)},
        )

        _assert_too_large(answer)
        cors = {k: v for k, v in answer[1].items() if k.startswith("access-control-")}
        assert cors["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert cors == {k: v for k, v in other.items() if k.startswith("access-control-")}


# --- Chunked bodies over the limit ------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "with_token", "payload"),
    [
        ("/entries", True, _entry()),
        ("/entries", False, _entry()),
        ("/auth/login", False, {"email": "a@example.com", "password": f"Wrong-{SECRET}-1"}),
    ],
    ids=["entry_with_token", "entry_without_token", "login"],
)
def test_request_body_limit_chunked_body_over_the_limit_is_413(
    server, migrated_db, token, path, with_token, payload
):
    before = _counts(migrated_db)

    for size in (DEFAULT + 1, 3 * DEFAULT):
        answer = server.request(
            "POST",
            path,
            _padded(payload, size),
            chunked=True,
            headers=_auth(token if with_token else None),
        )

        _assert_too_large(answer)
    # No entry, no tag, no failed login attempt counted.
    assert _counts(migrated_db) == before


def test_request_body_limit_chunked_summary_and_suggestion_make_no_ai_call(
    server, migrated_db, token
):
    before = _counts(migrated_db)
    period = {"period_start": "2026-01-01", "period_end": "2026-01-31"}

    _assert_too_large(
        server.request(
            "POST", "/summaries", _padded(period, DEFAULT + 1), chunked=True, headers=_auth(token)
        )
    )
    _assert_too_large(
        server.request(
            "POST",
            "/suggestions",
            _padded({"text": SECRET}, DEFAULT + 1),
            chunked=True,
            headers=_auth(token),
        )
    )

    assert _mock(server).suggest_calls == [] and _mock(server).summarise_calls == []
    assert _counts(migrated_db) == before


# --- The largest valid requests ---------------------------------------------------------


def test_request_body_limit_largest_summary_edit_is_saved(server, migrated_db, token):
    entry = {"text": "Shipped it.", "date": DAY, "category": "Achievement"}
    status, _, _ = server.request(
        "POST", "/entries", json.dumps(entry).encode(), headers=_auth(token)
    )
    assert status == 201
    period = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
    status, _, created = server.request(
        "POST", "/summaries", json.dumps(period).encode(), headers=_auth(token)
    )
    assert status == 201, created
    summary_id = json.loads(created)["id"]
    body = _escaped({"text": EMOJI * 10_000})
    assert len(body) == 120_011

    status, _, edited = server.request(
        "PATCH", f"/summaries/{summary_id}", body, headers=_auth(token)
    )

    assert status == 200, edited
    assert json.loads(edited)["text"] == EMOJI * 10_000
    with migrated_db.connect() as connection:
        saved = connection.execute(
            select(Summary.text).where(Summary.id == uuid.UUID(summary_id))
        ).scalar_one()
    assert saved == EMOJI * 10_000


def test_request_body_limit_largest_entry_update_is_saved(server, token):
    status, _, created = server.request(
        "POST", "/entries", json.dumps(_entry()).encode(), headers=_auth(token)
    )
    assert status == 201
    entry_id = json.loads(created)["id"]
    tags = [f"{number}" + EMOJI * 39 for number in range(10)]
    payload = _entry(text=EMOJI * 2_000, result_impact=EMOJI * 500, tags=tags)
    body = _escaped(payload)
    # About 35 KB, far below the default limit.
    assert 34_000 < len(body) < 36_000

    status, _, updated = server.request("PUT", f"/entries/{entry_id}", body, headers=_auth(token))

    assert status == 200, updated
    entry = json.loads(updated)
    assert (entry["text"], entry["result_impact"]) == (EMOJI * 2_000, EMOJI * 500)
    assert sorted(entry["tags"]) == sorted(tags)


# --- The request line and headers (uvicorn) ---------------------------------------------


def _largest_filter_query(tag_count: int) -> str:
    """Both dates, all 4 categories and `tag_count` names of 40 emoji, percent-encoded."""
    params = [("start_date", "2026-01-01"), ("end_date", "2026-12-31")]
    params += [("category", c) for c in ("Achievement", "Learning", "Feedback", "Side project")]
    params += [("tag", f"{number:02d}" + EMOJI * 38) for number in range(tag_count)]
    return "/entries?" + urllib.parse.urlencode(params)


def test_request_body_limit_largest_valid_filter_url_fits_the_request_line_limit(server, token):
    path = _largest_filter_query(20)
    assert 9_000 < len(path) < 10_000

    status, _, body = server.request("GET", path, headers=_auth(token))
    assert status == 200, body

    status, _, body = server.request("GET", _largest_filter_query(21), headers=_auth(token))
    assert status == 422, body
    assert [item["field"] for item in json.loads(body)["fields"]] == ["tag"]


# Uvicorn's soft 16 KiB limit on the request line and headers (amended criterion, 2026-11-15).
# The first piece of a request sent in two pieces: more than 16 KiB, but not yet complete.
FIRST_PIECE = 16_500


def _head(path: str, token: str) -> bytes:
    """A complete GET request: request line and headers, without a body."""
    return (
        f"GET {path} HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {token}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()


def _about_17_kb(token: str) -> bytes:
    """The largest valid filter and an unknown query parameter: about 17 KB in all."""
    path = _largest_filter_query(20)
    head = _head(f"{path}&unknown={'x' * (17_000 - len(path) - 150)}", token)
    assert 16_384 < FIRST_PIECE < len(head) < 17_500
    return head


def _raw_request(server: LiveServer, head: bytes, split_at: int | None) -> bytes:
    """Send a request as raw bytes, in one `sendall` or in two pieces, and return the answer."""
    with socket.create_connection(("127.0.0.1", server.port), timeout=30) as connection:
        if split_at is None:
            connection.sendall(head)
        else:
            connection.sendall(head[:split_at])
            time.sleep(0.2)
            connection.sendall(head[split_at:])
        answer = b""
        while chunk := connection.recv(65536):
            answer += chunk
    return answer


def _finished_lines(captured: CapturedTelemetry) -> list:
    return [log for log in captured.logs() if log.log_record.body == "request finished"]


def test_request_body_limit_about_17_kb_in_two_pieces_gets_uvicorns_plain_text_400(serve, token):
    """More than 16 KiB arrived before the request was complete: refused before the app runs."""
    captured = CapturedTelemetry()
    server = serve(telemetry=captured.telemetry)

    answer = _raw_request(server, _about_17_kb(token), split_at=FIRST_PIECE)

    status_line, _, rest = answer.partition(b"\r\n")
    assert status_line == b"HTTP/1.1 400 Bad Request"
    headers, _, body = rest.partition(b"\r\n\r\n")
    assert b"content-type: text/plain" in headers.lower()
    assert body == b"Invalid HTTP request received."
    # The same request in one piece reaches the app and gets its `request finished` line. The
    # app logs after the response, so wait for that line: by then a line for the refused
    # request would be there too. There is exactly one, so the refused request had none.
    assert _raw_request(server, _about_17_kb(token), split_at=None).startswith(b"HTTP/1.1 200 ")
    deadline = time.monotonic() + 10
    while not _finished_lines(captured):
        assert time.monotonic() < deadline, "no request finished line"
        time.sleep(0.05)
    time.sleep(0.2)
    [line] = _finished_lines(captured)
    assert line.log_record.attributes["http.response.status_code"] == 200
    assert [span.attributes["http.response.status_code"] for span in captured.server_spans()] == [
        200
    ]


def test_request_body_limit_about_17_kb_in_one_piece_reaches_the_app(server, migrated_db, token):
    """Complete in one read, it is not checked against 16 KiB and is validated as usual."""
    tag = "00" + EMOJI * 38
    status, _, created = server.request(
        "POST",
        "/entries",
        json.dumps(
            {"text": "Shipped it.", "date": DAY, "category": "Learning", "tags": [tag]}
        ).encode(),
        headers=_auth(token),
    )
    assert status == 201, created

    answer = _raw_request(server, _about_17_kb(token), split_at=None)

    # The unknown parameter is ignored, and the filter matches as always.
    assert answer.startswith(b"HTTP/1.1 200 ")
    entries = json.loads(answer.partition(b"\r\n\r\n")[2])["entries"]
    assert [entry["id"] for entry in entries] == [json.loads(created)["id"]]


def test_request_body_limit_45_tags_in_one_piece_get_422_naming_tag(server, token):
    head = _head(_largest_filter_query(45), token)
    assert len(head) > 16_384

    answer = _raw_request(server, head, split_at=None)

    assert answer.startswith(b"HTTP/1.1 422 ")
    body = json.loads(answer.partition(b"\r\n\r\n")[2])
    assert [item["field"] for item in body["fields"]] == ["tag"]
