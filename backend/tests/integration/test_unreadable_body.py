"""Request bodies the backend cannot read as JSON, against real PostgreSQL (issue #58).

Every operation with a request body answers such a body with the body error (422
`validation_failed` naming `body`), and the request changes nothing: no row of any table is
created, changed or deleted, the mock AI provider records no call, and no failed-login count
changes. Without a valid token, the operations that need one answer 401 first. No requirement
ID covers the body error, so its tests start with `test_unreadable_body_`; the token-first
test keeps FR-A3. The responses themselves and the telemetry are also tested without a
database in tests/unit/test_unreadable_body.py.
"""

import codecs
import datetime as dt
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text

from app.models import Entry
from tests.conftest import OPENAPI_PATH
from tests.integration.conftest import APP_TABLES
from tests.integration.test_entries import BODY_ERROR, UNREADABLE_BODIES, _token

ALICE = "alice@example.com"
BOB = "bob@example.com"
PASSWORD = "Correct-Horse-7"
MISSING_ID = "00000000-0000-4000-8000-000000000000"
ENTRY = {
    "text": "Shipped the release.",
    "date": "2026-11-08",
    "category": "Achievement",
    "tags": ["Python", "Go"],
}
PERIOD = {"period_start": "2026-11-01", "period_end": "2026-11-30"}
BODIES = {
    **UNREADABLE_BODIES,
    # Read as JSON, these would count a failed login, log Alice in or delete her account.
    "wrong-password-latin-1": b'{"email": "alice@example.com", "password": "wr\xf6ng"}',
    "correct-login-and-stray-byte": (
        b'{"email": "alice@example.com", "password": "' + PASSWORD.encode() + b'"}\x80'
    ),
    "correct-password-and-stray-byte": (b'{"current_password": "' + PASSWORD.encode() + b'"}\x80'),
}
"""Every unreadable body of the issue, and some that would change data if they were read."""


def _operations_with_a_body() -> dict[str, tuple[str, str]]:
    """operationId -> (method, path) of every operation with a `requestBody` in openapi.yaml."""
    contract = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    found = {}
    for path, path_item in contract["paths"].items():
        for method, operation in path_item.items():
            if isinstance(operation, dict) and "requestBody" in operation:
                found[operation["operationId"]] = (method.upper(), path)
    return found


OPERATIONS = _operations_with_a_body()
PUBLIC_OPERATIONS = {"register", "login"}


def _table_rows(engine: Engine) -> dict[str, list[tuple]]:
    """Every row of every application table."""
    snapshot = {}
    with engine.connect() as connection:
        for table in sorted(APP_TABLES):
            rows = connection.execute(text(f"SELECT * FROM {table}"))
            snapshot[table] = sorted(tuple(str(value) for value in row) for row in rows)
    return snapshot


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _account(client: TestClient, email: str) -> dict:
    """Register and log in through the API, then create an entry and generate a summary."""
    registered = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    token = login.json()["token"]
    entry = client.post("/entries", json=ENTRY, headers=_bearer(token))
    assert entry.status_code == 201
    summary = client.post("/summaries", json=PERIOD, headers=_bearer(token))
    assert summary.status_code == 201
    suggestion = client.post("/suggestions", json={"text": "Shipped"}, headers=_bearer(token))
    assert suggestion.status_code == 200
    return {
        "id": uuid.UUID(registered.json()["id"]),
        "token": token,
        "entry": entry.json()["id"],
        "summary": summary.json()["id"],
    }


@pytest.fixture
def world(client: TestClient) -> dict:
    """Alice and Bob, each with a login, an entry, its tags, a summary and AI usage, and a
    failed login for Alice's email and for an unknown one."""
    alice = _account(client, ALICE)
    bob = _account(client, BOB)
    for email in (ALICE, "nobody@example.com"):
        failed = client.post("/auth/login", json={"email": email, "password": "Wrong-Pass-1"})
        assert failed.status_code == 401
    return {"alice": alice, "bob": bob}


def _requests(world: dict) -> list[tuple[str, str, str]]:
    """(operationId, method, url) for every operation with a body, with Alice's ids. Updates
    also go to Bob's entry or summary and to one that does not exist."""
    alice, bob = world["alice"], world["bob"]
    requests = []
    for operation_id, (method, path) in OPERATIONS.items():
        if "{entryId}" in path:
            ids = [alice["entry"], bob["entry"], MISSING_ID]
            requests += [(operation_id, method, path.replace("{entryId}", i)) for i in ids]
        elif "{summaryId}" in path:
            ids = [alice["summary"], bob["summary"], MISSING_ID]
            requests += [(operation_id, method, path.replace("{summaryId}", i)) for i in ids]
        else:
            requests.append((operation_id, method, path))
    return requests


def _ai_calls(client: TestClient) -> tuple[int, int]:
    provider = client.app.state.ai_provider
    return len(provider.suggest_calls), len(provider.summarise_calls)


def test_unreadable_body_operations_with_a_body_are_the_eight_of_the_contract():
    assert set(OPERATIONS) == {
        "register",
        "login",
        "deleteAccount",
        "createEntry",
        "updateEntry",
        "suggestCategoryAndTags",
        "generateSummary",
        "updateSummary",
    }


def test_unreadable_body_changes_nothing_on_any_operation(
    client: TestClient, migrated_db: Engine, world: dict, contract
):
    """With a valid token (an ordinary user, not the demo account) where one is needed."""
    calls = _ai_calls(client)
    token = world["alice"]["token"]

    for operation_id, method, url in _requests(world):
        headers = {} if operation_id in PUBLIC_OPERATIONS else _bearer(token)
        for name, body in BODIES.items():
            before = _table_rows(migrated_db)

            response = client.request(
                method, url, content=body, headers={**headers, "Content-Type": "application/json"}
            )

            assert response.status_code == 422, (operation_id, url, name)
            assert response.json() == BODY_ERROR, (operation_id, url, name)
            contract("Error").validate(response.json())
            assert PASSWORD not in response.text
            # No user, token, entry, tag, link, summary, AI usage or login attempt row is
            # created, changed or deleted.
            assert _table_rows(migrated_db) == before, (operation_id, url, name)

    assert _ai_calls(client) == calls
    assert client.get("/entries", headers=_bearer(token)).status_code == 200


@pytest.mark.parametrize("token", ["none", "garbage", "expired"])
def test_fr_a3_unreadable_body_without_a_valid_token_is_not_authenticated_on_every_operation(
    client: TestClient, migrated_db: Engine, world: dict, contract, token: str
):
    expired = _token(migrated_db, world["alice"]["id"], valid_for=dt.timedelta(seconds=-1))
    headers = {
        "none": {},
        "garbage": _bearer("garbage"),
        "expired": _bearer(expired),
    }[token]
    calls = _ai_calls(client)
    before = _table_rows(migrated_db)
    protected = [request for request in _requests(world) if request[0] not in PUBLIC_OPERATIONS]
    assert len({operation_id for operation_id, _, _ in protected}) == 6

    for operation_id, method, url in protected:
        for name, body in UNREADABLE_BODIES.items():
            response = client.request(
                method, url, content=body, headers={**headers, "Content-Type": "application/json"}
            )

            assert response.status_code == 401, (operation_id, url, name)
            contract("Error").validate(response.json())
            assert response.json()["code"] == "not_authenticated"
            assert response.headers["WWW-Authenticate"] == "Bearer"

    assert _table_rows(migrated_db) == before
    assert _ai_calls(client) == calls


@pytest.mark.parametrize(
    "encode",
    [
        lambda raw: codecs.BOM_UTF8 + raw.encode("utf-8"),
        lambda raw: raw.encode("utf-16"),
        lambda raw: raw.encode("utf-16-le"),
        lambda raw: raw.encode("utf-32"),
    ],
    ids=["utf-8-bom", "utf-16-bom", "utf-16-le", "utf-32-bom"],
)
def test_unreadable_body_json_in_an_encoding_json_loads_detects_is_still_saved(
    client: TestClient, migrated_db: Engine, world: dict, encode
):
    """The contract promises only UTF-8, and the encodings read before are still read."""
    raw = '{"text": "Café ✓ 🚀", "date": "2026-11-15", "category": "Learning", "tags": ["Ünïcode"]}'

    response = client.post(
        "/entries",
        content=encode(raw),
        headers={**_bearer(world["alice"]["token"]), "Content-Type": "application/json"},
    )

    assert response.status_code == 201
    assert response.json()["text"] == "Café ✓ 🚀"
    assert response.json()["tags"] == ["Ünïcode"]
    with migrated_db.connect() as connection:
        stored = connection.execute(
            select(Entry.text).where(Entry.id == uuid.UUID(response.json()["id"]))
        ).scalar_one()
    assert stored == "Café ✓ 🚀"
