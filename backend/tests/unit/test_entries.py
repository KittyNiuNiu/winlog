"""Entry input rules and the create route that need no database (issue #9).

Covers FR-E1, FR-E2, FR-E3 and FR-A3. Storage, tags and access by another user are tested
against PostgreSQL in tests/integration/test_entries.py.
"""

import typing
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from app import entries
from app.auth import get_current_user
from app.entries import EntryInput
from app.main import create_app
from app.models import CATEGORIES, User
from app.tags import FilterTagName
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


# --- Get, update and delete (issue #10) ---------------------------------------------------

ENTRY_ID = "123e4567-e89b-12d3-a456-426614174000"
BY_ID = {"get": "get_entry", "put": "update_entry", "delete": "delete_entry"}
WRONG_IDS = [
    "not-a-uuid",
    "123e4567e89b12d3a456426614174000",
    "{123e4567-e89b-12d3-a456-426614174000}",
    "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
    "123e4567-e89b-12d3-a456-42661417400",
    "123e4567-e89b-12d3-a456-4266141740000",
    "123e4567-e89b12d3-a456-426614174000",
    "123g4567-e89b-12d3-a456-426614174000",
    " 123e4567-e89b-12d3-a456-426614174000",
    "123e4567-e89b-12d3-a456-426614174000\n",
]


def _send(client: TestClient, method: str, entry_id: str):
    path = f"/entries/{quote(entry_id, safe='')}"
    if method == "put":
        return client.put(path, json=VALID)
    return client.request(method.upper(), path)


@pytest.mark.parametrize("value", [ENTRY_ID, ENTRY_ID.upper()])
def test_fr_a3_entry_id_in_the_contract_format_is_accepted(value: str):
    assert entries._require_uuid(value) == value


@pytest.mark.parametrize("value", [*WRONG_IDS, 5, None, uuid.UUID(ENTRY_ID)])
def test_fr_a3_entry_id_in_any_other_format_is_rejected(value):
    with pytest.raises(Exception, match="Must be a UUID"):
        entries._require_uuid(value)


@pytest.mark.parametrize("method", list(BY_ID))
@pytest.mark.parametrize("entry_id", WRONG_IDS)
def test_fr_a3_wrong_id_format_is_a_validation_error_naming_entry_id(
    logged_in_client: TestClient, contract, method: str, entry_id: str
):
    response = _send(logged_in_client, method, entry_id)

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    assert [item["field"] for item in body["fields"]] == ["entryId"]


def test_fr_e4_update_validates_like_create(logged_in_client: TestClient, contract):
    response = logged_in_client.put(
        f"/entries/{ENTRY_ID}",
        json={"text": " ", "date": "2026-02-30", "category": "Other", "tags": [""]},
    )

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert [item["field"] for item in response.json()["fields"]] == [
        "text",
        "date",
        "category",
        "tags.0",
    ]


def test_fr_e4_update_validation_error_never_echoes_the_text(logged_in_client: TestClient):
    response = logged_in_client.put(
        f"/entries/{ENTRY_ID}",
        json={"text": "Secret words\x00", "date": "2026-11-08", "category": "Learning"},
    )

    assert response.status_code == 422
    assert "Secret words" not in response.text


@pytest.mark.parametrize("name", list(BY_ID.values()))
def test_fr_a3_get_update_and_delete_use_the_current_user_dependency(name: str):
    [route] = [r for r in entries.router.routes if r.name == name]

    assert get_current_user in [dependency.call for dependency in route.dependant.dependencies]


def test_entry_operations_match_the_contract(settings):
    generated = create_app(settings).openapi()["paths"]["/entries/{entryId}"]
    contract_path = OPENAPI["paths"]["/entries/{entryId}"]

    assert set(generated) == {"get", "put", "delete"}
    for method, operation in generated.items():
        assert operation["operationId"] == contract_path[method]["operationId"]
        assert operation["security"] == [{"bearerAuth": []}]
        [parameter] = operation["parameters"]
        assert (parameter["name"], parameter["in"], parameter["required"]) == (
            "entryId",
            "path",
            True,
        )
        assert parameter["schema"]["format"] == "uuid"
        assert "422" in operation["responses"]
    entry_schema = {"$ref": "#/components/schemas/Entry"}
    for method in ("get", "put"):
        assert generated[method]["responses"]["200"]["content"]["application/json"]["schema"] == (
            entry_schema
        )
    assert generated["put"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EntryInput"
    }
    assert "204" in generated["delete"]["responses"]
    assert "content" not in generated["delete"]["responses"]["204"]


@pytest.mark.parametrize("method", list(BY_ID))
@pytest.mark.parametrize("entry_id", [ENTRY_ID, "not-a-uuid"])
def test_fr_a3_get_update_and_delete_without_token_are_not_authenticated(
    client: TestClient, contract, method: str, entry_id: str
):
    response = _send(client, method, entry_id)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


# --- List and filter (issue #11) ----------------------------------------------------------


def test_list_entries_matches_the_contract(settings):
    generated = create_app(settings).openapi()["paths"]["/entries"]["get"]
    contract_operation = OPENAPI["paths"]["/entries"]["get"]

    assert generated["operationId"] == contract_operation["operationId"] == "listEntries"
    assert generated["security"] == [{"bearerAuth": []}]
    assert set(generated["responses"]) >= {"200", "422"}
    response = generated["responses"]["200"]["content"]["application/json"]["schema"]
    assert response == {"$ref": "#/components/schemas/EntryList"}
    parameters = {p["name"]: p for p in generated["parameters"]}
    assert [p["name"] for p in generated["parameters"]] == [
        p["name"] for p in contract_operation["parameters"]
    ]
    for parameter in contract_operation["parameters"]:
        assert parameters[parameter["name"]]["in"] == "query"
        assert parameters[parameter["name"]]["required"] is False
    [start_date, _] = parameters["start_date"]["schema"]["anyOf"]
    assert start_date == {"type": "string", "format": "date"}
    [category, _] = parameters["category"]["schema"]["anyOf"]
    assert category["type"] == "array"
    assert category["items"]["enum"] == list(CATEGORIES)
    [tag, _] = parameters["tag"]["schema"]["anyOf"]
    assert tag == {"type": "array", "items": {"type": "string"}}


def test_fr_a3_list_uses_the_current_user_dependency():
    [route] = [r for r in entries.router.routes if r.name == "list_entries"]

    assert get_current_user in [dependency.call for dependency in route.dependant.dependencies]


@pytest.mark.parametrize(
    "query",
    ["", "?start_date=2026-02-30&end_date=2026-01-01&category=Other&tag=%00", "?tag=a&tag=b"],
)
def test_fr_a3_list_without_token_is_not_authenticated(client: TestClient, contract, query: str):
    response = client.get(f"/entries{query}")

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def _list_error_fields(client: TestClient, contract, query: str) -> list[str]:
    response = client.get(f"/entries{query}")
    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    return [item["field"] for item in body["fields"]]


@pytest.mark.parametrize(
    ("start", "end"), [("2026-01-02", "2026-01-01"), ("2027-01-01", "2026-12-31")]
)
def test_fr_r1_start_date_after_end_date_names_the_end_date(
    logged_in_client: TestClient, contract, start: str, end: str
):
    fields = _list_error_fields(logged_in_client, contract, f"?start_date={start}&end_date={end}")

    assert fields == ["end_date"]


@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30",
        "2026-11-8",
        "2026-11-08T00:00:00",
        quote("２０２６-11-08"),
        "2026-11-08%0A",
        "1762560000",
        "",
        "yesterday",
    ],
)
def test_fr_r1_date_must_be_a_real_date_in_the_contract_format(
    logged_in_client: TestClient, contract, field: str, value: str
):
    assert _list_error_fields(logged_in_client, contract, f"?{field}={value}") == [field]


@pytest.mark.parametrize(
    "value", ["Other", "learning", "", "Side%2Bproject", "Achievement,Learning"]
)
def test_fr_r1_category_must_be_one_of_the_four(logged_in_client: TestClient, contract, value):
    fields = _list_error_fields(logged_in_client, contract, f"?category=Learning&category={value}")

    assert fields == ["category.1"]


def test_fr_r1_tag_name_with_nul_is_a_validation_error_that_does_not_echo_it(
    logged_in_client: TestClient, contract
):
    response = logged_in_client.get("/entries?tag=Go&tag=Secret%00name")

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert [item["field"] for item in response.json()["fields"]] == ["tag.1"]
    assert "Secret" not in response.text


def test_fr_r1_every_invalid_parameter_is_named(logged_in_client: TestClient, contract):
    fields = _list_error_fields(
        logged_in_client, contract, "?start_date=2026-02-30&end_date=x&category=Other&tag=%00"
    )

    assert fields == ["start_date", "end_date", "category.0", "tag.0"]


@pytest.mark.parametrize("value", ["\x00", "a\x00b", "\ud800", "a\udfffb"])
def test_fr_r1_filter_tag_name_rejects_characters_the_database_cannot_take(value: str):
    with pytest.raises(ValidationError) as error:
        TypeAdapter(FilterTagName).validate_python(value)

    assert [item["type"] for item in error.value.errors()] == ["invalid_character"]


@pytest.mark.parametrize("value", ["", "   ", "Python", " machine  learning ", "Sales, EMEA"])
def test_fr_r1_filter_tag_name_accepts_any_other_name_unchanged(value: str):
    """Unknown or empty names are not an error: they match nothing (#11)."""
    assert TypeAdapter(FilterTagName).validate_python(value) == value


def test_fr_r1_entry_filter_defaults_to_no_restriction():
    assert entries.EntryFilter() == entries.EntryFilter(
        start_date=None, end_date=None, categories=(), tags=()
    )
