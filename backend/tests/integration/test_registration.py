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
