"""Account deletion through the API, against real PostgreSQL (issue #20).

Operation `deleteAccount` in openapi.yaml. Covers FR-D2 and the acceptance criteria in
product-spec.md §7.6 and §8. Users, tokens and passwords go through the real register and
login operations, so the password check uses real argon2 hashes. Summaries and suggestions
use the mock AI provider; no test calls a real AI.
"""

import datetime as dt
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select, text

from app.auth import hash_token
from app.models import EntryTag, Token, User
from tests.integration.conftest import APP_TABLES, table_names

PATH = "/account"
ALICE = "alice@example.com"
BOB = "bob@example.com"
ALICE_PASSWORD = "Correct-Horse-7"
BOB_PASSWORD = "Battery-Staple-9"
FILTER = {"period_start": "2026-10-01", "period_end": "2026-10-31"}
ENTRIES = [
    {
        "text": "Gave a talk on testing.",
        "date": "2026-10-15",
        "category": "Learning",
        "tags": ["Testing", "Public speaking"],
        "result_impact": "Two teams adopted the approach.",
    },
    {"text": "Shipped the release.", "date": "2026-10-20", "category": "Achievement"},
    {
        "text": "Got feedback on the design review.",
        "date": "2026-10-16",
        "category": "Feedback",
        "tags": ["Design"],
    },
]
# Tables whose rows belong to one user, and how a row is tied to its user.
USER_ID_COLUMN = {
    "users": "id",
    "tokens": "user_id",
    "entries": "user_id",
    "tags": "user_id",
    "summaries": "user_id",
    "ai_usage": "user_id",
}


# --- Helpers ------------------------------------------------------------------------------


def _bearer(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _register(client: TestClient, email: str, password: str) -> uuid.UUID:
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


def _login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def _token(client: TestClient, email: str, password: str) -> str:
    response = _login(client, email, password)
    assert response.status_code == 200
    return response.json()["token"]


def _delete(client: TestClient, token: str | None, password: str | None = None, **kwargs):
    if password is not None:
        kwargs["json"] = {"current_password": password}
    return client.request("DELETE", PATH, headers=_bearer(token), **kwargs)


def _fill(client: TestClient, token: str) -> None:
    """Entries with tags, a summary and a suggestion, so every user table has rows."""
    for entry in ENTRIES:
        assert client.post("/entries", json=entry, headers=_bearer(token)).status_code == 201
    assert client.post("/summaries", json=FILTER, headers=_bearer(token)).status_code == 201
    suggestion = client.post("/suggestions", json={"text": "Fixed a bug."}, headers=_bearer(token))
    assert suggestion.status_code == 200


# Wrong passwords are counted in login_attempts on purpose (FR-A4, issue #46), so the
# before-and-after snapshots leave it out. It holds no user id, only SHA-256 hashes; its
# rows are tested in test_attempt_limits.py and by the "no row remains" test below.
SNAPSHOT_TABLES = APP_TABLES - {"login_attempts"}


def _snapshot(engine: Engine) -> dict[str, list[tuple]]:
    """Every row of every application table but login_attempts, to compare before and after."""
    with engine.connect() as connection:
        snapshot = {}
        for table in sorted(SNAPSHOT_TABLES):
            rows = connection.execute(text(f"SELECT * FROM {table}"))
            snapshot[table] = sorted(tuple(str(value) for value in row) for row in rows)
        return snapshot


def _rows_of(engine: Engine, user_id: uuid.UUID) -> dict[str, int]:
    """How many rows in each table belong to the user."""
    with engine.connect() as connection:
        counts = {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE {column} = :user_id"),
                {"user_id": user_id},
            ).scalar_one()
            for table, column in USER_ID_COLUMN.items()
        }
        counts["entry_tags"] = connection.execute(
            text(
                "SELECT count(*) FROM entry_tags"
                " WHERE entry_id IN (SELECT id FROM entries WHERE user_id = :user_id)"
                " OR tag_id IN (SELECT id FROM tags WHERE user_id = :user_id)"
            ),
            {"user_id": user_id},
        ).scalar_one()
    return counts


def _links_of(engine: Engine, entry_ids: set[uuid.UUID]) -> int:
    with engine.connect() as connection:
        links = connection.execute(select(EntryTag.entry_id)).scalars()
        return sum(1 for entry_id in links if entry_id in entry_ids)


def _entry_ids(engine: Engine, user_id: uuid.UUID) -> set[uuid.UUID]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id FROM entries WHERE user_id = :user_id"), {"user_id": user_id}
        )
        return set(rows.scalars())


def _global_counter(engine: Engine) -> list[tuple]:
    with engine.connect() as connection:
        return list(connection.execute(text("SELECT day, request_count FROM ai_usage_global")))


def _assert_error(response, contract, status: int, code: str) -> None:
    assert response.status_code == status
    contract("Error").validate(response.json())
    assert response.json()["code"] == code


@pytest.fixture
def alice(client: TestClient, migrated_db: Engine) -> uuid.UUID:
    return _register(client, ALICE, ALICE_PASSWORD)


@pytest.fixture
def alice_tokens(client: TestClient, alice: uuid.UUID) -> tuple[str, str]:
    """Two logins of Alice, as from two devices, and data in every user table."""
    first = _token(client, ALICE, ALICE_PASSWORD)
    second = _token(client, ALICE, ALICE_PASSWORD)
    _fill(client, first)
    return first, second


@pytest.fixture
def bob(client: TestClient, migrated_db: Engine) -> uuid.UUID:
    return _register(client, BOB, BOB_PASSWORD)


@pytest.fixture
def bob_token(client: TestClient, bob: uuid.UUID) -> str:
    token = _token(client, BOB, BOB_PASSWORD)
    _fill(client, token)
    return token


# --- Deleting -----------------------------------------------------------------------------


def test_fr_d2_account_deletion_removes_all_data(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_tokens, bob_token
):
    before = _rows_of(migrated_db, alice)
    # The test data puts at least one of Alice's rows in every user table.
    assert all(count > 0 for count in before.values()), before
    assert before["tokens"] == 2
    entry_ids = _entry_ids(migrated_db, alice)

    response = _delete(client, alice_tokens[0], ALICE_PASSWORD)

    assert response.status_code == 204
    assert response.content == b""
    assert _rows_of(migrated_db, alice) == dict.fromkeys(before, 0)
    assert _links_of(migrated_db, entry_ids) == 0


def test_fr_d2_no_row_of_the_user_remains_in_any_table(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_tokens, bob: uuid.UUID
):
    """§7.6: every table is checked, so a table added later without a cascade is noticed."""
    # Bob has an account but no data, so after the deletion only his user row may remain.
    assert table_names(migrated_db) - {"alembic_version"} == APP_TABLES

    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204

    snapshot = _snapshot(migrated_db)
    assert [row[0] for row in snapshot["users"]] == [str(bob)]
    for table in SNAPSHOT_TABLES - {"users", "ai_usage_global"}:
        assert snapshot[table] == [], table
    # The correct password cleared the count for Alice's email (FR-A4), and no other
    # attempt was made.
    with migrated_db.connect() as connection:
        assert connection.execute(text("SELECT * FROM login_attempts")).all() == []
    for table, rows in snapshot.items():
        assert not any(str(alice) in row for row in rows), table


def test_fr_d2_global_ai_counter_is_not_changed(
    client: TestClient, migrated_db: Engine, alice_tokens
):
    """§7.6 and §8: the day's global count holds no personal data and is never lowered."""
    before = _global_counter(migrated_db)
    assert before and before[0][1] > 0

    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204

    assert _global_counter(migrated_db) == before


def test_fr_d2_other_users_data_is_not_touched(
    client: TestClient, migrated_db: Engine, alice_tokens, bob: uuid.UUID, bob_token: str
):
    bob_rows = _rows_of(migrated_db, bob)
    bob_export = client.get("/export/json", headers=_bearer(bob_token)).json()

    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204

    assert _rows_of(migrated_db, bob) == bob_rows
    after = client.get("/export/json", headers=_bearer(bob_token))
    assert after.status_code == 200
    assert after.json()["entries"] == bob_export["entries"]
    assert after.json()["summaries"] == bob_export["summaries"]
    assert _login(client, BOB, BOB_PASSWORD).status_code == 200


def test_fr_a3_another_users_token_cannot_delete_the_account(
    client: TestClient, migrated_db: Engine, alice_tokens, bob_token: str, contract
):
    """The token decides whose account goes. Alice's password does not delete with Bob's token."""
    before = _snapshot(migrated_db)

    response = _delete(client, bob_token, ALICE_PASSWORD)

    _assert_error(response, contract, 403, "wrong_password")
    assert _snapshot(migrated_db) == before


def test_fr_d2_failed_deletion_deletes_nothing(
    client: TestClient, migrated_db: Engine, alice_tokens, bob_token
):
    """One transaction: when removing a part fails, the user and all their data stay."""
    before = _snapshot(migrated_db)
    with migrated_db.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION fail_on_delete() RETURNS trigger LANGUAGE plpgsql AS"
                " $$ BEGIN RAISE EXCEPTION 'test: deletion fails'; END $$"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER fail_on_delete BEFORE DELETE ON summaries"
                " FOR EACH ROW EXECUTE FUNCTION fail_on_delete()"
            )
        )
    try:
        failing = TestClient(client.app, raise_server_exceptions=False)
        response = _delete(failing, alice_tokens[0], ALICE_PASSWORD)
    finally:
        with migrated_db.begin() as connection:
            connection.execute(text("DROP TRIGGER fail_on_delete ON summaries"))
            connection.execute(text("DROP FUNCTION fail_on_delete()"))

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert _snapshot(migrated_db) == before
    assert client.get("/entries", headers=_bearer(alice_tokens[1])).status_code == 200


# --- Password check -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"current_password": None},
        {"current_password": ""},
        {"current_password": 12345678901},
        {"password": ALICE_PASSWORD},
        {"current_password": "A1!" + "a" * 126},  # longer than any password can be
    ],
)
def test_fr_d2_missing_password_returns_the_validation_error_and_deletes_nothing(
    client: TestClient, migrated_db: Engine, alice_tokens, bob_token, contract, body
):
    before = _snapshot(migrated_db)

    kwargs = {} if body is None else {"json": body}
    response = client.request("DELETE", PATH, headers=_bearer(alice_tokens[0]), **kwargs)

    _assert_error(response, contract, 422, "validation_failed")
    assert _snapshot(migrated_db) == before


def test_fr_d2_body_that_is_not_json_returns_the_validation_error_and_deletes_nothing(
    client: TestClient, migrated_db: Engine, alice_tokens, contract
):
    before = _snapshot(migrated_db)

    response = client.request(
        "DELETE",
        PATH,
        content=b'{"current_password": ',
        headers={**_bearer(alice_tokens[0]), "content-type": "application/json"},
    )

    _assert_error(response, contract, 422, "validation_failed")
    assert _snapshot(migrated_db) == before


@pytest.mark.parametrize(
    "password",
    [
        "Correct-Horse-8",
        "correct-horse-7",
        " Correct-Horse-7",
        "Correct-Horse-7 ",
        BOB_PASSWORD,  # another user's password
        "x",
    ],
)
def test_fr_d2_wrong_password_returns_the_wrong_password_error_and_deletes_nothing(
    client: TestClient, migrated_db: Engine, alice_tokens, bob_token, contract, password
):
    before = _snapshot(migrated_db)

    response = _delete(client, alice_tokens[0], password)

    _assert_error(response, contract, 403, "wrong_password")
    assert _snapshot(migrated_db) == before
    # Both logins keep working after a wrong password.
    for token in alice_tokens:
        assert client.get("/entries", headers=_bearer(token)).status_code == 200


def test_fr_d2_password_is_checked_against_the_stored_argon2_hash(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_tokens
):
    with migrated_db.connect() as connection:
        stored = connection.execute(select(User.password_hash).where(User.id == alice))
        assert stored.scalar_one().startswith("$argon2id$")

    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204


def test_fr_d2_password_never_appears_in_logs(
    client: TestClient, migrated_db: Engine, alice_tokens, caplog
):
    caplog.set_level(logging.DEBUG)
    wrong = "Wrong-Horse-8"
    too_long = "Too-Long-Secret-9" + "x" * 120

    responses = [
        _delete(client, alice_tokens[0], wrong),
        _delete(client, alice_tokens[0], too_long),
        _delete(client, None, ALICE_PASSWORD),
        _delete(client, alice_tokens[0], ALICE_PASSWORD),
    ]

    assert [response.status_code for response in responses] == [403, 422, 401, 204]
    for secret in [ALICE_PASSWORD, wrong, "Too-Long-Secret-9", *alice_tokens]:
        assert secret not in caplog.text
        for response in responses:
            assert secret not in response.text


# --- Afterwards ---------------------------------------------------------------------------


def test_fr_d2_every_token_of_the_user_is_rejected_afterwards(
    client: TestClient, migrated_db: Engine, alice_tokens, contract
):
    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204

    for token in alice_tokens:
        _assert_error(
            client.get("/entries", headers=_bearer(token)), contract, 401, "not_authenticated"
        )
        _assert_error(_delete(client, token, ALICE_PASSWORD), contract, 401, "not_authenticated")


def test_fr_d2_old_login_is_rejected_afterwards(
    client: TestClient, migrated_db: Engine, alice_tokens, contract
):
    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204

    response = _login(client, ALICE, ALICE_PASSWORD)

    _assert_error(response, contract, 401, "invalid_credentials")


def test_fr_d2_same_email_can_register_again_and_gets_a_new_empty_account(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_tokens
):
    assert _delete(client, alice_tokens[0], ALICE_PASSWORD).status_code == 204

    new_password = "Fresh-Start-42"
    new_id = _register(client, ALICE, new_password)
    token = _token(client, ALICE, new_password)

    assert new_id != alice
    for path, key in [("/entries", "entries"), ("/tags", "tags"), ("/summaries", "summaries")]:
        response = client.get(path, headers=_bearer(token))
        assert response.status_code == 200
        assert response.json() == {key: []}, path
    rows = _rows_of(migrated_db, new_id)
    assert rows == {**dict.fromkeys(rows, 0), "users": 1, "tokens": 1}
    # The old password does not open the new account.
    assert _login(client, ALICE, ALICE_PASSWORD).status_code == 401


# --- Errors -------------------------------------------------------------------------------


def _expired_token(engine: Engine, user_id: uuid.UUID) -> str:
    token = f"test-token-{uuid.uuid4()}"
    with engine.begin() as connection:
        connection.execute(
            insert(Token).values(
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1),
            )
        )
    return token


@pytest.mark.parametrize("kind", ["missing", "unknown", "expired", "logged out"])
def test_fr_d2_without_a_valid_token_returns_not_authenticated_and_deletes_nothing(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_tokens, contract, kind
):
    token = {
        "missing": lambda: None,
        "unknown": lambda: "not-a-real-token",
        "expired": lambda: _expired_token(migrated_db, alice),
        "logged out": lambda: alice_tokens[1],
    }[kind]()
    if kind == "logged out":
        assert client.post("/auth/logout", headers=_bearer(token)).status_code == 204
    before = _snapshot(migrated_db)

    response = _delete(client, token, ALICE_PASSWORD)

    _assert_error(response, contract, 401, "not_authenticated")
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _snapshot(migrated_db) == before


@pytest.mark.parametrize("body", [None, {}, b'{"current_password": '])
def test_fr_d2_without_a_token_an_invalid_body_still_returns_not_authenticated(
    client: TestClient, migrated_db: Engine, alice_tokens, contract, body
):
    before = _snapshot(migrated_db)
    if isinstance(body, bytes):
        kwargs = {"content": body, "headers": {"content-type": "application/json"}}
    else:
        kwargs = {} if body is None else {"json": body}

    response = client.request("DELETE", PATH, **kwargs)

    _assert_error(response, contract, 401, "not_authenticated")
    assert _snapshot(migrated_db) == before
