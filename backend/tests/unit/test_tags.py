"""Tag name rules that need no database (issue #8, FR-E3)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app import tags
from app.auth import get_current_user
from app.main import create_app
from app.tags import TagName, normalise_tag_name


class _TaggedInput(BaseModel):
    """Stands in for the entry input of #9 and #10, which will use `list[TagName]`."""

    tags: list[TagName] = []


def _client_with_tag_route(settings) -> TestClient:
    app = create_app(settings)

    @app.post("/test-only/tags")
    def tag_route(payload: _TaggedInput) -> dict:
        return {"tags": payload.tags}

    return TestClient(app)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("  machine   learning ", "machine learning"),
        ("Python", "Python"),
        ("\tdata \n science  ", "data science"),
        ("a  b   c", "a b c"),
    ],
)
def test_fr_e3_tag_name_is_trimmed_and_inner_spaces_become_one(given: str, expected: str):
    assert normalise_tag_name(given) == expected


def test_fr_e3_tag_name_keeps_its_case():
    assert normalise_tag_name(" GraphQL ") == "GraphQL"


def test_fr_e3_request_tag_names_are_normalised(settings):
    client = _client_with_tag_route(settings)

    response = client.post("/test-only/tags", json={"tags": ["  machine   learning ", "Go"]})

    assert response.status_code == 200
    assert response.json() == {"tags": ["machine learning", "Go"]}


@pytest.mark.parametrize("empty", ["", " ", "   ", "\t\n", " "])
def test_fr_e3_tag_name_empty_after_trimming_is_a_validation_error_naming_the_field(
    settings, contract, empty: str
):
    client = _client_with_tag_route(settings)

    response = client.post("/test-only/tags", json={"tags": ["Python", empty]})

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    assert body["fields"] == [{"field": "tags.1", "reason": "Tag name must not be empty."}]


def test_fr_a3_tag_list_uses_the_current_user_dependency():
    [route] = [r for r in tags.router.routes if r.name == "list_tags"]

    assert get_current_user in [dependency.call for dependency in route.dependant.dependencies]


def test_fr_a3_tag_list_without_token_is_not_authenticated(client: TestClient, contract):
    response = client.get("/tags")

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_tag_list_matches_the_contract(settings):
    operation = create_app(settings).openapi()["paths"]["/tags"]["get"]

    assert operation["operationId"] == "listTags"
    assert operation["security"] == [{"bearerAuth": []}]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/TagList"}


@pytest.mark.parametrize("character", ["\\u0000", "\\ud800", "\\udfff"])
def test_fr_e3_tag_name_with_a_character_the_database_cannot_store_is_a_validation_error(
    settings, contract, character: str
):
    """NUL cannot be stored in PostgreSQL text and a lone surrogate has no UTF-8 form."""
    client = _client_with_tag_route(settings)
    raw = f'{{"tags": ["Python", "Go{character}"]}}'

    response = client.post(
        "/test-only/tags", content=raw.encode("ascii"), headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["fields"] == [
        {
            "field": "tags.1",
            "reason": "Contains a character that cannot be stored (NUL or an unpaired surrogate).",
        }
    ]
