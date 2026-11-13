"""The demo account against real PostgreSQL (FR-X1, issue #21).

Operation `demoLogin`, the demo error of `deleteAccount` and the seed script
(`scripts/seed_demo`). Visitors go through the real API with tokens from demo-login. Summaries
use the mock AI provider; no test calls a real AI.
"""

import calendar
import datetime as dt
import logging
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select, text, update
from sqlalchemy.orm import Session

import app.demo_seed
from app.auth import hash_token
from app.demo_seed import SAMPLE_ENTRIES, SAMPLE_SUMMARIES, reset_demo_account, sample_tag_names
from app.main import create_app
from app.models import CATEGORIES, Token, User
from app.passwords import hash_password, verify_password
from app.settings import Settings
from scripts import seed_demo
from tests.integration.conftest import ALLOWED_ORIGIN, APP_TABLES

DEMO = "demo@example.com"
ALICE = "alice@example.com"
ALICE_PASSWORD = "Correct-Horse-7"
TODAY = dt.date(2026, 11, 10)
DEMO_ERROR = {
    "code": "demo_account_not_deletable",
    "message": "The demo account cannot be deleted.",
}


# --- Helpers ------------------------------------------------------------------------------


def _settings(test_database_url: str, **overrides) -> Settings:
    values = {
        "database_url": test_database_url,
        "cors_allowed_origins": [ALLOWED_ORIGIN],
        "ai_provider": "mock",
        "demo_email": DEMO,
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.fixture
def demo_settings(test_database_url: str, migrated_db: Engine) -> Settings:
    return _settings(test_database_url)


@pytest.fixture
def api(demo_settings: Settings) -> TestClient:
    """The app with the demo turned on. The demo account is not seeded yet."""
    return TestClient(create_app(demo_settings))


def _seed(engine: Engine, today: dt.date = TODAY, email: str = DEMO) -> uuid.UUID:
    with Session(engine) as session:
        result = reset_demo_account(session, email, today)
        session.commit()
    return result.user_id


@pytest.fixture
def seeded(api: TestClient, migrated_db: Engine) -> TestClient:
    _seed(migrated_db)
    return api


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _demo_token(client: TestClient) -> str:
    response = client.post("/auth/demo")
    assert response.status_code == 200
    return response.json()["token"]


def _register(client: TestClient, email: str = ALICE, password: str = ALICE_PASSWORD) -> None:
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201


def _login(client: TestClient, email: str = ALICE, password: str = ALICE_PASSWORD) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["token"]


def _user(engine: Engine, email: str) -> User | None:
    with Session(engine) as session:
        return session.scalars(select(User).where(User.email == email)).one_or_none()


def _demo_content(client: TestClient, token: str) -> dict:
    """The demo account's data as visitors see it, without ids and timestamps."""
    entries = client.get("/entries", headers=_bearer(token)).json()["entries"]
    tags = client.get("/tags", headers=_bearer(token)).json()["tags"]
    summaries = client.get("/summaries", headers=_bearer(token)).json()["summaries"]
    return {
        "entries": sorted(
            (e["date"], e["category"], e["text"], e["result_impact"] or "", tuple(e["tags"]))
            for e in entries
        ),
        "tags": sorted(tags),
        "summaries": sorted(
            (
                s["text"],
                s["filter"]["period_start"],
                s["filter"]["period_end"],
                tuple(s["filter"]["categories"]),
                tuple(s["filter"]["tags"]),
            )
            for s in summaries
        ),
    }


def _table_rows(engine: Engine, user_id: uuid.UUID | None = None) -> dict:
    """Rows of every application table; with a user, only that user's (and all global rows)."""
    owner = {
        "users": "id",
        "tokens": "user_id",
        "entries": "user_id",
        "tags": "user_id",
        "summaries": "user_id",
        "ai_usage": "user_id",
        "entry_tags": "(SELECT user_id FROM entries WHERE entries.id = entry_tags.entry_id)",
        "ai_usage_global": None,
        # No user id: SHA-256 hashes of emails and visitor IPs (FR-A4).
        "login_attempts": None,
    }
    assert set(owner) == APP_TABLES
    snapshot = {}
    with engine.connect() as connection:
        for table, column in sorted(owner.items()):
            query = f"SELECT * FROM {table}"
            params = {}
            if user_id is not None and column is not None:
                query += f" WHERE {column} = :user_id"
                params = {"user_id": user_id}
            rows = connection.execute(text(query), params)
            snapshot[table] = sorted(tuple(str(value) for value in row) for row in rows)
    return snapshot


def _visitor_changes(client: TestClient, token: str) -> None:
    """A visitor changes everything they can: entries, tags and summaries."""
    headers = _bearer(token)
    entries = client.get("/entries", headers=headers).json()["entries"]
    created = client.post(
        "/entries",
        json={
            "text": "Visitor entry.",
            "date": "2026-11-09",
            "category": "Learning",
            "tags": ["Visitor tag"],
        },
        headers=headers,
    )
    assert created.status_code == 201
    first, second = entries[0], entries[1]
    edited = client.put(
        f"/entries/{first['id']}",
        json={"text": "Edited by a visitor.", "date": first["date"], "category": "Feedback"},
        headers=headers,
    )
    assert edited.status_code == 200
    assert client.delete(f"/entries/{second['id']}", headers=headers).status_code == 204
    [summary] = client.get("/summaries", headers=headers).json()["summaries"]
    changed = client.patch(
        f"/summaries/{summary['id']}", json={"text": "Visitor text."}, headers=headers
    )
    assert changed.status_code == 200
    generated = client.post(
        "/summaries",
        json={"period_start": "2026-01-01", "period_end": "2026-12-31"},
        headers=headers,
    )
    assert generated.status_code == 201
    assert client.delete(f"/summaries/{summary['id']}", headers=headers).status_code == 204


# --- Demo-login ---------------------------------------------------------------------------


def test_fr_x1_demo_login_returns_token(seeded: TestClient, migrated_db: Engine, contract):
    response = seeded.post("/auth/demo")

    assert response.status_code == 200
    body = response.json()
    contract("DemoLoginResult").validate(body)
    assert body["demo"] is True
    # A normal token for the demo user, stored only as its hash.
    with Session(migrated_db) as session:
        row = session.scalars(
            select(Token).where(Token.token_hash == hash_token(body["token"]))
        ).one()
        assert row.user_id == _user(migrated_db, DEMO).id
        assert (
            session.scalars(select(Token).where(Token.token_hash == body["token"])).first() is None
        )
    entries = seeded.get("/entries", headers=_bearer(body["token"])).json()["entries"]
    assert len(entries) == len(SAMPLE_ENTRIES)


def test_fr_x1_demo_login_when_turned_off_returns_not_found(
    test_database_url: str, migrated_db: Engine, contract
):
    # The demo user exists, but DEMO_EMAIL is empty: the demo is off.
    _seed(migrated_db)
    client = TestClient(create_app(_settings(test_database_url, demo_email="")))

    response = client.post("/auth/demo")

    assert response.status_code == 404
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_found"
    assert _table_rows(migrated_db)["tokens"] == []


def test_fr_x1_demo_login_before_the_seed_returns_not_found(
    api: TestClient, migrated_db: Engine, contract
):
    response = api.post("/auth/demo")

    assert response.status_code == 404
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_found"
    # Demo-login never creates the account.
    assert _user(migrated_db, DEMO) is None


def test_fr_x1_demo_token_has_the_login_lifetime_and_cleans_up_expired_tokens(
    test_database_url: str, migrated_db: Engine
):
    demo_id = _seed(migrated_db)
    client = TestClient(create_app(_settings(test_database_url, token_lifetime_days=3)))
    _register(client)
    alice_id = _user(migrated_db, ALICE).id
    past = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    with migrated_db.begin() as connection:
        for user_id, value in ((demo_id, "old-demo"), (alice_id, "old-alice")):
            connection.execute(
                insert(Token).values(user_id=user_id, token_hash=hash_token(value), expires_at=past)
            )
    before = dt.datetime.now(dt.UTC)

    body = client.post("/auth/demo").json()
    login_body = client.post(
        "/auth/login", json={"email": ALICE, "password": ALICE_PASSWORD}
    ).json()

    lifetime = dt.timedelta(days=3)
    for result in (body, login_body):
        expires_at = dt.datetime.fromisoformat(result["expires_at"])
        assert before + lifetime <= expires_at <= dt.datetime.now(dt.UTC) + lifetime
    with Session(migrated_db) as session:
        hashes = set(session.scalars(select(Token.token_hash)))
    # Each login removed only its own user's expired token, as login does.
    assert hash_token("old-demo") not in hashes
    assert hash_token("old-alice") not in hashes
    assert hash_token(body["token"]) in hashes


def test_fr_x1_expired_demo_token_stops_working(seeded: TestClient, migrated_db: Engine):
    token = _demo_token(seeded)
    with migrated_db.begin() as connection:
        connection.execute(
            update(Token)
            .where(Token.token_hash == hash_token(token))
            .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1))
        )

    response = seeded.get("/entries", headers=_bearer(token))

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


# --- A demo session works like a normal one -----------------------------------------------


def test_fr_x1_demo_session_token_works_like_a_normal_one(seeded: TestClient):
    token = _demo_token(seeded)
    headers = _bearer(token)

    # Entries: create, edit, delete.
    created = seeded.post(
        "/entries",
        json={
            "text": "Tried the demo.",
            "date": "2026-11-09",
            "category": "Learning",
            "tags": ["Demo"],
        },
        headers=headers,
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    edited = seeded.put(
        f"/entries/{entry_id}",
        json={"text": "Tried the demo again.", "date": "2026-11-09", "category": "Achievement"},
        headers=headers,
    )
    assert edited.status_code == 200
    assert seeded.get(f"/entries/{entry_id}", headers=headers).json()["text"] == (
        "Tried the demo again."
    )
    assert seeded.delete(f"/entries/{entry_id}", headers=headers).status_code == 204

    # Summaries: generate (mock AI), edit, delete.
    generated = seeded.post(
        "/summaries",
        json={
            "period_start": "2026-08-01",
            "period_end": "2026-11-10",
            "categories": ["Achievement"],
        },
        headers=headers,
    )
    assert generated.status_code == 201
    summary_id = generated.json()["id"]
    changed = seeded.patch(f"/summaries/{summary_id}", json={"text": "My edit."}, headers=headers)
    assert changed.status_code == 200
    assert changed.json()["text"] == "My edit."
    assert seeded.delete(f"/summaries/{summary_id}", headers=headers).status_code == 204

    # Suggestions, tags and both exports.
    assert (
        seeded.post("/suggestions", json={"text": "Fixed a bug."}, headers=headers).status_code
        == 200
    )
    assert set(seeded.get("/tags", headers=headers).json()["tags"]) >= set(sample_tag_names())
    exported = seeded.get("/export/json", headers=headers)
    assert exported.status_code == 200
    assert len(exported.json()["entries"]) == len(SAMPLE_ENTRIES)
    assert len(exported.json()["summaries"]) == len(SAMPLE_SUMMARIES)
    assert seeded.get("/export/markdown", headers=headers).status_code == 200

    # Logout revokes only this token.
    other = _demo_token(seeded)
    assert seeded.post("/auth/logout", headers=headers).status_code == 204
    assert seeded.get("/entries", headers=headers).status_code == 401
    assert seeded.get("/entries", headers=_bearer(other)).status_code == 200


def test_fr_x1_demo_visitors_share_the_data_and_the_ai_limits(
    test_database_url: str, migrated_db: Engine, contract
):
    _seed(migrated_db)
    client = TestClient(create_app(_settings(test_database_url, ai_daily_summaries_per_user=1)))
    first, second = _demo_token(client), _demo_token(client)
    period = {"period_start": "2026-05-01", "period_end": "2026-11-10"}

    created = client.post(
        "/entries",
        json={"text": "Shared.", "date": "2026-11-09", "category": "Learning"},
        headers=_bearer(first),
    )
    assert created.status_code == 201
    seen = client.get(f"/entries/{created.json()['id']}", headers=_bearer(second))
    assert seen.status_code == 200

    assert client.post("/summaries", json=period, headers=_bearer(first)).status_code == 201
    limited = client.post("/summaries", json=period, headers=_bearer(second))
    assert limited.status_code == 429
    contract("Error").validate(limited.json())
    assert limited.json()["limit"] == "user_summaries"


# --- Deleting the demo account ------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"json": {"current_password": "Known-Demo-Pass-1"}}, id="correct-password"),
        pytest.param({"json": {"current_password": "Wrong-Horse-8"}}, id="wrong-password"),
        pytest.param({"json": {}}, id="missing-password"),
        pytest.param({"json": {"current_password": ""}}, id="empty-password"),
        pytest.param({}, id="no-body"),
        pytest.param(
            {"content": b'{"current_password": ', "headers": {"content-type": "application/json"}},
            id="invalid-json",
        ),
        pytest.param(
            {"content": b"\xff\xfe", "headers": {"content-type": "application/json"}},
            id="not-utf-8",
        ),
    ],
)
def test_fr_x1_deleting_the_demo_account_returns_the_demo_error_and_deletes_nothing(
    seeded: TestClient, migrated_db: Engine, contract, kwargs: dict
):
    # Give the demo account a known password, so even the correct one can be sent.
    with migrated_db.begin() as connection:
        connection.execute(
            update(User)
            .where(User.email == DEMO)
            .values(password_hash=hash_password("Known-Demo-Pass-1"))
        )
    token = _demo_token(seeded)
    before = _table_rows(migrated_db)
    headers = {**_bearer(token), **kwargs.pop("headers", {})}

    response = seeded.request("DELETE", "/account", headers=headers, **kwargs)

    assert response.status_code == 409
    contract("Error").validate(response.json())
    assert response.json() == DEMO_ERROR
    assert _table_rows(migrated_db) == before
    # The token still works, and the data is all there.
    assert len(seeded.get("/entries", headers=_bearer(token)).json()["entries"]) == len(
        SAMPLE_ENTRIES
    )


def test_fr_x1_deleting_with_an_invalid_token_returns_not_authenticated(
    seeded: TestClient, migrated_db: Engine
):
    before = _table_rows(migrated_db)

    response = seeded.request("DELETE", "/account", headers=_bearer("not-a-token"), json={})

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert _table_rows(migrated_db) == before


def test_fr_x1_other_users_can_still_delete_their_account(seeded: TestClient, migrated_db: Engine):
    _register(seeded)
    token = _login(seeded)
    demo_before = _table_rows(migrated_db, _user(migrated_db, DEMO).id)

    response = seeded.request(
        "DELETE", "/account", headers=_bearer(token), json={"current_password": ALICE_PASSWORD}
    )

    assert response.status_code == 204
    assert _user(migrated_db, ALICE) is None
    assert _table_rows(migrated_db, _user(migrated_db, DEMO).id) == demo_before


# --- Seed and reset -----------------------------------------------------------------------


@pytest.fixture
def script_env(test_database_url: str, migrated_db: Engine, monkeypatch) -> Iterator[None]:
    """The environment the script reads, pointed at the test database."""
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", ALLOWED_ORIGIN)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("DEMO_EMAIL", DEMO)
    yield


def test_fr_x1_script_creates_the_demo_account_with_the_sample_data(
    script_env, api: TestClient, migrated_db: Engine, capsys
):
    assert _user(migrated_db, DEMO) is None

    assert seed_demo.main() == 0

    output = capsys.readouterr().out
    assert f"Reset the demo account {DEMO}" in output
    user = _user(migrated_db, DEMO)
    assert user is not None
    content = _demo_content(api, _demo_token(api))
    assert len(content["entries"]) == len(SAMPLE_ENTRIES)
    assert len(content["summaries"]) == len(SAMPLE_SUMMARIES)


def test_fr_x1_script_does_nothing_when_the_demo_is_off(
    script_env, migrated_db: Engine, monkeypatch, capsys
):
    monkeypatch.setenv("DEMO_EMAIL", "")
    before = _table_rows(migrated_db)

    assert seed_demo.main() == 0

    assert "The demo is turned off" in capsys.readouterr().out
    assert _table_rows(migrated_db) == before


def test_fr_x1_random_password_is_never_stored_logged_or_shown(
    script_env, migrated_db: Engine, monkeypatch, capsys, caplog
):
    passwords = []
    original = app.demo_seed.random_password

    def recording() -> str:
        passwords.append(original())
        return passwords[-1]

    monkeypatch.setattr(app.demo_seed, "random_password", recording)
    caplog.set_level(logging.DEBUG)

    assert seed_demo.main() == 0
    assert seed_demo.main() == 0

    first, second = passwords
    assert first != second
    stored = _user(migrated_db, DEMO).password_hash
    assert stored.startswith("$argon2id$")
    # The hash is of the newest random password; the earlier one no longer works.
    assert verify_password(stored, second)
    assert not verify_password(stored, first)
    output = capsys.readouterr()
    everything = output.out + output.err + caplog.text + str(_table_rows(migrated_db))
    assert first not in everything
    assert second not in everything


def test_fr_x1_running_the_script_twice_gives_the_same_result(
    seeded: TestClient, migrated_db: Engine
):
    token = _demo_token(seeded)
    first = _demo_content(seeded, token)
    first_id = _user(migrated_db, DEMO).id

    _seed(migrated_db)

    assert _demo_content(seeded, token) == first
    assert _user(migrated_db, DEMO).id == first_id
    with migrated_db.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM users WHERE email = :email"), {"email": DEMO}
            ).scalar_one()
            == 1
        )


def test_fr_x1_reset_restores_the_sample_data_after_a_visitor_changed_it(
    seeded: TestClient, migrated_db: Engine
):
    token = _demo_token(seeded)
    original = _demo_content(seeded, token)
    _visitor_changes(seeded, token)
    assert _demo_content(seeded, token) != original

    _seed(migrated_db)

    assert _demo_content(seeded, token) == original
    # The visitor's tag is gone too, not only its entry.
    assert "Visitor tag" not in seeded.get("/tags", headers=_bearer(token)).json()["tags"]


def test_fr_x1_reset_keeps_tokens_and_ai_usage(seeded: TestClient, migrated_db: Engine):
    token = _demo_token(seeded)
    assert (
        seeded.post(
            "/suggestions", json={"text": "Fixed a bug."}, headers=_bearer(token)
        ).status_code
        == 200
    )
    demo_id = _user(migrated_db, DEMO).id
    before = _table_rows(migrated_db, demo_id)

    _seed(migrated_db)

    after = _table_rows(migrated_db, demo_id)
    # Visitors stay logged in, and a reset does not give back AI requests.
    assert after["tokens"] == before["tokens"]
    assert after["ai_usage"] == before["ai_usage"]
    assert after["ai_usage_global"] == before["ai_usage_global"]


def test_fr_x1_reset_never_touches_other_users(api: TestClient, migrated_db: Engine):
    _register(api)
    token = _login(api)
    headers = _bearer(token)
    for name in ("Mentoring", "Python", "Own tag"):  # names the sample data also uses
        assert (
            api.post(
                "/entries",
                json={
                    "text": f"Alice {name}.",
                    "date": "2026-11-01",
                    "category": "Achievement",
                    "tags": [name],
                },
                headers=headers,
            ).status_code
            == 201
        )
    assert (
        api.post(
            "/summaries",
            json={"period_start": "2026-11-01", "period_end": "2026-11-01"},
            headers=headers,
        ).status_code
        == 201
    )
    alice_id = _user(migrated_db, ALICE).id
    before = _table_rows(migrated_db, alice_id)

    _seed(migrated_db)
    _seed(migrated_db)

    assert _table_rows(migrated_db, alice_id) == before
    assert _login(api)  # Alice's password still works


def test_fr_x1_script_takes_over_an_existing_user_with_the_demo_email(
    api: TestClient, migrated_db: Engine
):
    # Someone registered the demo email before the first seed: the seed makes it the demo
    # account, with a new random password, so their password stops working.
    _register(api, DEMO, ALICE_PASSWORD)
    assert (
        api.post(
            "/entries",
            json={"text": "Mine.", "date": "2026-11-01", "category": "Learning"},
            headers=_bearer(_login(api, DEMO)),
        ).status_code
        == 201
    )

    _seed(migrated_db)

    response = api.post("/auth/login", json={"email": DEMO, "password": ALICE_PASSWORD})
    assert response.status_code == 401
    content = _demo_content(api, _demo_token(api))
    assert "Mine." not in [entry[2] for entry in content["entries"]]
    assert len(content["entries"]) == len(SAMPLE_ENTRIES)


def test_fr_x1_seeding_makes_no_ai_call(seeded: TestClient, migrated_db: Engine):
    rows = _table_rows(migrated_db)

    assert rows["ai_usage"] == []
    assert rows["ai_usage_global"] == []


# --- Sample data rules, as visitors see them -----------------------------------------------


def _months_before(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def test_fr_x1_sample_data_rules_hold_in_the_database(seeded: TestClient):
    token = _demo_token(seeded)
    headers = _bearer(token)
    entries = seeded.get("/entries", headers=headers).json()["entries"]
    tags = seeded.get("/tags", headers=headers).json()["tags"]
    summaries = seeded.get("/summaries", headers=headers).json()["summaries"]

    assert len(entries) >= 20
    assert {entry["category"] for entry in entries} == set(CATEGORIES)
    assert len(tags) >= 5
    assert any(entry["result_impact"] for entry in entries)
    assert any("für" in entry["text"] or "español" in entry["text"] for entry in entries)
    dates = [dt.date.fromisoformat(entry["date"]) for entry in entries]
    assert max(dates) == TODAY - dt.timedelta(days=2)
    assert min(dates) >= _months_before(TODAY, 6)
    # Newest first, as the list always is.
    assert dates == sorted(dates, reverse=True)

    assert len(summaries) >= 1
    for summary in summaries:
        assert summary["text"].strip()
        summary_filter = summary["filter"]
        params = {
            "start_date": summary_filter["period_start"],
            "end_date": summary_filter["period_end"],
            "category": summary_filter["categories"],
            "tag": summary_filter["tags"],
        }
        matching = seeded.get("/entries", params=params, headers=headers).json()["entries"]
        assert matching, summary_filter


def test_fr_x1_sample_dates_follow_the_day_of_the_run(seeded: TestClient, migrated_db: Engine):
    later = TODAY + dt.timedelta(days=40)

    _seed(migrated_db, later)

    entries = seeded.get("/entries", headers=_bearer(_demo_token(seeded))).json()["entries"]
    assert entries[0]["date"] == (later - dt.timedelta(days=2)).isoformat()
