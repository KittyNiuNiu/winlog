"""Listing, reading, editing and deleting saved summaries without a database (issue #18).

Operations `listSummaries`, `getSummary`, `updateSummary` and `deleteSummary` in openapi.yaml.
Covers FR-R5 and FR-A3: the contract, the edit body rules, the id format and authentication.
Storage, ordering, other users and entries are tested against PostgreSQL in
tests/integration/test_summary_management.py.
"""

import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import summaries
from app.auth import get_current_user
from app.main import create_app
from app.models import User
from app.summaries import SummaryUpdate

OPENAPI = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "openapi.yaml").read_text(encoding="utf-8")
)
SUMMARY_ID = "123e4567-e89b-12d3-a456-426614174000"
BY_ID = {"get": "get_summary", "patch": "update_summary", "delete": "delete_summary"}
WRONG_IDS = [
    "not-a-uuid",
    "123e4567e89b12d3a456426614174000",
    "{123e4567-e89b-12d3-a456-426614174000}",
    "urn:uuid:123e4567-e89b-12d3-a456-426614174000",
    "123e4567-e89b-12d3-a456-42661417400",
    "123e4567-e89b-12d3-a456-4266141740000",
    "123g4567-e89b-12d3-a456-426614174000",
    " 123e4567-e89b-12d3-a456-426614174000",
    "123e4567-e89b-12d3-a456-426614174000\n",
]


def _errors(payload: object) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        SummaryUpdate.model_validate(payload)
    return [
        (".".join(str(part) for part in item["loc"]), item["type"]) for item in error.value.errors()
    ]


def _send(client: TestClient, method: str, summary_id: str, body: object = None):
    path = f"/summaries/{quote(summary_id, safe='')}"
    if method == "patch":
        return client.patch(path, json={"text": "New text"} if body is None else body)
    return client.request(method.upper(), path)


@pytest.fixture
def logged_in_client(settings) -> TestClient:
    """The real routes with a stand-in user. Validation fails before any database use."""
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="a@b.c")
    return TestClient(app)


# --- Contract -----------------------------------------------------------------------------


def test_fr_r5_list_summaries_matches_the_contract(settings):
    generated = create_app(settings).openapi()
    operation = generated["paths"]["/summaries"]["get"]

    assert operation["operationId"] == OPENAPI["paths"]["/summaries"]["get"]["operationId"]
    assert operation["security"] == [{"bearerAuth": []}]
    assert "parameters" not in operation  # not paginated, no filter
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response == {"$ref": "#/components/schemas/SummaryList"}
    assert generated["components"]["schemas"]["SummaryList"]["required"] == ["summaries"]


def test_fr_r5_summary_operations_match_the_contract(settings):
    generated = create_app(settings).openapi()
    path = generated["paths"]["/summaries/{summaryId}"]
    contract_path = OPENAPI["paths"]["/summaries/{summaryId}"]

    assert set(path) == {"get", "patch", "delete"}
    for method, operation in path.items():
        assert operation["operationId"] == contract_path[method]["operationId"]
        assert operation["security"] == [{"bearerAuth": []}]
        [parameter] = operation["parameters"]
        assert (parameter["name"], parameter["in"], parameter["required"]) == (
            "summaryId",
            "path",
            True,
        )
        assert parameter["schema"]["format"] == "uuid"
        assert "422" in operation["responses"]
    for method in ("get", "patch"):
        assert path[method]["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/Summary"
        }
    assert path["patch"]["requestBody"]["required"] is True
    assert path["patch"]["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SummaryUpdate"
    }
    assert set(generated["components"]["schemas"]["SummaryUpdate"]["properties"]) == {"text"}
    assert generated["components"]["schemas"]["SummaryUpdate"]["required"] == ["text"]
    assert "204" in path["delete"]["responses"]
    assert "content" not in path["delete"]["responses"]["204"]


@pytest.mark.parametrize("name", ["list_summaries", *BY_ID.values()])
def test_fr_a3_summary_operations_use_the_current_user_dependency(name: str):
    [route] = [r for r in summaries.router.routes if r.name == name]

    assert get_current_user in [dependency.call for dependency in route.dependant.dependencies]


# --- Edit body ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["Edited.", "  Leading and trailing spaces  ", "Line one\n\nLine two\n", "x"]
)
def test_fr_r5_edited_text_is_kept_exactly_as_typed(text: str):
    assert SummaryUpdate.model_validate({"text": text}).text == text


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({}, "missing"),
        ({"text": None}, "string_type"),
        ({"text": 5}, "string_type"),
        ({"text": ["a"]}, "string_type"),
        ({"text": ""}, "text_missing"),
        ({"text": " \t\n\r "}, "text_missing"),
        ({"text": " 　﻿"}, "text_missing"),
        ({"text": "Has a NUL\x00"}, "invalid_character"),
        ({"text": "Lone surrogate \ud800"}, "invalid_character"),
    ],
)
def test_fr_r5_edit_needs_text_that_is_not_empty_or_only_whitespace(payload, error: str):
    assert _errors(payload) == [("text", error)]


def test_fr_r5_edit_ignores_every_field_but_the_text():
    body = SummaryUpdate.model_validate(
        {
            "text": "Edited.",
            "filter": {"period_start": "2020-01-01", "period_end": "2020-12-31"},
            "id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "created_at": "2000-01-01T00:00:00Z",
        }
    )

    assert body.model_dump() == {"text": "Edited."}


@pytest.mark.parametrize("body", [{}, {"text": "   "}, {"text": None}, ["text"], "text"])
def test_fr_r5_invalid_edit_is_a_validation_error_naming_the_field(
    logged_in_client: TestClient, contract, body
):
    response = _send(logged_in_client, "patch", SUMMARY_ID, body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    # A body that is not a JSON object fails as a whole, which the shared format names `body`.
    expected = ["text"] if isinstance(body, dict) else ["body"]
    assert [item["field"] for item in response.json()["fields"]] == expected


def test_privacy_edit_validation_error_never_echoes_the_text(logged_in_client: TestClient):
    response = _send(logged_in_client, "patch", SUMMARY_ID, {"text": "Secret summary\x00"})

    assert response.status_code == 422
    assert "Secret summary" not in response.text


# --- Id format and authentication ---------------------------------------------------------


@pytest.mark.parametrize("method", list(BY_ID))
@pytest.mark.parametrize("summary_id", WRONG_IDS)
def test_fr_a3_wrong_summary_id_format_is_a_validation_error_naming_summary_id(
    logged_in_client: TestClient, contract, method: str, summary_id: str
):
    response = _send(logged_in_client, method, summary_id)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert [item["field"] for item in response.json()["fields"]] == ["summaryId"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/summaries"),
        ("get", f"/summaries/{SUMMARY_ID}"),
        ("patch", f"/summaries/{SUMMARY_ID}"),
        ("delete", f"/summaries/{SUMMARY_ID}"),
        ("get", "/summaries/not-a-uuid"),
        ("patch", "/summaries/not-a-uuid"),
        ("delete", "/summaries/not-a-uuid"),
    ],
)
def test_fr_a3_summary_operations_without_token_are_not_authenticated(
    client: TestClient, contract, method: str, path: str
):
    kwargs = {"json": {"text": ""}} if method == "patch" else {}

    response = client.request(method.upper(), path, **kwargs)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
