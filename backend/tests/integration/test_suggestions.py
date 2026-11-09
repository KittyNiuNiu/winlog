"""AI suggestions through the API (issue #16, `suggestCategoryAndTags` in openapi.yaml).

Covers FR-S1, FR-S2, FR-S3 and FR-A3, and the acceptance criteria in product-spec.md §7.3 and
§8, against real PostgreSQL. Every AI call goes to the mock provider.
"""

import datetime as dt
import logging
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select

from app.ai import AIProvider, MockProvider, Suggestion, SummaryEntry, get_ai_provider
from app.ai.limits import LIMIT_MESSAGES
from app.auth import hash_token
from app.main import create_app
from app.models import AiUsage, AiUsageGlobal, Entry, EntryTag, Tag, Token, User
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

TEXT = "Shipped the release and wrote the runbook."
AI_UNAVAILABLE = {"code": "ai_unavailable", "message": "The AI is not available right now."}


# --- Helpers ------------------------------------------------------------------------------


def _user(engine: Engine) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(User)
            .values(email=f"user-{uuid.uuid4()}@example.com", password_hash="hash")
            .returning(User.id)
        ).scalar_one()


def _token(engine: Engine, user_id: uuid.UUID) -> str:
    """A login for the user, without going through the password check."""
    token = f"test-token-{uuid.uuid4()}"
    with engine.begin() as connection:
        connection.execute(
            insert(Token).values(
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
            )
        )
    return token


def _tag(engine: Engine, user_id: uuid.UUID, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(insert(Tag).values(user_id=user_id, name=name))


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _counts(engine: Engine) -> dict[str, int]:
    """The number of rows in each table a suggestion could change."""
    tables = {
        "users": User,
        "tokens": Token,
        "entries": Entry,
        "tags": Tag,
        "entry_tags": EntryTag,
        "ai_usage": AiUsage,
        "ai_usage_global": AiUsageGlobal,
    }
    with engine.connect() as connection:
        return {
            name: connection.execute(select(func.count()).select_from(model)).scalar_one()
            for name, model in tables.items()
        }


def _usage(engine: Engine, user_id: uuid.UUID) -> tuple[int, int]:
    """The user's suggestion count and the global count, over all days."""
    with engine.connect() as connection:
        user = connection.execute(
            select(func.coalesce(func.sum(AiUsage.request_count), 0)).where(
                AiUsage.user_id == user_id, AiUsage.request_type == "suggestion"
            )
        ).scalar_one()
        everyone = connection.execute(
            select(func.coalesce(func.sum(AiUsageGlobal.request_count), 0))
        ).scalar_one()
    return user, everyone


def _app(test_database_url: str, **settings: int) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                database_url=test_database_url,
                cors_allowed_origins=[ALLOWED_ORIGIN],
                ai_provider="mock",
                **settings,
            )
        )
    )


@pytest.fixture
def make_client(test_database_url: str, migrated_db: Engine) -> Callable[..., TestClient]:
    """Build the app with the given settings, connected to the migrated test database."""
    return lambda **settings: _app(test_database_url, **settings)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def _mock(client: TestClient) -> MockProvider:
    provider = client.app.state.ai_provider
    assert isinstance(provider, MockProvider)
    return provider


@pytest.fixture
def user(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db)


@pytest.fixture
def token(migrated_db: Engine, user: uuid.UUID) -> str:
    return _token(migrated_db, user)


def _suggest(client: TestClient, token: str | None, body: object = None):
    headers = _auth(token) if token else {}
    return client.post(
        "/suggestions", json={"text": TEXT} if body is None else body, headers=headers
    )


def _suggest_tags(client: TestClient, token: str, tags: list[str]) -> list[str]:
    """The tags the endpoint returns when the AI suggests these tags."""
    _mock(client).return_suggestion(Suggestion(category="Learning", tags=tags))
    response = _suggest(client, token)
    assert response.status_code == 200, response.json()
    return response.json()["tags"]


# --- Success ------------------------------------------------------------------------------


def test_fr_s1_suggestion_returns_one_category_and_tags(client, token, contract):
    _mock(client).return_suggestion(Suggestion(category="Achievement", tags=["Release"]))

    response = _suggest(client, token)

    assert response.status_code == 200
    contract("Suggestion").validate(response.json())
    assert response.json() == {"category": "Achievement", "tags": ["Release"]}


def test_fr_s1_default_mock_suggestion_follows_the_contract(client, token, contract):
    response = _suggest(client, token)

    assert response.status_code == 200
    contract("Suggestion").validate(response.json())
    assert response.json()["category"] in {"Achievement", "Learning", "Feedback", "Side project"}
    assert response.json()["tags"] == ["Mock tag"]


def test_fr_s1_only_the_entry_text_is_sent_to_the_ai(client, migrated_db, user, token):
    """§8: the AI receives the text exactly as typed, and nothing else (not the user's tags)."""
    _tag(migrated_db, user, "Secret project")
    text = "  Led the incident review.\nResult: fewer pages.  "

    response = _suggest(client, token, {"text": text, "user_id": str(uuid.uuid4())})

    assert response.status_code == 200
    mock = _mock(client)
    assert mock.suggest_calls == [text]
    assert mock.summarise_calls == []


def test_fr_s1_suggestions_go_through_the_daily_limits(client, migrated_db, user, token):
    """The call goes through #15's limited entry point, so it is counted for the user."""
    assert _usage(migrated_db, user) == (0, 0)

    assert _suggest(client, token).status_code == 200
    assert _suggest(client, token).status_code == 200

    assert _usage(migrated_db, user) == (2, 2)


# --- Tag names ----------------------------------------------------------------------------


def test_fr_s3_tag_matching_an_existing_tag_in_another_case_uses_its_spelling(
    client, migrated_db, user, token
):
    _tag(migrated_db, user, "PostgreSQL")
    _tag(migrated_db, user, "Team Lead")

    tags = _suggest_tags(client, token, ["postgresql", "TEAM LEAD", "Mentoring"])

    assert tags == ["PostgreSQL", "Team Lead", "Mentoring"]


def test_fr_s3_unused_existing_tag_is_matched_too(client, migrated_db, user, token):
    """A tag no entry uses any more is still the user's tag (#8), so its spelling is used."""
    _tag(migrated_db, user, "iOS")

    assert _suggest_tags(client, token, ["IOS"]) == ["iOS"]


def test_fr_s3_tag_names_are_cleaned_with_the_tag_rules(client, migrated_db, user, token):
    _tag(migrated_db, user, "Release notes")

    tags = _suggest_tags(client, token, ["  release \t  NOTES ", " Code   review "])

    assert tags == ["Release notes", "Code review"]


def test_fr_a3_another_users_tag_is_not_used_for_matching(client, migrated_db, token):
    other = _user(migrated_db)
    _tag(migrated_db, other, "KUBERNETES")

    assert _suggest_tags(client, token, ["Kubernetes"]) == ["Kubernetes"]


def test_fr_a3_matching_uses_only_the_users_own_tag_when_both_have_one(
    client, migrated_db, user, token
):
    _tag(migrated_db, _user(migrated_db), "PYTHON")
    _tag(migrated_db, user, "Python")

    assert _suggest_tags(client, token, ["python"]) == ["Python"]


def test_fr_s3_duplicate_tags_are_returned_once(client, migrated_db, user, token):
    _tag(migrated_db, user, "Go")

    tags = _suggest_tags(client, token, ["Rust", "rust", " RUST ", "go", "GO", "Go"])

    assert tags == ["Rust", "Go"]


def test_fr_s3_at_most_five_tags_are_returned(client, token, contract):
    tags = _suggest_tags(client, token, ["A", "B", "C", "D", "E", "F", "G", "H"])

    assert tags == ["A", "B", "C", "D", "E"]
    contract("Suggestion").validate({"category": "Learning", "tags": tags})


def test_fr_s3_duplicates_are_removed_before_the_five_tag_cap(client, migrated_db, user, token):
    _tag(migrated_db, user, "Bb")

    tags = _suggest_tags(client, token, ["A", "a", "BB", "b b", "C", "c", "D", "E", "F"])

    assert tags == ["A", "Bb", "b b", "C", "D"]


def test_fr_s3_a_suggestion_may_have_no_tags(client, token, contract):
    _mock(client).return_suggestion(Suggestion(category="Feedback", tags=[]))

    response = _suggest(client, token)

    assert response.status_code == 200
    contract("Suggestion").validate(response.json())
    assert response.json() == {"category": "Feedback", "tags": []}


# --- Nothing is saved ---------------------------------------------------------------------


def test_fr_s2_suggestions_save_nothing(client, migrated_db, user, token):
    _tag(migrated_db, user, "Existing")
    before = _counts(migrated_db)

    tags = _suggest_tags(client, token, ["existing", "Brand new tag", "Another new one"])

    assert tags == ["Existing", "Brand new tag", "Another new one"]
    after = _counts(migrated_db)
    # Only #15's usage counts change: the user's count row and the global count row.
    assert after == {**before, "ai_usage": before["ai_usage"] + 1, "ai_usage_global": 1}
    with migrated_db.connect() as connection:
        assert connection.execute(select(Tag.name)).scalars().all() == ["Existing"]


@pytest.mark.parametrize("failure", ["raise_timeout", "raise_provider_error"])
def test_fr_s2_a_failed_suggestion_saves_nothing(client, migrated_db, token, failure):
    before = _counts(migrated_db)
    getattr(_mock(client), failure)()

    assert _suggest(client, token).status_code == 503

    after = _counts(migrated_db)
    # The failed call has still been counted (#15); nothing else changed.
    assert after == {**before, "ai_usage": before["ai_usage"] + 1, "ai_usage_global": 1}


# --- Errors -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": None},
        {"text": ""},
        {"text": "   "},
        {"text": "\t\n  　"},
        {"text": 42},
        {"text": "a\x00b"},
    ],
)
def test_fr_s1_missing_blank_or_invalid_text_is_a_validation_error_and_not_counted(
    client, migrated_db, user, token, contract, body
):
    response = _suggest(client, token, body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert [field["field"] for field in response.json()["fields"]] == ["text"]
    assert _mock(client).suggest_calls == []
    assert _usage(migrated_db, user) == (0, 0)


def test_fr_s1_body_that_is_not_an_object_is_a_validation_error(client, migrated_db, token):
    for body in (["text"], "text"):
        response = _suggest(client, token, body)
        assert response.status_code == 422
        assert response.json()["code"] == "validation_failed"
    assert _mock(client).suggest_calls == []
    assert _counts(migrated_db)["ai_usage_global"] == 0


def test_fr_s1_reached_user_limit_returns_limit_reached(make_client, migrated_db, contract):
    client = make_client(ai_daily_suggestions_per_user=1)
    user = _user(migrated_db)
    token = _token(migrated_db, user)
    assert _suggest(client, token).status_code == 200

    response = _suggest(client, token)

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "limit_reached",
        "message": LIMIT_MESSAGES["user_suggestions"],
        "limit": "user_suggestions",
    }
    # The limit is checked before the AI is called, and a refused request is not counted.
    assert len(_mock(client).suggest_calls) == 1
    assert _usage(migrated_db, user) == (1, 1)


def test_fr_s1_reached_global_cap_returns_limit_reached(make_client, migrated_db, contract):
    client = make_client(ai_daily_requests_global=1)
    assert _suggest(client, _token(migrated_db, _user(migrated_db))).status_code == 200

    response = _suggest(client, _token(migrated_db, _user(migrated_db)))

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json()["code"] == "limit_reached"
    assert response.json()["limit"] == "global"
    assert len(_mock(client).suggest_calls) == 1


def test_fr_s1_ai_timeout_returns_ai_unavailable(client, token, contract):
    _mock(client).raise_timeout()

    response = _suggest(client, token)

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE


def test_fr_s1_ai_provider_failure_returns_ai_unavailable(client, token, contract):
    _mock(client).raise_provider_error()

    response = _suggest(client, token)

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE


def test_fr_s1_unusable_ai_output_returns_ai_unavailable(client, token):
    """The adapter turns output that breaks its rules into a provider failure (#12)."""
    _mock(client).return_suggestion(Suggestion(category="Hobby", tags=["Release"]))  # type: ignore[arg-type]

    response = _suggest(client, token)

    assert response.status_code == 503
    assert response.json() == AI_UNAVAILABLE


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}])
def test_fr_a3_suggestion_without_valid_token_is_not_authenticated(
    client, migrated_db, headers, contract
):
    response = client.post("/suggestions", json={"text": TEXT}, headers=headers)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _mock(client).suggest_calls == []
    assert _counts(migrated_db)["ai_usage_global"] == 0


def test_fr_a3_invalid_body_without_token_is_not_authenticated(client, migrated_db):
    response = client.post(
        "/suggestions", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert _mock(client).suggest_calls == []


# --- Privacy ------------------------------------------------------------------------------


class _LeakyProvider(AIProvider):
    """A provider whose failure message repeats the entry text, as a real one might."""

    name = "leaky"

    def _suggest(self, text: str) -> Suggestion:
        raise RuntimeError(f"The provider could not handle: {text}")

    def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
        raise NotImplementedError


def _all_logged_text(caplog: pytest.LogCaptureFixture) -> str:
    """Every logged message, with any traceback and its causes."""
    formatter = logging.Formatter()
    return "\n".join(formatter.format(record) for record in caplog.records)


def test_privacy_entry_text_and_suggested_tags_are_never_logged(client, token, caplog):
    _mock(client).return_suggestion(Suggestion(category="Learning", tags=["Hidden tag name"]))

    with caplog.at_level(logging.DEBUG):
        response = _suggest(client, token)

    assert response.status_code == 200
    logged = _all_logged_text(caplog)
    assert TEXT not in logged
    assert "Hidden tag name" not in logged


def test_privacy_provider_error_that_repeats_the_text_is_not_logged(client, token, caplog):
    """The provider's exception is the cause of AIProviderError (#12); it must not be logged."""
    client.app.dependency_overrides[get_ai_provider] = lambda: _LeakyProvider()

    with caplog.at_level(logging.DEBUG):
        response = _suggest(client, token)

    assert response.status_code == 503
    assert response.json() == AI_UNAVAILABLE
    logged = _all_logged_text(caplog)
    assert "AIProviderError" in logged  # the adapter logs the error type only
    assert TEXT not in logged
    assert "could not handle" not in logged
