"""The suggestions route without a database (issue #16, `suggestCategoryAndTags`).

Covers FR-S1, FR-S3 and the §7.3 error handling. The limited entry point is replaced by a
stand-in, so these tests make no AI call and need no PostgreSQL. Tag matching, the limits and
"nothing is saved" are tested against PostgreSQL in tests/integration/test_suggestions.py.
"""

import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import suggestions
from app.ai import (
    AIError,
    AILimitReachedError,
    AIProviderError,
    AITimeoutError,
    Suggestion,
    get_limited_ai,
)
from app.ai.limits import LIMIT_MESSAGES
from app.auth import get_current_user
from app.errors import ApiError
from app.main import create_app
from app.models import User
from app.suggestions import MAX_SUGGESTED_TAGS, SuggestionRequest, suggested_tag_names
from tests.conftest import OPENAPI_PATH

TEXT = "Ran the quarterly planning workshop."
AI_UNAVAILABLE = {"code": "ai_unavailable", "message": "The AI is not available right now."}


class FakeLimitedAI:
    """Stands in for `LimitedAI`: records the calls and answers or raises as configured."""

    def __init__(self, answer: Suggestion | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[uuid.UUID, str]] = []

    def suggest(self, user_id: uuid.UUID, text: str) -> Suggestion:
        self.calls.append((user_id, text))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), email="a@b.c")


def _client(settings, user: User, ai: FakeLimitedAI) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_limited_ai] = lambda: ai
    return TestClient(app)


# --- Contract -----------------------------------------------------------------------------


def test_fr_s1_suggestion_operation_matches_the_contract(settings):
    generated = create_app(settings).openapi()
    operation = generated["paths"]["/suggestions"]["post"]

    assert set(generated["paths"]["/suggestions"]) == {"post"}
    assert operation["operationId"] == "suggestCategoryAndTags"
    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["requestBody"]["required"] is True
    request = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request == {"$ref": "#/components/schemas/SuggestionRequest"}
    response = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response == {"$ref": "#/components/schemas/Suggestion"}
    schemas = generated["components"]["schemas"]
    assert schemas["SuggestionRequest"]["required"] == ["text"]
    assert schemas["Suggestion"]["required"] == ["category", "tags"]
    assert schemas["Suggestion"]["properties"]["tags"]["maxItems"] == MAX_SUGGESTED_TAGS


def test_fr_s3_tag_cap_is_the_contracts():
    contract = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    tags = contract["components"]["schemas"]["Suggestion"]["properties"]["tags"]

    assert MAX_SUGGESTED_TAGS == tags["maxItems"] == 5


@pytest.mark.parametrize("text", ["", " ", "\t\n", "　"])
def test_fr_s1_request_rejects_blank_text(text: str):
    with pytest.raises(ValueError):
        SuggestionRequest.model_validate({"text": text})


def test_fr_s1_request_keeps_the_text_exactly_as_typed():
    assert SuggestionRequest.model_validate({"text": f"  {TEXT}\n"}).text == f"  {TEXT}\n"


# --- Route --------------------------------------------------------------------------------


def test_fr_s1_suggestion_sends_only_the_users_id_and_text_to_the_limited_entry_point(
    settings, user, contract
):
    ai = FakeLimitedAI(Suggestion(category="Learning", tags=[]))

    response = _client(settings, user, ai).post(
        "/suggestions", json={"text": TEXT, "category": "Achievement", "tags": ["Ignored"]}
    )

    assert response.status_code == 200
    contract("Suggestion").validate(response.json())
    assert response.json() == {"category": "Learning", "tags": []}
    assert ai.calls == [(user.id, TEXT)]


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": " \n "}, {"text": None}])
def test_fr_s1_invalid_text_makes_no_ai_call(settings, user, contract, body):
    ai = FakeLimitedAI(Suggestion(category="Learning", tags=[]))

    response = _client(settings, user, ai).post("/suggestions", json=body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["fields"][0]["field"] == "text"
    assert ai.calls == []


@pytest.mark.parametrize(
    "error", [AITimeoutError("timed out"), AIProviderError("failed"), AIError("other")]
)
def test_fr_s1_ai_failure_returns_ai_unavailable(settings, user, contract, error):
    response = _client(settings, user, FakeLimitedAI(error)).post(
        "/suggestions", json={"text": TEXT}
    )

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE


@pytest.mark.parametrize("limit", ["user_suggestions", "global"])
def test_fr_s1_reached_limit_returns_limit_reached(settings, user, contract, limit):
    response = _client(settings, user, FakeLimitedAI(AILimitReachedError(limit))).post(
        "/suggestions", json={"text": TEXT}
    )

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "limit_reached",
        "message": LIMIT_MESSAGES[limit],
        "limit": limit,
    }


def test_privacy_ai_unavailable_error_does_not_carry_the_provider_error(settings, user):
    """The provider's exception may repeat the entry text, so no traceback may include it."""
    try:
        raise AIProviderError("The AI provider failed.") from RuntimeError(f"bad input: {TEXT}")
    except AIProviderError as provider_error:
        ai = FakeLimitedAI(provider_error)

    with Session() as session, pytest.raises(ApiError) as raised:
        suggestions.suggest_category_and_tags(
            SuggestionRequest(text=TEXT),
            user,
            ai,
            session,  # type: ignore[arg-type]
        )

    assert raised.value.code == "ai_unavailable"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert TEXT not in str(raised.value)


def test_fr_s3_no_suggested_tags_needs_no_lookup(user):
    """Without names, nothing is looked up, so no database is needed."""
    with Session() as session:
        assert suggested_tag_names(session, user, []) == []
        assert suggested_tag_names(session, user, ["", "   "]) == []
