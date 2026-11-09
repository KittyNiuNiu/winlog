"""Login, logout and request authentication against the real test database (FR-A2, FR-A3)."""

import datetime as dt
import hashlib
import logging
import statistics
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, insert, select, update

import app.passwords
from app.auth import CurrentUser, hash_token
from app.main import create_app
from app.models import Token, User
from app.passwords import hash_password
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

PASSWORD = "Correct-Horse-7"
BOB_PASSWORD = "Battery-Staple-9"


def _add_whoami(app: FastAPI) -> None:
    """A route used only by these tests: answers with the user the token identifies."""

    @app.get("/test/whoami")
    def whoami(user: CurrentUser) -> dict:
        return {"email": user.email}


@pytest.fixture
def api(client: TestClient) -> TestClient:
    _add_whoami(client.app)
    return client


def _register(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD):
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    return response


def _login(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _token(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD) -> str:
    response = _login(client, email, password)
    assert response.status_code == 200
    return response.json()["token"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _whoami(client: TestClient, token: str):
    return client.get("/test/whoami", headers=_bearer(token))


def _logout(client: TestClient, token: str):
    return client.post("/auth/logout", headers=_bearer(token))


def _tokens(engine: Engine) -> list:
    with engine.connect() as connection:
        return list(connection.execute(select(Token)).all())


def _user_id(engine: Engine, email: str):
    with engine.connect() as connection:
        return connection.execute(select(User.id).where(User.email == email)).scalar_one()


def _assert_not_authenticated(response, contract) -> None:
    assert response.status_code == 401
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def _assert_invalid_credentials(response, contract) -> None:
    assert response.status_code == 401
    body = response.json()
    contract("Error").validate(body)
    assert body == {"code": "invalid_credentials", "message": "Wrong email or password."}


# --- Login ---------------------------------------------------------------------------------


def test_fr_a2_valid_login_returns_a_token(api: TestClient, migrated_db: Engine, contract):
    _register(api)
    before = dt.datetime.now(dt.UTC)

    response = _login(api)

    assert response.status_code == 200
    body = response.json()
    contract("LoginResult").validate(body)
    assert set(body) == {"token", "expires_at"}
    expires_at = dt.datetime.fromisoformat(body["expires_at"])
    assert before + dt.timedelta(days=7) <= expires_at <= before + dt.timedelta(days=7, minutes=1)
    assert _whoami(api, body["token"]).json() == {"email": "alice@example.com"}


def test_fr_a2_only_the_sha256_hash_of_the_token_is_stored(api: TestClient, migrated_db: Engine):
    _register(api)

    token = _token(api)

    [row] = _tokens(migrated_db)
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in [str(value) for value in row]
    assert row.user_id == _user_id(migrated_db, "alice@example.com")
    assert row.expires_at - row.created_at == dt.timedelta(days=7)


def test_fr_a2_token_lifetime_comes_from_the_setting(
    test_database_url: str, migrated_db: Engine, contract
):
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        token_lifetime_days=2,
    )
    client = TestClient(create_app(settings))
    _register(client)
    before = dt.datetime.now(dt.UTC)

    body = _login(client).json()

    expires_at = dt.datetime.fromisoformat(body["expires_at"])
    assert before + dt.timedelta(days=2) <= expires_at <= before + dt.timedelta(days=2, minutes=1)
    [row] = _tokens(migrated_db)
    assert row.expires_at - row.created_at == dt.timedelta(days=2)


def test_fr_a2_email_is_trimmed_and_compared_in_lower_case(api: TestClient, migrated_db: Engine):
    _register(api, email="Alice@Example.com")

    response = _login(api, email="  ALICE@example.COM ")

    assert response.status_code == 200
    assert _whoami(api, response.json()["token"]).json() == {"email": "alice@example.com"}


def test_fr_a2_wrong_password_and_unknown_email_get_the_same_error(
    api: TestClient, migrated_db: Engine, contract
):
    _register(api)

    wrong_password = _login(api, password="Correct-Horse-8")
    unknown_email = _login(api, email="nobody@example.com")

    _assert_invalid_credentials(wrong_password, contract)
    _assert_invalid_credentials(unknown_email, contract)
    assert wrong_password.json() == unknown_email.json()
    assert dict(wrong_password.headers) == dict(unknown_email.headers)
    assert _tokens(migrated_db) == []


def test_fr_a2_password_is_checked_exactly_as_typed(api: TestClient, migrated_db: Engine):
    _register(api, password=" Abcdefg1x ")

    assert _login(api, password="Abcdefg1x").status_code == 401
    assert _login(api, password=" Abcdefg1x ").status_code == 200


class _HasherSpy:
    """Stands in for the argon2 hasher: records which hashes it checks, and still checks them."""

    def __init__(self, hasher) -> None:
        self.hasher = hasher
        self.hashes: list[str] = []

    def verify(self, password_hash: str, password: str) -> bool:
        self.hashes.append(password_hash)
        return self.hasher.verify(password_hash, password)


def _argon2_parameters(password_hash: str) -> str:
    # "$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>" -> "$argon2id$v=19$m=65536,t=3,p=4"
    return "$".join(password_hash.split("$")[:4])


def test_fr_a2_unknown_email_still_checks_a_dummy_hash(
    api: TestClient, migrated_db: Engine, monkeypatch
):
    _register(api)
    with migrated_db.connect() as connection:
        real_hash = connection.execute(select(User.password_hash)).scalar_one()
    spy = _HasherSpy(app.passwords._hasher)
    monkeypatch.setattr(app.passwords, "_hasher", spy)

    assert _login(api, email="nobody@example.com").status_code == 401
    assert _login(api, password="Correct-Horse-8").status_code == 401

    dummy, checked_real = spy.hashes
    assert checked_real == real_hash
    assert dummy != real_hash
    assert _argon2_parameters(dummy) == _argon2_parameters(real_hash)


def test_fr_a2_unknown_email_takes_about_as_long_as_a_wrong_password(
    api: TestClient, migrated_db: Engine
):
    _register(api)

    def median_seconds(email: str) -> float:
        durations = []
        for _ in range(5):
            start = time.perf_counter()
            assert _login(api, email=email, password="Correct-Horse-8").status_code == 401
            durations.append(time.perf_counter() - start)
        return statistics.median(durations)

    wrong_password = median_seconds("alice@example.com")
    unknown_email = median_seconds("nobody@example.com")

    # Without the dummy hash an unknown email answers many times faster: no argon2 check.
    assert unknown_email > wrong_password / 2


def test_fr_a2_password_of_128_characters_is_checked(api: TestClient, migrated_db: Engine):
    long_password = "A1!" + "a" * 125
    _register(api, password=long_password)

    assert _login(api, password=long_password).status_code == 200
    assert _login(api, password=long_password[:-1] + "b").status_code == 401


def test_fr_a2_login_applies_no_password_rule(api: TestClient, migrated_db: Engine, contract):
    # An account whose password no longer meets the rule, for example after a rule change.
    with migrated_db.begin() as connection:
        connection.execute(
            insert(User).values(email="old@example.com", password_hash=hash_password("old"))
        )

    assert _login(api, email="old@example.com", password="old").status_code == 200
    _assert_invalid_credentials(_login(api, email="old@example.com", password="new"), contract)


def test_fr_a2_unpaired_surrogate_in_password_returns_the_validation_error(
    api: TestClient, migrated_db: Engine, contract
):
    _register(api)
    raw = '{"email": "alice@example.com", "password": "Correct-Horse-7\\ud800"}'

    response = api.post(
        "/auth/login", content=raw.encode("ascii"), headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert [item["field"] for item in response.json()["fields"]] == ["password"]
    assert _tokens(migrated_db) == []


# --- Several tokens ------------------------------------------------------------------------


def test_fr_a2_each_login_creates_a_new_token_and_keeps_the_others(
    api: TestClient, migrated_db: Engine
):
    _register(api)

    first = _token(api)
    second = _token(api)

    assert first != second
    assert len(_tokens(migrated_db)) == 2
    assert _whoami(api, first).status_code == 200
    assert _whoami(api, second).status_code == 200


def test_fr_a2_login_deletes_the_users_expired_tokens(api: TestClient, migrated_db: Engine):
    _register(api)
    _register(api, email="bob@example.com", password=BOB_PASSWORD)
    alice_expired = _token(api)
    alice_valid = _token(api)
    bob_expired = _token(api, "bob@example.com", BOB_PASSWORD)
    yesterday = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    with migrated_db.begin() as connection:
        connection.execute(
            update(Token)
            .where(Token.token_hash.in_([hash_token(alice_expired), hash_token(bob_expired)]))
            .values(expires_at=yesterday)
        )

    alice_new = _token(api)

    stored = {row.token_hash for row in _tokens(migrated_db)}
    # Alice's expired token is gone. Her valid one stays, and Bob's tokens are not touched.
    assert stored == {hash_token(alice_valid), hash_token(alice_new), hash_token(bob_expired)}


# --- Logout --------------------------------------------------------------------------------


def test_fr_a2_logout_revokes_token(api: TestClient, migrated_db: Engine, contract):
    _register(api)
    token = _token(api)

    response = _logout(api, token)

    assert response.status_code == 204
    assert response.content == b""
    assert _tokens(migrated_db) == []
    _assert_not_authenticated(_whoami(api, token), contract)


def test_fr_a2_logged_out_token_is_not_authenticated(
    api: TestClient, migrated_db: Engine, contract
):
    _register(api)
    token = _token(api)
    _logout(api, token)

    _assert_not_authenticated(_logout(api, token), contract)


def test_fr_a2_logout_ends_only_the_current_login(api: TestClient, migrated_db: Engine):
    _register(api)
    phone = _token(api)
    laptop = _token(api)

    assert _logout(api, phone).status_code == 204

    assert _whoami(api, laptop).json() == {"email": "alice@example.com"}
    assert [row.token_hash for row in _tokens(migrated_db)] == [hash_token(laptop)]


# --- The authentication dependency ---------------------------------------------------------


def test_fr_a3_token_identifies_its_user_and_survives_another_users_logout(
    api: TestClient, migrated_db: Engine
):
    _register(api)
    _register(api, email="bob@example.com", password=BOB_PASSWORD)
    alice = _token(api)
    bob = _token(api, "bob@example.com", BOB_PASSWORD)

    assert _whoami(api, alice).json() == {"email": "alice@example.com"}
    assert _whoami(api, bob).json() == {"email": "bob@example.com"}

    assert _logout(api, bob).status_code == 204

    assert _whoami(api, alice).json() == {"email": "alice@example.com"}
    assert _logout(api, alice).status_code == 204


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Basic YWxpY2U6c2VjcmV0"},
        {"Authorization": "Token abc"},
    ],
)
def test_fr_a3_missing_or_malformed_token_is_not_authenticated(
    api: TestClient, migrated_db: Engine, contract, headers: dict
):
    _register(api)
    _token(api)

    _assert_not_authenticated(api.get("/test/whoami", headers=headers), contract)


def test_fr_a3_unknown_token_is_not_authenticated(api: TestClient, migrated_db: Engine, contract):
    _register(api)
    token = _token(api)

    _assert_not_authenticated(_whoami(api, token + "x"), contract)
    _assert_not_authenticated(_whoami(api, "a" * 43), contract)
    # The stored hash is not a token.
    _assert_not_authenticated(_whoami(api, hash_token(token)), contract)


def test_fr_a3_expired_token_is_not_authenticated(api: TestClient, migrated_db: Engine, contract):
    _register(api)
    token = _token(api)
    with migrated_db.begin() as connection:
        connection.execute(
            update(Token).values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1))
        )

    _assert_not_authenticated(_whoami(api, token), contract)
    _assert_not_authenticated(_logout(api, token), contract)


def test_fr_a3_bearer_scheme_is_case_insensitive(api: TestClient, migrated_db: Engine):
    _register(api)
    token = _token(api)

    response = api.get("/test/whoami", headers={"Authorization": f"bearer {token}"})

    assert response.json() == {"email": "alice@example.com"}


def test_fr_a2_tokens_are_deleted_with_their_user(api: TestClient, migrated_db: Engine, contract):
    _register(api)
    _register(api, email="bob@example.com", password=BOB_PASSWORD)
    alice = [_token(api), _token(api)]
    bob = _token(api, "bob@example.com", BOB_PASSWORD)

    with migrated_db.begin() as connection:
        connection.execute(delete(User).where(User.email == "alice@example.com"))

    assert [row.token_hash for row in _tokens(migrated_db)] == [hash_token(bob)]
    for token in alice:
        _assert_not_authenticated(_whoami(api, token), contract)
    assert _whoami(api, bob).status_code == 200


# --- Privacy -------------------------------------------------------------------------------


def test_fr_a2_passwords_and_tokens_never_appear_in_logs(
    api: TestClient, migrated_db: Engine, caplog
):
    caplog.set_level(logging.DEBUG)

    _register(api)
    _login(api, password="Wrong-Horse-8")
    _login(api, email="nobody@example.com", password="Unknown-Horse-9")
    first = _token(api)
    second = _token(api)
    _whoami(api, first)
    _logout(api, first)
    _logout(api, first)  # the not-authenticated path

    for secret in [PASSWORD, "Wrong-Horse-8", "Unknown-Horse-9", first, second]:
        assert secret not in caplog.text
