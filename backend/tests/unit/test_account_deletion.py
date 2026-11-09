"""Account deletion without a database (issue #20).

Operation `deleteAccount` in openapi.yaml. Covers FR-D2: the contract, the validation error,
the password check and the order of the checks. The login and the database session are
replaced by fakes, so a test sees exactly what the operation does to the database. Deleting
the data, tokens, other users and logs are tested against PostgreSQL in
tests/integration/test_account_deletion.py.
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi.testclient import TestClient

from app import accounts
from app.ai import get_ai_provider
from app.ai.limits import get_limited_ai
from app.auth import CurrentLogin, get_current_login
from app.db import get_session
from app.main import create_app
from app.models import User
from app.passwords import hash_password

OPENAPI = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "openapi.yaml").read_text(encoding="utf-8")
)
PATH = "/account"
PASSWORD = "Correct-Horse-7"
# Hashed once, because argon2 is slow on purpose.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture
def session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), email="alice@example.com", password_hash=PASSWORD_HASH)


@pytest.fixture
def api(settings, session: MagicMock, user: User) -> TestClient:
    """The app with a logged-in user and a fake session that records every call."""
    app = create_app(settings)
    app.dependency_overrides[get_current_login] = lambda: CurrentLogin(
        token_id=uuid.uuid4(), user=user
    )
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def _delete(client: TestClient, headers: dict[str, str] | None = None, **kwargs):
    headers = {"Authorization": "Bearer t", **(headers or {})}
    return client.request("DELETE", PATH, headers=headers, **kwargs)


def _assert_nothing_deleted(session: MagicMock) -> None:
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def _calls(dependant) -> set:
    found = {dependant.call}
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


# --- Contract -----------------------------------------------------------------------------


def test_fr_d2_delete_account_operation_matches_the_contract(settings):
    generated = create_app(settings).openapi()
    operation = generated["paths"][PATH]["delete"]
    expected = OPENAPI["paths"][PATH]["delete"]

    assert operation["operationId"] == expected["operationId"] == "deleteAccount"
    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["requestBody"]["required"] is True
    body = operation["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/AccountDeletion"}
    assert {"204", "403", "422"} <= set(operation["responses"])
    assert {"204", "401", "403", "422"} <= set(expected["responses"])


def test_fr_d2_generated_request_schema_matches_the_contract(settings):
    generated = create_app(settings).openapi()["components"]["schemas"]["AccountDeletion"]
    expected = OPENAPI["components"]["schemas"]["AccountDeletion"]

    assert generated["required"] == expected["required"] == ["current_password"]
    assert set(generated["properties"]) == set(expected["properties"])
    assert generated["properties"]["current_password"]["type"] == "string"


def test_fr_d2_account_deletion_never_depends_on_the_ai():
    [route] = [route for route in accounts.router.routes if route.path == PATH]

    calls = _calls(route.dependant)
    assert get_ai_provider not in calls
    assert get_limited_ai not in calls
    assert get_current_login in calls


# --- Validation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"current_password": None},
        {"current_password": ""},
        {"current_password": 12345678901},
        {"current_password": ["Correct-Horse-7"]},
        {"password": PASSWORD},
        {"current_password": "A1!" + "a" * 126},  # 129 characters, more than any password
    ],
)
def test_fr_d2_missing_or_invalid_password_returns_the_validation_error(
    api: TestClient, session: MagicMock, contract, body: dict
):
    response = _delete(api, json=body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert [item["field"] for item in response.json()["fields"]] == ["current_password"]
    _assert_nothing_deleted(session)


def test_fr_d2_request_without_body_returns_the_validation_error(
    api: TestClient, session: MagicMock, contract
):
    response = _delete(api)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    _assert_nothing_deleted(session)


def test_fr_d2_password_with_unpaired_surrogate_returns_the_validation_error(
    api: TestClient, session: MagicMock, contract
):
    # httpx cannot encode a lone surrogate, so the JSON escape is sent exactly as written.
    raw = '{"current_password": "Surrogate-Secret-7\\ud800"}'
    response = _delete(
        api, content=raw.encode("ascii"), headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert "Surrogate-Secret-7" not in response.text
    _assert_nothing_deleted(session)


def test_fr_d2_rejected_password_is_never_echoed(api: TestClient):
    response = _delete(api, json={"current_password": "Secret-" + "x" * 130})

    assert response.status_code == 422
    assert "Secret-" not in response.text


# --- Password check -----------------------------------------------------------------------


@pytest.mark.parametrize("password", ["Correct-Horse-8", "correct-horse-7", PASSWORD + " "])
def test_fr_d2_wrong_password_returns_the_wrong_password_error_and_deletes_nothing(
    api: TestClient, session: MagicMock, contract, password: str
):
    response = _delete(api, json={"current_password": password})

    assert response.status_code == 403
    contract("Error").validate(response.json())
    assert response.json() == {"code": "wrong_password", "message": "That password is incorrect."}
    _assert_nothing_deleted(session)


def test_fr_d2_correct_password_deletes_the_user_in_one_commit(
    api: TestClient, session: MagicMock, user: User
):
    response = _delete(api, json={"current_password": PASSWORD})

    assert response.status_code == 204
    assert response.content == b""
    # One DELETE of the user; the database cascades it to all of the user's data.
    [call] = session.execute.call_args_list
    statement = call.args[0]
    assert statement.is_delete
    assert statement.table.name == "users"
    assert statement.compile().params == {"id_1": user.id}
    session.commit.assert_called_once()


def test_fr_d2_password_is_checked_the_same_way_as_at_login(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, user: User
):
    checked = []

    def verify(password_hash: str, password: str) -> bool:
        checked.append((password_hash, password))
        return False

    monkeypatch.setattr(accounts, "verify_password", verify)

    assert _delete(api, json={"current_password": PASSWORD}).status_code == 403
    assert checked == [(user.password_hash, PASSWORD)]


# --- Errors -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {"current_password": PASSWORD}},
        {},
        {"content": b'{"current_password": ', "headers": {"content-type": "application/json"}},
    ],
)
def test_fr_d2_request_without_token_returns_not_authenticated(
    settings, session: MagicMock, contract, kwargs: dict
):
    # The real login check, with a fake session that finds no token.
    session.execute.return_value.one_or_none.return_value = None
    app = create_app(settings)
    app.dependency_overrides[get_session] = lambda: session

    response = TestClient(app).request("DELETE", PATH, **kwargs)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    session.commit.assert_not_called()
