"""Registration against the real test database (FR-A1)."""

import logging
import threading

import pytest
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select

from app.models import User

PASSWORD = "Correct-Horse-7"


def _register(client: TestClient, email: str = "alice@example.com", password: str = PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def _users(engine: Engine) -> list[User]:
    with engine.connect() as connection:
        return list(connection.execute(select(User.email, User.password_hash)).all())


def test_fr_a1_register_creates_account(client: TestClient, migrated_db: Engine, contract):
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    contract("User").validate(body)
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == "alice@example.com"
    assert [row.email for row in _users(migrated_db)] == ["alice@example.com"]


def test_fr_a1_response_never_contains_password_or_hash(client: TestClient, migrated_db: Engine):
    response = _register(client)

    stored_hash = _users(migrated_db)[0].password_hash
    assert PASSWORD not in response.text
    assert stored_hash not in response.text
    assert "password" not in response.text


def test_fr_a1_password_is_stored_only_as_an_argon2_hash(client: TestClient, migrated_db: Engine):
    _register(client)

    [row] = _users(migrated_db)
    assert row.password_hash.startswith("$argon2id$")
    assert PASSWORD not in row.password_hash
    assert PasswordHasher().verify(row.password_hash, PASSWORD)


def test_fr_a1_password_is_used_exactly_as_typed(client: TestClient, migrated_db: Engine):
    response = _register(client, password=" Abcdefg1x ")

    assert response.status_code == 201
    stored_hash = _users(migrated_db)[0].password_hash
    assert PasswordHasher().verify(stored_hash, " Abcdefg1x ")
    with pytest.raises(VerifyMismatchError):
        PasswordHasher().verify(stored_hash, "Abcdefg1x")


def test_fr_a1_password_of_exactly_10_characters_is_accepted(client: TestClient):
    assert _register(client, password="Abcdefg1!x").status_code == 201


def test_fr_a1_email_is_trimmed_and_stored_in_lower_case(client: TestClient, migrated_db: Engine):
    response = _register(client, email=" Alice@Example.com ")

    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"
    assert [row.email for row in _users(migrated_db)] == ["alice@example.com"]


@pytest.mark.parametrize("second", ["alice@example.com", "ALICE@EXAMPLE.COM", "Alice@example.com"])
def test_fr_a1_existing_email_in_any_case_is_rejected(
    client: TestClient, migrated_db: Engine, contract, second: str
):
    _register(client, email="alice@example.com")

    response = _register(client, email=second)

    assert response.status_code == 409
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "email_already_registered"
    assert len(_users(migrated_db)) == 1


def test_fr_a1_simultaneous_registrations_create_one_account(
    client: TestClient, migrated_db: Engine
):
    attempts = 5
    barrier = threading.Barrier(attempts)
    statuses: list[int] = []

    def register() -> None:
        barrier.wait()
        statuses.append(_register(client).status_code)

    threads = [threading.Thread(target=register) for _ in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(statuses) == [201] + [409] * (attempts - 1)
    assert len(_users(migrated_db)) == 1


def test_fr_a1_password_never_appears_in_logs(client: TestClient, caplog):
    caplog.set_level(logging.DEBUG)

    _register(client)
    _register(client)  # duplicate, the error path
    _register(client, password="no-uppercase-secret-1")  # validation error path

    assert PASSWORD not in caplog.text
    assert "no-uppercase-secret-1" not in caplog.text


@pytest.mark.parametrize(
    "password",
    [
        "Abcdefgh1²",  # superscript two
        "Abcdefgh1１",  # fullwidth digit one
        "Abcdefgh1٣",  # Arabic-Indic digit three
    ],
)
def test_fr_a1_digit_outside_0_to_9_counts_as_the_special_character(
    client: TestClient, migrated_db: Engine, password: str
):
    response = _register(client, password=password)

    assert response.status_code == 201
    [row] = _users(migrated_db)
    assert PasswordHasher().verify(row.password_hash, password)


def test_fr_a1_circled_capital_a_is_not_the_uppercase_letter(
    client: TestClient, migrated_db: Engine, contract
):
    response = _register(client, password="Ⓐbcdefgh12")

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["fields"] == [
        {"field": "password", "reason": "Password needs at least one uppercase letter."}
    ]
    assert _users(migrated_db) == []


def _register_raw(client: TestClient, raw: str):
    # httpx cannot encode a lone surrogate, so the JSON escape is sent exactly as written.
    return client.post(
        "/auth/register", content=raw.encode("ascii"), headers={"content-type": "application/json"}
    )


def test_fr_a1_unpaired_surrogate_in_password_returns_the_validation_error(
    client: TestClient, migrated_db: Engine, contract, caplog
):
    caplog.set_level(logging.DEBUG)

    response = _register_raw(
        client, '{"email": "e5@example.com", "password": "Surrogate-Secret-7\\ud800"}'
    )

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    assert [item["field"] for item in body["fields"]] == ["password"]
    assert "Surrogate-Secret-7" not in response.text
    assert "Surrogate-Secret-7" not in caplog.text
    assert _users(migrated_db) == []


def test_fr_a1_unpaired_surrogate_in_email_returns_the_validation_error(
    client: TestClient, migrated_db: Engine, contract
):
    response = _register_raw(client, '{"email": "e5\\ud800@example.com", "password": "Abcdefg1!x"}')

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert [item["field"] for item in body["fields"]] == ["email"]
    assert _users(migrated_db) == []


def test_fr_a1_escaped_surrogate_pair_is_one_valid_special_character(
    client: TestClient, migrated_db: Engine
):
    response = _register_raw(
        client, '{"email": "e6@example.com", "password": "Abcdefgh1\\ud83d\\ude00"}'
    )

    assert response.status_code == 201
    [row] = _users(migrated_db)
    assert PasswordHasher().verify(row.password_hash, "Abcdefgh1\U0001f600")
