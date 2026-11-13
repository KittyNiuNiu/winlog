"""Login and demo-login attempt limits against the real test database (FR-A4, issue #46).

Failed logins per email (default 10 within 15 minutes), counted together with wrong
passwords on account deletion, and demo-logins per visitor IP (default 20 within 60
minutes). The settings, the IP parsing and the contract are tested in
tests/unit/test_attempt_limits.py.
"""

import datetime as dt
import hashlib
import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.orm import Session

import app.accounts
from app.attempt_limits import AttemptLimiter
from app.demo_seed import reset_demo_account
from app.main import create_app
from app.models import LoginAttempt, Token, User
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

ALICE = "alice@example.com"
ALICE_PASSWORD = "Correct-Horse-7"
WRONG_PASSWORD = "Wrong-Horse-8"
NOBODY = "nobody@example.com"
DEMO = "demo@example.com"
VISITOR = "203.0.113.7"
START = dt.datetime(2026, 11, 13, 9, 0, tzinfo=dt.UTC)


# --- Helpers ------------------------------------------------------------------------------


class Clock:
    """A clock the test moves forward by hand."""

    def __init__(self, now: dt.datetime = START) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += dt.timedelta(**delta)


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
def settings(test_database_url: str, migrated_db: Engine) -> Settings:
    return _settings(test_database_url)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def api(settings: Settings, clock: Clock) -> TestClient:
    """The app with the default limits, the demo turned on and a clock the test controls."""
    application = create_app(settings)
    application.state.attempt_limiter = AttemptLimiter.from_settings(
        application.state.engine, settings, clock
    )
    return TestClient(application)


@pytest.fixture
def alice(api: TestClient) -> None:
    response = api.post("/auth/register", json={"email": ALICE, "password": ALICE_PASSWORD})
    assert response.status_code == 201


@pytest.fixture
def demo(migrated_db: Engine) -> uuid.UUID:
    with Session(migrated_db) as session:
        result = reset_demo_account(session, DEMO, dt.date(2026, 11, 13))
        session.commit()
    return result.user_id


@pytest.fixture
def password_checks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Records every password check of login and account deletion (real and dummy hash)."""
    checks: list[str] = []
    verify = app.accounts.verify_password
    dummy = app.accounts.verify_against_dummy_hash

    def verify_spy(password_hash: str, password: str) -> bool:
        checks.append("verify")
        return verify(password_hash, password)

    def dummy_spy(password: str) -> None:
        checks.append("dummy")
        dummy(password)

    monkeypatch.setattr(app.accounts, "verify_password", verify_spy)
    monkeypatch.setattr(app.accounts, "verify_against_dummy_hash", dummy_spy)
    return checks


def _login(client: TestClient, email: str = ALICE, password: str = WRONG_PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _token(client: TestClient) -> str:
    response = _login(client, password=ALICE_PASSWORD)
    assert response.status_code == 200
    return response.json()["token"]


def _delete(client: TestClient, token: str, password: str):
    return client.request(
        "DELETE",
        "/account",
        json={"current_password": password},
        headers={"Authorization": f"Bearer {token}"},
    )


def _demo_login(client: TestClient, forwarded_for: str | None = VISITOR):
    headers = {} if forwarded_for is None else {"X-Forwarded-For": forwarded_for}
    return client.post("/auth/demo", headers=headers)


def _fail(client: TestClient, times: int, email: str = ALICE) -> None:
    for _ in range(times):
        assert _login(client, email).status_code == 401


def _assert_too_many_attempts(response, contract, retry_after: int | None = None) -> None:
    assert response.status_code == 429
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "too_many_attempts"
    seconds = response.headers["Retry-After"]
    assert seconds.isdigit()
    if retry_after is not None:
        assert int(seconds) == retry_after
    assert "token" not in body


def _tokens(engine: Engine) -> int:
    with engine.connect() as connection:
        return connection.execute(select(func.count()).select_from(Token)).scalar_one()


def _rows(engine: Engine) -> list[tuple]:
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                select(
                    LoginAttempt.kind,
                    LoginAttempt.key_hash,
                    LoginAttempt.window_start,
                    LoginAttempt.attempt_count,
                ).order_by(LoginAttempt.kind, LoginAttempt.key_hash)
            )
        ]


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _count(engine: Engine, kind: str, key: str) -> int | None:
    with engine.connect() as connection:
        return connection.execute(
            select(LoginAttempt.attempt_count).where(
                LoginAttempt.kind == kind, LoginAttempt.key_hash == _sha256(key)
            )
        ).scalar_one_or_none()


def _user_exists(engine: Engine, email: str) -> bool:
    with engine.connect() as connection:
        return (
            connection.execute(select(User.id).where(User.email == email)).one_or_none() is not None
        )


# --- Failed logins per email --------------------------------------------------------------


def test_fr_a4_tenth_failed_login_allowed_and_eleventh_refused(
    api: TestClient, migrated_db: Engine, alice, contract
):
    for attempt in range(1, 11):
        response = _login(api)
        assert response.status_code == 401, attempt
        assert response.json()["code"] == "invalid_credentials"

    _assert_too_many_attempts(_login(api), contract)
    assert _count(migrated_db, "login", ALICE) == 10


def test_fr_a4_eleventh_failed_login_refused(api: TestClient, alice, contract):
    _fail(api, 10)

    for _ in range(3):
        _assert_too_many_attempts(_login(api), contract)


def test_fr_a4_correct_password_refused_while_blocked(
    api: TestClient, migrated_db: Engine, alice, password_checks, contract
):
    _fail(api, 10)
    password_checks.clear()
    tokens = _tokens(migrated_db)

    _assert_too_many_attempts(_login(api, password=ALICE_PASSWORD), contract)

    assert password_checks == []  # no password was checked
    assert _tokens(migrated_db) == tokens  # no token was created


def test_fr_a4_refused_attempts_do_not_extend_the_block(
    api: TestClient, alice, clock: Clock, contract
):
    _fail(api, 10)
    for _ in range(5):
        clock.advance(minutes=1)
        _assert_too_many_attempts(_login(api), contract)

    clock.advance(minutes=10)  # 15 minutes after the first failure

    assert _login(api, password=ALICE_PASSWORD).status_code == 200


def test_fr_a4_unknown_emails_counted_the_same_way(
    api: TestClient, migrated_db: Engine, alice, password_checks, contract
):
    for attempt in range(10):
        unknown = _login(api, NOBODY)
        existing = _login(api, ALICE)
        assert unknown.status_code == existing.status_code == 401, attempt
        assert unknown.json() == existing.json()

    unknown = _login(api, NOBODY)
    existing = _login(api, ALICE)
    _assert_too_many_attempts(unknown, contract)
    _assert_too_many_attempts(existing, contract)
    assert unknown.json() == existing.json()
    assert unknown.headers["Retry-After"] == existing.headers["Retry-After"]
    assert _count(migrated_db, "login", NOBODY) == _count(migrated_db, "login", ALICE) == 10
    # While blocked, not even the dummy hash is checked for the unknown email.
    assert password_checks.count("dummy") == 10


def test_fr_a4_email_is_counted_after_trimming_and_lower_casing(
    api: TestClient, migrated_db: Engine, alice, contract
):
    spellings = [
        "alice@example.com",
        "ALICE@example.com",
        " Alice@Example.COM ",
        "aLiCe@EXAMPLE.com",
    ]
    for attempt in range(10):
        assert _login(api, spellings[attempt % len(spellings)]).status_code == 401

    for spelling in spellings:
        _assert_too_many_attempts(_login(api, spelling, ALICE_PASSWORD), contract)
    assert _count(migrated_db, "login", ALICE) == 10


def test_fr_a4_limit_is_per_email(api: TestClient, alice, contract):
    _fail(api, 10, NOBODY)
    _assert_too_many_attempts(_login(api, NOBODY), contract)

    assert _login(api, password=ALICE_PASSWORD).status_code == 200


def test_fr_a4_successful_login_clears_the_count(
    api: TestClient, migrated_db: Engine, alice, contract
):
    _fail(api, 9)
    assert _count(migrated_db, "login", ALICE) == 9

    assert _login(api, password=ALICE_PASSWORD).status_code == 200
    assert _count(migrated_db, "login", ALICE) is None

    # A full new allowance: ten more failures before the block.
    _fail(api, 10)
    _assert_too_many_attempts(_login(api), contract)


def test_fr_a4_block_ends_after_the_window(api: TestClient, alice, clock: Clock, contract):
    _fail(api, 1)
    clock.advance(minutes=5)
    _fail(api, 9)  # the tenth failure, 5 minutes after the first
    _assert_too_many_attempts(_login(api, password=ALICE_PASSWORD), contract)

    # Refused until 15 minutes after the first failure of the window.
    clock.advance(minutes=10, seconds=-1)
    _assert_too_many_attempts(_login(api, password=ALICE_PASSWORD), contract, retry_after=1)
    clock.advance(seconds=1)

    assert _login(api, password=ALICE_PASSWORD).status_code == 200


def test_fr_a4_a_new_window_starts_after_the_old_one_ends(
    api: TestClient, migrated_db: Engine, alice, clock: Clock, contract
):
    _fail(api, 10)
    clock.advance(minutes=15)

    _fail(api, 1)  # the first failure of a new window
    assert _count(migrated_db, "login", ALICE) == 1
    _fail(api, 9)
    _assert_too_many_attempts(_login(api), contract, retry_after=15 * 60)


def test_fr_a4_failures_spread_beyond_the_window_never_block(api: TestClient, alice, clock: Clock):
    # 9 failures per window, never 10 within one window.
    for _ in range(3):
        _fail(api, 9)
        clock.advance(minutes=15)

    assert _login(api, password=ALICE_PASSWORD).status_code == 200


def test_fr_a4_retry_after_is_the_seconds_left_in_the_window(
    api: TestClient, alice, clock: Clock, contract
):
    _fail(api, 10)
    _assert_too_many_attempts(_login(api), contract, retry_after=900)

    clock.advance(minutes=4, seconds=30.5)

    # 629.5 seconds left, rounded up.
    _assert_too_many_attempts(_login(api), contract, retry_after=630)


def test_fr_a4_retry_after_is_readable_from_another_origin(api: TestClient, alice):
    _fail(api, 10)

    response = api.post(
        "/auth/login",
        json={"email": ALICE, "password": WRONG_PASSWORD},
        headers={"Origin": ALLOWED_ORIGIN},
    )

    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "retry-after" in {name.strip() for name in exposed.split(",")}


def test_fr_a4_limits_come_from_the_settings(
    test_database_url: str, migrated_db: Engine, clock: Clock, contract
):
    settings = _settings(
        test_database_url, login_max_failed_attempts=3, login_attempt_window_minutes=2
    )
    application = create_app(settings)
    application.state.attempt_limiter = AttemptLimiter.from_settings(
        application.state.engine, settings, clock
    )
    client = TestClient(application)

    _fail(client, 3, NOBODY)
    _assert_too_many_attempts(_login(client, NOBODY), contract, retry_after=120)
    clock.advance(minutes=2)
    assert _login(client, NOBODY).status_code == 401


def test_fr_a4_counts_survive_a_restart(
    settings: Settings, api: TestClient, alice, clock: Clock, contract
):
    _fail(api, 10)

    # A new app with a new limiter, as after a restart, at the same moment.
    restarted_app = create_app(settings)
    restarted_app.state.attempt_limiter = AttemptLimiter.from_settings(
        restarted_app.state.engine, settings, clock
    )
    restarted = TestClient(restarted_app)

    _assert_too_many_attempts(_login(restarted, password=ALICE_PASSWORD), contract)


def test_fr_a4_app_uses_the_real_clock_by_default(
    settings: Settings, migrated_db: Engine, contract
):
    client = TestClient(create_app(settings))
    _fail(client, 10, NOBODY)

    response = _login(client, NOBODY)

    _assert_too_many_attempts(response, contract)
    assert 899 <= int(response.headers["Retry-After"]) <= 900


# --- Account deletion ---------------------------------------------------------------------


def test_fr_a4_wrong_deletion_passwords_count_toward_the_login_limit(
    api: TestClient, migrated_db: Engine, alice, contract
):
    token = _token(api)
    for _ in range(10):
        assert _delete(api, token, WRONG_PASSWORD).status_code == 403

    assert _count(migrated_db, "login", ALICE) == 10
    _assert_too_many_attempts(_login(api, password=ALICE_PASSWORD), contract)


def test_fr_a4_login_and_deletion_failures_add_up(api: TestClient, alice, contract):
    token = _token(api)
    _fail(api, 5)
    for _ in range(5):
        assert _delete(api, token, WRONG_PASSWORD).status_code == 403

    _assert_too_many_attempts(_delete(api, token, WRONG_PASSWORD), contract)
    _assert_too_many_attempts(_login(api), contract)


def test_fr_a4_deletion_refused_while_blocked_without_checking_the_password(
    api: TestClient, migrated_db: Engine, alice, password_checks, contract
):
    token = _token(api)
    _fail(api, 10)
    password_checks.clear()

    _assert_too_many_attempts(_delete(api, token, ALICE_PASSWORD), contract)

    assert password_checks == []
    assert _user_exists(migrated_db, ALICE)
    # The login still works: only the deletion was refused.
    assert api.get("/entries", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_fr_a4_deletion_works_again_after_the_window(
    api: TestClient, migrated_db: Engine, alice, clock: Clock, contract
):
    token = _token(api)
    for _ in range(10):
        assert _delete(api, token, WRONG_PASSWORD).status_code == 403
    _assert_too_many_attempts(_delete(api, token, ALICE_PASSWORD), contract)

    clock.advance(minutes=15)

    assert _delete(api, token, ALICE_PASSWORD).status_code == 204
    assert not _user_exists(migrated_db, ALICE)
    assert _rows(migrated_db) == []


def test_fr_a4_deletion_validation_error_comes_before_the_limit(
    api: TestClient, migrated_db: Engine, alice
):
    token = _token(api)
    _fail(api, 10)

    response = api.request(
        "DELETE", "/account", json={}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 422
    assert _count(migrated_db, "login", ALICE) == 10


def test_fr_a4_deleting_the_demo_account_gets_the_demo_error_and_counts_nothing(
    api: TestClient, migrated_db: Engine, demo
):
    token = _demo_login(api).json()["token"]

    response = _delete(api, token, WRONG_PASSWORD)

    assert response.status_code == 409
    assert _count(migrated_db, "login", DEMO) is None


# --- Demo-logins per visitor IP -----------------------------------------------------------


def test_fr_a4_demo_login_limit_per_ip(api: TestClient, migrated_db: Engine, demo, contract):
    for attempt in range(20):
        assert _demo_login(api).status_code == 200, attempt
    tokens = _tokens(migrated_db)

    _assert_too_many_attempts(_demo_login(api), contract, retry_after=3600)

    assert _tokens(migrated_db) == tokens  # no token was created
    # Another visitor is not affected.
    assert _demo_login(api, "198.51.100.23").status_code == 200


def test_fr_a4_demo_login_limit_ends_after_the_window(
    api: TestClient, demo, clock: Clock, contract
):
    for _ in range(20):
        assert _demo_login(api).status_code == 200
        clock.advance(minutes=1)
    _assert_too_many_attempts(_demo_login(api), contract, retry_after=40 * 60)

    clock.advance(minutes=40)

    assert _demo_login(api).status_code == 200


def test_fr_a4_every_demo_login_request_counts(api: TestClient, migrated_db: Engine, contract):
    # The demo account is not seeded, so every request is "not found"; each one still counts.
    for _ in range(20):
        assert _demo_login(api).status_code == 404

    _assert_too_many_attempts(_demo_login(api), contract)
    assert _count(migrated_db, "demo", VISITOR) == 20


def test_fr_a4_demo_login_uses_only_the_proxys_x_forwarded_for_entry(
    api: TestClient, migrated_db: Engine, demo, contract
):
    # Whatever a client puts in front, the proxy's own (last) entry decides.
    for attempt in range(20):
        spoofed = f"10.0.0.{attempt}, 192.0.2.{attempt}, {VISITOR}"
        assert _demo_login(api, spoofed).status_code == 200

    _assert_too_many_attempts(_demo_login(api, f"192.0.2.99,{VISITOR}"), contract)
    _assert_too_many_attempts(_demo_login(api, VISITOR), contract)
    assert _count(migrated_db, "demo", VISITOR) == 20
    assert len(_rows(migrated_db)) == 1


def test_fr_a4_demo_login_without_x_forwarded_for_uses_the_connection_address(
    api: TestClient, migrated_db: Engine, demo
):
    assert _demo_login(api, forwarded_for=None).status_code == 200

    # Starlette's test client connects from the host "testclient".
    assert _count(migrated_db, "demo", "testclient") == 1


def test_fr_a4_demo_logins_and_failed_logins_are_counted_apart(
    api: TestClient, migrated_db: Engine, alice, demo
):
    for _ in range(20):
        assert _demo_login(api).status_code == 200

    assert _login(api, password=ALICE_PASSWORD).status_code == 200
    _fail(api, 10)
    assert _count(migrated_db, "demo", VISITOR) == 20
    assert _count(migrated_db, "login", ALICE) == 10


# --- Parallel attempts --------------------------------------------------------------------


def _race(calls: list[Callable[[], object]]) -> list:
    """Run the calls in parallel threads that start together."""
    barrier = threading.Barrier(len(calls))

    def run(call: Callable[[], object]):
        barrier.wait()
        return call()

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


def _statuses(responses) -> dict[int, int]:
    statuses: dict[int, int] = {}
    for response in responses:
        statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
    return statuses


@pytest.mark.parametrize("attempt", range(3))
def test_fr_a4_parallel_failed_logins_cannot_get_past_the_limit(
    api: TestClient, migrated_db: Engine, alice, password_checks, attempt
):
    responses = _race([lambda: _login(api) for _ in range(25)])

    assert _statuses(responses) == {401: 10, 429: 15}
    assert password_checks.count("verify") == 10
    assert _count(migrated_db, "login", ALICE) == 10


@pytest.mark.parametrize("attempt", range(3))
def test_fr_a4_parallel_attempts_for_the_last_slot_let_exactly_one_through(
    api: TestClient, migrated_db: Engine, alice, attempt
):
    _fail(api, 9)

    responses = _race([lambda: _login(api, password=ALICE_PASSWORD) for _ in range(10)])

    # One correct login took the last slot; the others were refused unchecked.
    assert _statuses(responses) == {200: 1, 429: 9}


@pytest.mark.parametrize("attempt", range(3))
def test_fr_a4_parallel_failed_logins_and_deletions_share_the_limit(
    api: TestClient, migrated_db: Engine, alice, attempt
):
    token = _token(api)

    responses = _race(
        [lambda: _login(api) for _ in range(10)]
        + [lambda: _delete(api, token, WRONG_PASSWORD) for _ in range(10)]
    )

    statuses = _statuses(responses)
    assert statuses[429] == 10
    assert statuses.get(401, 0) + statuses.get(403, 0) == 10
    assert _count(migrated_db, "login", ALICE) == 10


@pytest.mark.parametrize("attempt", range(3))
def test_fr_a4_parallel_demo_logins_cannot_get_past_the_limit(
    api: TestClient, migrated_db: Engine, demo, attempt
):
    tokens = _tokens(migrated_db)

    responses = _race([lambda: _demo_login(api) for _ in range(30)])

    assert _statuses(responses) == {200: 20, 429: 10}
    assert _tokens(migrated_db) == tokens + 20
    assert _count(migrated_db, "demo", VISITOR) == 20


def test_fr_a4_parallel_attempts_for_many_keys_do_not_deadlock(
    api: TestClient, migrated_db: Engine, clock: Clock
):
    # Ended windows for many keys, so every request also runs the cleanup at the same time.
    with migrated_db.begin() as connection:
        connection.execute(
            insert(LoginAttempt),
            [
                {
                    "kind": "login",
                    "key_hash": _sha256(f"old{number}@example.com"),
                    "window_start": START - dt.timedelta(hours=1),
                    "attempt_count": 3,
                }
                for number in range(200)
            ],
        )

    responses = _race(
        [lambda number=number: _login(api, f"user{number}@example.com") for number in range(20)]
        + [lambda number=number: _demo_login(api, f"192.0.2.{number}") for number in range(20)]
    )

    assert _statuses(responses) == {401: 20, 404: 20}
    assert len(_rows(migrated_db)) == 40


# --- Storage and privacy ------------------------------------------------------------------


def test_fr_a4_old_rows_deleted_when_new_attempts_are_written(api: TestClient, migrated_db: Engine):
    def row(kind: str, key: str, minutes_ago: int) -> dict:
        return {
            "kind": kind,
            "key_hash": _sha256(key),
            "window_start": START - dt.timedelta(minutes=minutes_ago),
            "attempt_count": 5,
        }

    with migrated_db.begin() as connection:
        connection.execute(
            insert(LoginAttempt),
            [
                row("login", "ended@example.com", 15),  # its 15-minute window has ended
                row("login", "current@example.com", 14),
                row("demo", "192.0.2.1", 60),  # its 60-minute window has ended
                row("demo", "192.0.2.2", 20),  # older than 15 minutes, but a demo window
            ],
        )

    assert _login(api, NOBODY).status_code == 401

    assert {(kind, key_hash) for kind, key_hash, *_ in _rows(migrated_db)} == {
        ("login", _sha256("current@example.com")),
        ("demo", _sha256("192.0.2.2")),
        ("login", _sha256(NOBODY)),
    }


def test_fr_a4_demo_logins_also_delete_old_rows(api: TestClient, migrated_db: Engine):
    with migrated_db.begin() as connection:
        connection.execute(
            insert(LoginAttempt).values(
                kind="login",
                key_hash=_sha256(NOBODY),
                window_start=START - dt.timedelta(minutes=30),
                attempt_count=10,
            )
        )

    _demo_login(api)

    assert [kind for kind, *_ in _rows(migrated_db)] == ["demo"]


def test_fr_a4_table_holds_hashes_not_plain_values(
    api: TestClient, migrated_db: Engine, alice, demo
):
    _fail(api, 2)
    _fail(api, 1, " NoBody@Example.com ")
    _demo_login(api)

    rows = _rows(migrated_db)
    assert {(kind, key_hash) for kind, key_hash, *_ in rows} == {
        ("login", _sha256(ALICE)),
        ("login", _sha256(NOBODY)),
        ("demo", _sha256(VISITOR)),
    }
    text = repr(rows).lower()
    for plain in (ALICE, NOBODY, "nobody", "alice", VISITOR, WRONG_PASSWORD.lower()):
        assert plain not in text


def test_fr_a4_window_start_is_the_first_counted_attempt(
    api: TestClient, migrated_db: Engine, alice, clock: Clock
):
    _fail(api, 1)
    clock.advance(minutes=3)
    _fail(api, 1)

    [(_kind, _hash, window_start, count)] = _rows(migrated_db)
    assert window_start == START
    assert count == 2


def test_fr_a4_emails_ips_and_passwords_never_appear_in_logs(
    api: TestClient, alice, demo, caplog, contract
):
    caplog.set_level(logging.DEBUG)

    _fail(api, 10)
    _assert_too_many_attempts(_login(api, password=ALICE_PASSWORD), contract)
    _fail(api, 1, NOBODY)
    for _ in range(21):
        _demo_login(api)

    for secret in (ALICE, NOBODY, VISITOR, ALICE_PASSWORD, WRONG_PASSWORD, _sha256(ALICE)):
        assert secret not in caplog.text


def test_fr_a4_cleared_count_is_gone_from_the_table(api: TestClient, migrated_db: Engine, alice):
    _fail(api, 3)

    assert _login(api, password=ALICE_PASSWORD).status_code == 200

    with migrated_db.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(LoginAttempt).where(LoginAttempt.kind == "login")
            ).scalar_one()
            == 0
        )


def test_fr_a4_block_also_ends_when_the_window_start_is_moved_back(
    api: TestClient, migrated_db: Engine, alice
):
    """The window is read from the stored row, so the block depends only on the database."""
    _fail(api, 10)
    with migrated_db.begin() as connection:
        connection.execute(
            update(LoginAttempt).values(window_start=START - dt.timedelta(minutes=15))
        )

    assert _login(api, password=ALICE_PASSWORD).status_code == 200
