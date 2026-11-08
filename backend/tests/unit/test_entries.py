"""Entry input rules and the create route that need no database (issue #9).

Covers FR-E1, FR-E2, FR-E3 and FR-A3. Storage, tags and access by another user are tested
against PostgreSQL in tests/integration/test_entries.py.
"""

import typing
import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import entries
from app.auth import get_current_user
from app.entries import EntryInput
from app.main import create_app
from app.models import CATEGORIES, User
from app.text_rules import has_unstorable_characters, is_blank

OPENAPI = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "openapi.yaml").read_text(encoding="utf-8")
)
VALID = {"text": "Shipped it.", "date": "2026-11-08", "category": "Achievement"}


def _errors(payload: dict) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        EntryInput.model_validate(payload)
    return [
        (".".join(str(part) for part in item["loc"]), item["type"]) for item in error.value.errors()
    ]


@pytest.fixture
def logged_in_client(settings) -> TestClient:
    """The real create route with a stand-in user. Validation fails before any database use."""
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="a@b.c")
    return TestClient(app)


# --- Text rules ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", " ", "\t\n\v\f\r", " ", " ", "  ", "  ", " ", " ", "　", "﻿"])
def test_fr_e2_whitespace_follows_the_contract_pattern(text: str):
    """openapi.yaml uses `pattern: '\\S'`, whose whitespace is ECMAScript's `\\s`."""
    assert is_blank(text)


@pytest.mark.parametrize("text", ["a", " a ", "​", "\x1c", "\x85", "᠎", "."])
def test_fr_e2_other_characters_are_not_whitespace(text: str):
    assert not is_blank(text)


@pytest.mark.parametrize("text", ["\x00", "a\x00b", "\ud800", "a\udfffb", "\ude00\ud83d"])
def test_fr_e2_nul_and_unpaired_surrogates_cannot_be_stored(text: str):
    assert has_unstorable_characters(text)


@pytest.mark.parametrize("text", ["", "Plain", "Größe 日本語 🎉", "\x01\x1f\x7f", "￿"])
def test_fr_e2_other_text_can_be_stored(text: str):
    assert not has_unstorable_characters(text)


# --- Input model --------------------------------------------------------------------------


def test_fr_e1_text_is_kept_exactly_as_typed():
    text = "  Two wins:\n- one\n- two\n\n  "

    assert EntryInput.model_validate({**VALID, "text": text}).text == text


@pytest.mark.parametrize("text", ["", "   ", "\n\t", "　﻿"])
def test_fr_e2_entry_requires_text_that_is_not_only_whitespace(text: str):
    assert _errors({**VALID, "text": text}) == [("text", "text_missing")]


def test_fr_e2_entry_requires_text_date_and_category():
    assert _errors({}) == [("text", "missing"), ("date", "missing"), ("category", "missing")]


@pytest.mark.parametrize("value", ["missing", None, "", "  ", " "])
def test_fr_e2_result_impact_missing_empty_or_whitespace_becomes_null(value):
    payload = dict(VALID)
    if value != "missing":
        payload["result_impact"] = value

    assert EntryInput.model_validate(payload).result_impact is None


def test_fr_e2_result_impact_is_kept_as_typed():
    assert EntryInput.model_validate({**VALID, "result_impact": " 10% faster "}).result_impact == (
        " 10% faster "
    )


@pytest.mark.parametrize(
    "date",
    [
        "2026-02-30",
        "2026-11-8",
        "2026-11-08T00:00:00",
        "２０２６-11-08",
        "2026-11-08\n",
        1762560000,
    ],
)
def test_fr_e2_date_must_be_a_real_date_in_the_contract_format(date):
    [(field, _)] = _errors({**VALID, "date": date})

    assert field == "date"


def test_fr_e2_future_dates_are_accepted():
    assert str(EntryInput.model_validate({**VALID, "date": "2099-12-31"}).date) == "2099-12-31"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("text", "a\x00b"),
        ("text", "a\ud800"),
        ("result_impact", "\x00"),
        ("result_impact", "\udfff"),
    ],
)
def test_fr_e2_unstorable_characters_are_rejected_with_the_field_name(field: str, value: str):
    assert _errors({**VALID, field: value}) == [(field, "invalid_character")]


def test_fr_e3_tag_names_are_normalised_and_checked():
    assert EntryInput.model_validate({**VALID, "tags": [" machine  learning "]}).tags == [
        "machine learning"
    ]
    assert _errors({**VALID, "tags": ["Go", " "]}) == [("tags.1", "tag_name_empty")]
    assert _errors({**VALID, "tags": ["Go", "a\x00"]}) == [("tags.1", "invalid_character")]


def test_fr_a3_a_user_id_in_the_body_is_ignored():
    entry_input = EntryInput.model_validate({**VALID, "user_id": str(uuid.uuid4())})

    assert not hasattr(entry_input, "user_id")


def test_fr_e2_categories_match_the_contract_and_the_database_rule():
    assert typing.get_args(entries.Category) == CATEGORIES
    assert list(CATEGORIES) == OPENAPI["components"]["schemas"]["Category"]["enum"]


# --- Route --------------------------------------------------------------------------------


def test_fr_a3_create_uses_the_current_user_dependency():
    [route] = [r for r in entries.router.routes if r.name == "create_entry"]

    assert get_current_user in [dependency.call for dependency in route.dependant.dependencies]


def test_create_entry_matches_the_contract(settings):
    operation = create_app(settings).openapi()["paths"]["/entries"]["post"]

    assert operation["operationId"] == "createEntry"
    assert operation["security"] == [{"bearerAuth": []}]
    assert set(operation["responses"]) >= {"201", "422"}
    request = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request == {"$ref": "#/components/schemas/EntryInput"}
    response = operation["responses"]["201"]["content"]["application/json"]["schema"]
    assert response == {"$ref": "#/components/schemas/Entry"}


@pytest.mark.parametrize("body", [VALID, {}])
def test_fr_a3_create_without_token_is_not_authenticated(client: TestClient, contract, body):
    response = client.post("/entries", json=body)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_fr_e2_validation_error_names_each_field(logged_in_client: TestClient, contract):
    response = logged_in_client.post(
        "/entries",
        json={"text": " ", "date": "2026-02-30", "category": "Other", "tags": [""]},
    )

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    assert [item["field"] for item in body["fields"]] == ["text", "date", "category", "tags.0"]


def test_fr_e2_validation_error_never_echoes_the_text(logged_in_client: TestClient):
    response = logged_in_client.post(
        "/entries", json={"text": "Secret words\x00", "date": "2026-11-08", "category": "Learning"}
    )

    assert response.status_code == 422
    assert "Secret words" not in response.text
