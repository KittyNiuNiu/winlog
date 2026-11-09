"""Generating a summary through the API (issue #17, `generateSummary` in openapi.yaml).

Covers FR-R3, FR-R4 and FR-A3, and the acceptance criteria in product-spec.md §7.4 and §8,
against real PostgreSQL. Every AI call goes to the mock provider.
"""

import dataclasses
import datetime as dt
import logging
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select

from app.ai import AIProvider, MockProvider, Suggestion, SummaryEntry, get_ai_provider
from app.ai.adapter import MAX_SUMMARY_CHARACTERS
from app.ai.limits import LIMIT_MESSAGES
from app.auth import hash_token
from app.main import create_app
from app.models import AiUsage, AiUsageGlobal, Entry, EntryTag, Summary, Tag, Token, User
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

AI_UNAVAILABLE = {"code": "ai_unavailable", "message": "The AI is not available right now."}
NO_MATCHING_ENTRIES = {
    "code": "no_matching_entries",
    "message": "No entries match this filter, so no summary was generated.",
}
JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
SUMMARY_TEXT = "In January you shipped the release and mentored two colleagues."


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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


def _entry(
    client: TestClient,
    token: str,
    date: str,
    category: str = "Achievement",
    tags: list[str] | None = None,
    text: str | None = None,
    result_impact: str | None = None,
) -> dict:
    """An entry created through the API (#9). Returns it as the API returned it."""
    response = client.post(
        "/entries",
        json={
            "text": text or f"{category} on {date}",
            "date": date,
            "category": category,
            "tags": tags or [],
            "result_impact": result_impact,
        },
        headers=_auth(token),
    )
    assert response.status_code == 201, response.json()
    return response.json()


def _generate(client: TestClient, token: str | None, body: object = None):
    headers = _auth(token) if token else {}
    return client.post("/summaries", json=JANUARY if body is None else body, headers=headers)


def _sent(entry: dict) -> SummaryEntry:
    """The SummaryEntry the AI should receive for an entry as the API returns it."""
    return SummaryEntry(
        date=dt.date.fromisoformat(entry["date"]),
        category=entry["category"],
        text=entry["text"],
        result_impact=entry["result_impact"],
        tags=tuple(entry["tags"]),
    )


def _listed(client: TestClient, token: str, body: dict) -> list[dict]:
    """The entries the list endpoint (#11) returns for the same filter."""
    params = {
        "start_date": body["period_start"],
        "end_date": body["period_end"],
        "category": body.get("categories", []),
        "tag": body.get("tags", []),
    }
    response = client.get("/entries", params=params, headers=_auth(token))
    assert response.status_code == 200
    return response.json()["entries"]


def _counts(engine: Engine) -> dict[str, int]:
    """The number of rows in each table a summary request could change."""
    tables = {
        "users": User,
        "tokens": Token,
        "entries": Entry,
        "tags": Tag,
        "entry_tags": EntryTag,
        "summaries": Summary,
        "ai_usage": AiUsage,
        "ai_usage_global": AiUsageGlobal,
    }
    with engine.connect() as connection:
        return {
            name: connection.execute(select(func.count()).select_from(model)).scalar_one()
            for name, model in tables.items()
        }


def _usage(engine: Engine, user_id: uuid.UUID) -> tuple[int, int]:
    """The user's summary count and the global count, over all days."""
    with engine.connect() as connection:
        user = connection.execute(
            select(func.coalesce(func.sum(AiUsage.request_count), 0)).where(
                AiUsage.user_id == user_id, AiUsage.request_type == "summary"
            )
        ).scalar_one()
        everyone = connection.execute(
            select(func.coalesce(func.sum(AiUsageGlobal.request_count), 0))
        ).scalar_one()
    return user, everyone


def _summaries(engine: Engine) -> list[Summary]:
    with engine.connect() as connection:
        return list(connection.execute(select(Summary)).all())


def _entry_rows(engine: Engine) -> list[tuple]:
    """Every entry, tag and tag link with all their columns, to check that none changed."""
    with engine.connect() as connection:
        return [
            *connection.execute(select(Entry).order_by(Entry.id)).all(),
            *connection.execute(select(Tag).order_by(Tag.id)).all(),
            *connection.execute(
                select(EntryTag).order_by(EntryTag.entry_id, EntryTag.tag_id)
            ).all(),
        ]


@pytest.fixture
def january(client: TestClient, token: str) -> dict[str, dict]:
    """A user's entries in and around January 2026."""
    return {
        "before": _entry(client, token, "2025-12-31", "Achievement", ["Python"]),
        "start": _entry(
            client, token, "2026-01-01", "Achievement", ["Python", "Team Lead"], result_impact="+5%"
        ),
        "learning": _entry(client, token, "2026-01-15", "Learning", ["Rust"]),
        "feedback": _entry(client, token, "2026-01-20", "Feedback"),
        "end": _entry(client, token, "2026-01-31", "Side project", ["python"]),
        "after": _entry(client, token, "2026-02-01", "Achievement", ["Python"]),
    }


# --- Success ------------------------------------------------------------------------------


def test_fr_r4_summary_is_saved_with_its_filter(client, migrated_db, user, token, contract):
    _entry(client, token, "2026-01-10", "Achievement", ["Python", "Team Lead"])
    _mock(client).return_summary(SUMMARY_TEXT)
    body = {
        **JANUARY,
        "categories": ["Achievement", "Learning"],
        "tags": [" PYTHON ", "team   lead", "Kotlin"],
    }

    response = _generate(client, token, body)

    assert response.status_code == 201, response.json()
    contract("Summary").validate(response.json())
    summary = response.json()
    assert summary["text"] == SUMMARY_TEXT
    # Tag names are cleaned with #8's rules, and use a tag's stored spelling when it exists.
    assert summary["filter"] == {
        **JANUARY,
        "categories": ["Achievement", "Learning"],
        "tags": ["Python", "Team Lead", "Kotlin"],
    }
    [row] = _summaries(migrated_db)
    assert str(row.id) == summary["id"]
    assert row.user_id == user
    assert row.period_start == dt.date(2026, 1, 1)
    assert row.period_end == dt.date(2026, 1, 31)
    assert row.filter_categories == ["Achievement", "Learning"]
    assert row.filter_tags == ["Python", "Team Lead", "Kotlin"]
    assert row.text == SUMMARY_TEXT
    assert dt.datetime.fromisoformat(summary["created_at"]) == row.created_at
    assert dt.datetime.fromisoformat(summary["updated_at"]) == row.updated_at


def test_fr_r4_summary_without_categories_or_tags_is_saved_with_empty_lists(
    client, migrated_db, token, contract
):
    _entry(client, token, "2026-01-10")

    response = _generate(client, token, JANUARY)

    assert response.status_code == 201
    contract("Summary").validate(response.json())
    assert response.json()["filter"] == {**JANUARY, "categories": [], "tags": []}
    # The default mock summary, so the text comes from the AI's answer.
    assert response.json()["text"] == "Mock summary of 1 entry from 2026-01-10 to 2026-01-10."
    [row] = _summaries(migrated_db)
    assert row.filter_categories == []
    assert row.filter_tags == []


def test_fr_r4_filter_tags_matching_each_other_are_saved_once(client, migrated_db, token):
    _entry(client, token, "2026-01-10", tags=["Go"])
    body = {**JANUARY, "tags": ["go", "GO", " Go ", "Rust", "rust"]}

    response = _generate(client, token, body)

    assert response.status_code == 201
    assert response.json()["filter"]["tags"] == ["Go", "Rust"]


def test_fr_r4_filter_tag_names_empty_after_cleaning_are_left_out(client, token):
    """An empty name matches nothing (#11), so leaving it out keeps the same filter."""
    _entry(client, token, "2026-01-10", tags=["Go"])

    response = _generate(client, token, {**JANUARY, "tags": ["", "  ", "go"]})

    assert response.status_code == 201
    assert response.json()["filter"]["tags"] == ["Go"]


def test_fr_r4_filter_categories_given_twice_are_saved_once(client, token):
    _entry(client, token, "2026-01-10", "Learning")
    body = {**JANUARY, "categories": ["Learning", "Feedback", "Learning"]}

    response = _generate(client, token, body)

    assert response.status_code == 201
    assert response.json()["filter"]["categories"] == ["Learning", "Feedback"]


def test_fr_r3_period_of_one_day_is_valid(client, token):
    _entry(client, token, "2026-01-10")

    response = _generate(client, token, {"period_start": "2026-01-10", "period_end": "2026-01-10"})

    assert response.status_code == 201


def test_fr_r3_each_request_saves_a_new_summary(client, migrated_db, token):
    _entry(client, token, "2026-01-10")

    first = _generate(client, token)
    second = _generate(client, token)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert len(_summaries(migrated_db)) == 2


def test_fr_r3_summaries_go_through_the_daily_limits(client, migrated_db, user, token):
    """The call goes through #15's limited entry point, so it is counted for the user."""
    _entry(client, token, "2026-01-10")
    assert _usage(migrated_db, user) == (0, 0)

    assert _generate(client, token).status_code == 201

    assert _usage(migrated_db, user) == (1, 1)


# --- Matching entries ---------------------------------------------------------------------


def test_fr_r3_summary_uses_only_matching_entries(client, token, january):
    """§7.4: the period includes both days, and entries outside it are not sent."""
    response = _generate(client, token, JANUARY)

    assert response.status_code == 201
    # Newest first, as the list endpoint sorts them (#11).
    expected = [january[key] for key in ("end", "feedback", "learning", "start")]
    assert _mock(client).summarise_calls == [tuple(map(_sent, expected))]


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"categories": ["Achievement"]},
        {"categories": ["Learning", "Side project"]},
        {"tags": ["python"]},
        {"tags": ["Rust", "TEAM LEAD"]},
        {"categories": ["Achievement"], "tags": ["Python"]},
        {"categories": ["Feedback"], "tags": []},
    ],
)
def test_fr_r3_summary_uses_exactly_the_entries_the_list_returns(client, token, january, extra):
    """Entries are selected with #11's shared filter, so they match the list endpoint."""
    body = {**JANUARY, **extra}
    listed = _listed(client, token, body)
    assert listed

    response = _generate(client, token, body)

    assert response.status_code == 201
    assert _mock(client).summarise_calls == [tuple(map(_sent, listed))]


def test_fr_r3_adapter_receives_only_the_fields_section_8_allows(client, migrated_db, token):
    """§8: each entry's date, category, text, Result/Impact and tags, and nothing else."""
    entry = _entry(
        client,
        token,
        "2026-01-10",
        "Learning",
        ["Team Lead", "Python"],
        text="  Learned the new deploy pipeline.\n",
        result_impact="Deploys take 5 minutes.",
    )

    assert _generate(client, token).status_code == 201

    [[sent]] = _mock(client).summarise_calls
    assert type(sent) is SummaryEntry
    assert [field.name for field in dataclasses.fields(sent)] == [
        "date",
        "category",
        "text",
        "result_impact",
        "tags",
    ]
    assert sent == SummaryEntry(
        date=dt.date(2026, 1, 10),
        category="Learning",
        text="  Learned the new deploy pipeline.\n",
        result_impact="Deploys take 5 minutes.",
        tags=("Python", "Team Lead"),
    )
    # No id, user id or email reaches the AI.
    sent_values = repr(sent)
    assert entry["id"] not in sent_values
    assert "@example.com" not in sent_values


def test_fr_r3_generating_changes_no_entry(client, migrated_db, token, january):
    before = _entry_rows(migrated_db)

    assert _generate(client, token, {**JANUARY, "tags": ["python", "New tag"]}).status_code == 201

    assert _entry_rows(migrated_db) == before
    # The filter's tag name "New tag" is saved with the summary, but no tag is created.
    with migrated_db.connect() as connection:
        assert "New tag" not in connection.execute(select(Tag.name)).scalars().all()


# --- No match -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"period_start": "2026-03-01", "period_end": "2026-03-31"},
        {**JANUARY, "categories": ["Achievement", "Feedback"], "tags": ["Rust"]},
        {**JANUARY, "tags": ["Unknown tag"]},
        {**JANUARY, "tags": ["", "   "]},
    ],
)
def test_fr_r3_no_matching_entries_makes_no_ai_call_and_saves_nothing(
    client, migrated_db, user, token, contract, january, body
):
    before = _counts(migrated_db)

    response = _generate(client, token, body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json() == NO_MATCHING_ENTRIES
    assert _mock(client).summarise_calls == []
    assert _usage(migrated_db, user) == (0, 0)
    assert _counts(migrated_db) == before


def test_fr_r3_user_without_entries_gets_no_matching_entries(client, migrated_db, token):
    response = _generate(client, token)

    assert response.status_code == 422
    assert response.json() == NO_MATCHING_ENTRIES
    assert _mock(client).summarise_calls == []
    assert _counts(migrated_db)["ai_usage_global"] == 0


def test_fr_r3_no_match_is_answered_even_when_the_limit_is_reached(make_client, migrated_db):
    """The match is checked before the limits, so the user is told the real reason."""
    client = make_client(ai_daily_summaries_per_user=0)
    token = _token(migrated_db, _user(migrated_db))

    response = _generate(client, token)

    assert response.status_code == 422
    assert response.json() == NO_MATCHING_ENTRIES


# --- Validation ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "fields"),
    [
        ({}, ["period_start", "period_end"]),
        ({"period_end": "2026-01-31"}, ["period_start"]),
        ({"period_start": "2026-01-01"}, ["period_end"]),
        ({"period_start": None, "period_end": "2026-01-31"}, ["period_start"]),
        ({"period_start": "2026-02-01", "period_end": "2026-01-31"}, ["period_end"]),
        ({"period_start": "2026-02-30", "period_end": "2026-03-31"}, ["period_start"]),
        ({"period_start": "2026-01-01", "period_end": "2026-1-31"}, ["period_end"]),
        ({"period_start": "2026-01-01T00:00:00", "period_end": "2026-01-31"}, ["period_start"]),
        ({"period_start": "2026-01-01", "period_end": 20260131}, ["period_end"]),
        ({"period_start": "not a date", "period_end": "2026-01-31"}, ["period_start"]),
        ({**JANUARY, "categories": ["Hobby"]}, ["categories.0"]),
        ({**JANUARY, "categories": ["Learning", "achievement"]}, ["categories.1"]),
        ({**JANUARY, "categories": "Learning"}, ["categories"]),
        ({**JANUARY, "categories": None}, ["categories"]),
        ({**JANUARY, "tags": ["Python", "a\x00b"]}, ["tags.1"]),
        ({**JANUARY, "tags": [42]}, ["tags.0"]),
        ({**JANUARY, "tags": None}, ["tags"]),
    ],
)
def test_fr_r3_invalid_filter_is_a_validation_error_and_not_counted(
    client, migrated_db, user, token, contract, january, body, fields
):
    before = _counts(migrated_db)

    response = _generate(client, token, body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert [field["field"] for field in response.json()["fields"]] == fields
    assert _mock(client).summarise_calls == []
    assert _usage(migrated_db, user) == (0, 0)
    assert _counts(migrated_db) == before


def test_fr_r3_tag_name_with_an_unpaired_surrogate_is_a_validation_error(
    client, migrated_db, token, january
):
    """The JSON escape `\\ud800` cannot be stored, so it must not reach the database."""
    body = b'{"period_start": "2026-01-01", "period_end": "2026-01-31", "tags": ["\\ud800"]}'

    response = client.post(
        "/summaries", content=body, headers={**_auth(token), "content-type": "application/json"}
    )

    assert response.status_code == 422
    assert [field["field"] for field in response.json()["fields"]] == ["tags.0"]
    assert _mock(client).summarise_calls == []
    assert _counts(migrated_db)["ai_usage_global"] == 0


def test_fr_r3_period_out_of_order_says_why(client, token, january):
    response = _generate(client, token, {"period_start": "2026-02-01", "period_end": "2026-01-31"})

    assert response.json()["fields"] == [
        {"field": "period_end", "reason": "Period end must not be before the period start."}
    ]


@pytest.mark.parametrize("body", [["2026-01-01"], "2026-01-01", None])
def test_fr_r3_body_that_is_not_an_object_is_a_validation_error(
    client, migrated_db, token, january, body
):
    response = client.post("/summaries", json=body, headers=_auth(token))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
    assert _mock(client).summarise_calls == []
    assert _counts(migrated_db)["ai_usage_global"] == 0


def test_fr_r3_fields_outside_the_contract_are_ignored(client, migrated_db, user, token):
    _entry(client, token, "2026-01-10")
    other = _user(migrated_db)

    response = _generate(client, token, {**JANUARY, "user_id": str(other), "text": "Mine"})

    assert response.status_code == 201
    assert response.json()["text"] != "Mine"
    [row] = _summaries(migrated_db)
    assert row.user_id == user


# --- Limits and AI errors -----------------------------------------------------------------


def test_fr_r3_reached_user_limit_returns_limit_reached(make_client, migrated_db, contract):
    client = make_client(ai_daily_summaries_per_user=1)
    user = _user(migrated_db)
    token = _token(migrated_db, user)
    _entry(client, token, "2026-01-10")
    assert _generate(client, token).status_code == 201

    response = _generate(client, token)

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "limit_reached",
        "message": LIMIT_MESSAGES["user_summaries"],
        "limit": "user_summaries",
    }
    # The limit is checked before the AI is called; a refused request is not counted or saved.
    assert len(_mock(client).summarise_calls) == 1
    assert _usage(migrated_db, user) == (1, 1)
    assert len(_summaries(migrated_db)) == 1


def test_fr_r3_reached_global_cap_returns_limit_reached(make_client, migrated_db, contract):
    client = make_client(ai_daily_requests_global=1)
    first = _token(migrated_db, _user(migrated_db))
    second = _token(migrated_db, _user(migrated_db))
    _entry(client, first, "2026-01-10")
    _entry(client, second, "2026-01-10")
    assert _generate(client, first).status_code == 201

    response = _generate(client, second)

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "limit_reached",
        "message": LIMIT_MESSAGES["global"],
        "limit": "global",
    }
    assert len(_mock(client).summarise_calls) == 1
    assert len(_summaries(migrated_db)) == 1


def test_fr_r3_ai_timeout_returns_ai_unavailable_and_saves_nothing(
    client, migrated_db, user, token, contract
):
    _entry(client, token, "2026-01-10")
    before = _counts(migrated_db)
    _mock(client).raise_timeout()

    response = _generate(client, token)

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE
    assert len(_mock(client).summarise_calls) == 1
    # The attempted call still counts (#15, §8); nothing else changed.
    after = _counts(migrated_db)
    assert after == {**before, "ai_usage": before["ai_usage"] + 1, "ai_usage_global": 1}
    assert _usage(migrated_db, user) == (1, 1)


def test_fr_r3_ai_provider_failure_returns_ai_unavailable_and_saves_nothing(
    client, migrated_db, token, contract
):
    _entry(client, token, "2026-01-10")
    before = _counts(migrated_db)
    _mock(client).raise_provider_error()

    response = _generate(client, token)

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE
    after = _counts(migrated_db)
    assert after == {**before, "ai_usage": before["ai_usage"] + 1, "ai_usage_global": 1}


@pytest.mark.parametrize("output", ["", "   \n", "a\x00b", None])
def test_fr_r3_unusable_ai_output_returns_ai_unavailable(client, migrated_db, token, output):
    """The adapter turns output that breaks its rules into a provider failure (#12)."""
    _entry(client, token, "2026-01-10")
    _mock(client).return_summary(output)  # type: ignore[arg-type]

    response = _generate(client, token)

    assert response.status_code == 503
    assert response.json() == AI_UNAVAILABLE
    assert _summaries(migrated_db) == []


@pytest.mark.parametrize("char", ["a", "語"])
def test_fr_r3_summary_over_10000_characters_returns_ai_unavailable_and_still_counts(
    client, migrated_db, user, token, contract, char
):
    """§7.4: a summary has at most 10,000 characters. A longer one is an unusable AI answer:
    nothing is saved, and the attempted call counts (product owner decision on #17, §8)."""
    _entry(client, token, "2026-01-10")
    before = _counts(migrated_db)
    _mock(client).return_summary(char * (MAX_SUMMARY_CHARACTERS + 1))

    response = _generate(client, token)

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE
    assert len(_mock(client).summarise_calls) == 1
    after = _counts(migrated_db)
    assert after == {**before, "ai_usage": before["ai_usage"] + 1, "ai_usage_global": 1}
    assert _usage(migrated_db, user) == (1, 1)
    assert _summaries(migrated_db) == []


@pytest.mark.parametrize("char", ["a", "語"])
def test_fr_r3_summary_of_exactly_10000_characters_is_saved_whole(
    client, migrated_db, token, contract, char
):
    _entry(client, token, "2026-01-10")
    text = char * MAX_SUMMARY_CHARACTERS
    _mock(client).return_summary(text)

    response = _generate(client, token)

    assert response.status_code == 201, response.json()
    contract("Summary").validate(response.json())
    assert response.json()["text"] == text
    [row] = _summaries(migrated_db)
    assert row.text == text


# --- Authentication and other users -------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-token"}])
def test_fr_a3_summary_without_valid_token_is_not_authenticated(
    client, migrated_db, token, headers, contract
):
    _entry(client, token, "2026-01-10")

    response = client.post("/summaries", json=JANUARY, headers=headers)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _mock(client).summarise_calls == []
    assert _counts(migrated_db)["ai_usage_global"] == 0
    assert _summaries(migrated_db) == []


def test_fr_a3_invalid_body_without_token_is_not_authenticated(client):
    response = client.post(
        "/summaries", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert _mock(client).summarise_calls == []


def test_fr_a3_another_users_entries_are_never_included(client, migrated_db, user, token):
    other_token = _token(migrated_db, _user(migrated_db))
    own = _entry(client, token, "2026-01-10", "Achievement", ["Python"])
    _entry(client, other_token, "2026-01-11", "Achievement", ["Python"], text="Not yours")
    _entry(client, other_token, "2026-01-12", "Learning", ["Rust"], text="Not yours either")

    for body in (JANUARY, {**JANUARY, "categories": ["Achievement"], "tags": ["python"]}):
        response = _generate(client, token, body)
        assert response.status_code == 201

    calls = _mock(client).summarise_calls
    assert calls == [(_sent(own),), (_sent(own),)]
    with migrated_db.connect() as connection:
        assert connection.execute(select(Summary.user_id)).scalars().all() == [user, user]


def test_fr_a3_another_users_tag_name_gives_no_matching_entries(
    client, migrated_db, user, token, contract
):
    _entry(client, token, "2026-01-10", "Achievement", ["Python"])
    other_token = _token(migrated_db, _user(migrated_db))
    _entry(client, other_token, "2026-01-10", "Achievement", ["Secret project"])

    response = _generate(client, token, {**JANUARY, "tags": ["Secret project"]})

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json() == NO_MATCHING_ENTRIES
    assert _mock(client).summarise_calls == []
    assert _usage(migrated_db, user) == (0, 0)
    assert _summaries(migrated_db) == []


def test_fr_a3_saved_tag_spelling_comes_only_from_the_users_own_tags(client, migrated_db, token):
    _entry(client, token, "2026-01-10", "Achievement", ["Python"])
    other_token = _token(migrated_db, _user(migrated_db))
    _entry(client, other_token, "2026-01-10", "Achievement", ["KUBERNETES"])

    response = _generate(client, token, {**JANUARY, "tags": ["python", "kubernetes"]})

    assert response.status_code == 201
    assert response.json()["filter"]["tags"] == ["Python", "kubernetes"]


# --- Privacy ------------------------------------------------------------------------------


class _LeakyProvider(AIProvider):
    """A provider whose failure message repeats the entry text, as a real one might."""

    name = "leaky"

    def _suggest(self, text: str) -> Suggestion:
        raise NotImplementedError

    def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
        raise RuntimeError(f"The provider could not handle: {entries[0].text}")


def _all_logged_text(caplog: pytest.LogCaptureFixture) -> str:
    """Every logged message, with any traceback and its causes."""
    formatter = logging.Formatter()
    return "\n".join(formatter.format(record) for record in caplog.records)


def test_privacy_entry_text_and_summary_text_are_never_logged(client, token, caplog):
    entry_text = "Negotiated the confidential vendor contract."
    _entry(client, token, "2026-01-10", text=entry_text, result_impact="Saved 40k")
    _mock(client).return_summary(SUMMARY_TEXT)

    with caplog.at_level(logging.DEBUG):
        response = _generate(client, token)

    assert response.status_code == 201
    logged = _all_logged_text(caplog)
    assert "AI summarise with provider mock succeeded" in logged  # the adapter's log line
    assert entry_text not in logged
    assert "Saved 40k" not in logged
    assert SUMMARY_TEXT not in logged


def test_privacy_provider_error_that_repeats_the_text_is_not_logged(client, token, caplog):
    """The provider's exception is the cause of AIProviderError (#12); it must not be logged."""
    entry_text = "Negotiated the confidential vendor contract."
    _entry(client, token, "2026-01-10", text=entry_text)
    client.app.dependency_overrides[get_ai_provider] = lambda: _LeakyProvider()

    with caplog.at_level(logging.DEBUG):
        response = _generate(client, token)

    assert response.status_code == 503
    assert response.json() == AI_UNAVAILABLE
    logged = _all_logged_text(caplog)
    assert "AIProviderError" in logged  # the adapter logs the error type only
    assert entry_text not in logged
    assert "could not handle" not in logged
