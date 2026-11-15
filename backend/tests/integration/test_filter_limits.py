"""How many values a filter holds, against real PostgreSQL (issue #88, product-spec.md §7.4).

Covers FR-R1 (`GET /entries`), FR-R3 (`POST /summaries`) and FR-R4 (saved filters). A filter
holds at most 20 tag names and 4 categories, counted as sent. Up to the limit, filters match
exactly as before. Summaries saved before the limits are stored directly, as the API can no
longer create them, and are still returned in full. Every AI call goes to the mock provider.
"""

import datetime as dt
import json
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select

from app.ai import MockProvider
from app.auth import hash_token
from app.main import create_app
from app.models import (
    CATEGORIES,
    AiUsage,
    AiUsageGlobal,
    Entry,
    EntryTag,
    Summary,
    Tag,
    Token,
    User,
)
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
DAY = "2026-01-10"
EMOJI = "🎉"
TOO_MANY_TAGS = "A filter can have at most 20 tag names."
TOO_MANY_CATEGORIES = "A filter can have at most 4 categories."
NO_MATCHING_ENTRIES = "no_matching_entries"


# --- Helpers ------------------------------------------------------------------------------


def _user(engine: Engine) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(User)
            .values(email=f"user-{uuid.uuid4()}@example.com", password_hash="hash")
            .returning(User.id)
        ).scalar_one()


def _token(engine: Engine, user_id: uuid.UUID) -> str:
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


@pytest.fixture
def make_client(test_database_url: str, migrated_db: Engine) -> Callable[..., TestClient]:
    def build(**settings: int) -> TestClient:
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

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def _mock(client: TestClient) -> MockProvider:
    provider = client.app.state.ai_provider
    assert isinstance(provider, MockProvider)
    return provider


@pytest.fixture
def alice(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db)


@pytest.fixture
def alice_token(migrated_db: Engine, alice: uuid.UUID) -> str:
    return _token(migrated_db, alice)


@pytest.fixture
def bob_token(migrated_db: Engine) -> str:
    return _token(migrated_db, _user(migrated_db))


def _create(client: TestClient, token: str, **fields) -> str:
    body = {"text": "Shipped it.", "date": DAY, "category": "Achievement", **fields}
    response = client.post("/entries", json=body, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _list(client: TestClient, token: str, **params):
    return client.get("/entries", params=params, headers=_auth(token))


def _listed_ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [entry["id"] for entry in response.json()["entries"]]


def _fields(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "validation_failed"
    return [(item["field"], item["reason"]) for item in body["fields"]]


def _counts(engine: Engine) -> dict[str, int]:
    tables = {
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


def _tags(count: int, prefix: str = "tag") -> list[str]:
    return [f"{prefix}-{number}" for number in range(count)]


# --- GET /entries (FR-R1) ----------------------------------------------------------------


def test_fr_r1_list_with_20_tags_answers_200_and_21_answers_422_naming_tag(
    client, alice_token, contract
):
    tags = _tags(21)
    first = _create(client, alice_token, tags=tags[:10])
    second = _create(client, alice_token, tags=tags[10:20])
    _create(client, alice_token, tags=["other"])

    response = _list(client, alice_token, tag=tags[:20])
    assert sorted(_listed_ids(response)) == sorted([first, second])
    contract("EntryList").validate(response.json())

    response = _list(client, alice_token, tag=tags)
    contract("Error").validate(response.json())
    assert _fields(response) == [("tag", TOO_MANY_TAGS)]


def _bob_tags(engine: Engine, client: TestClient) -> list[str]:
    token = _token(engine, _user(engine))
    names = _tags(10, "bob") + _tags(10, "bob-more")
    _create(client, token, tags=names[:10])
    _create(client, token, tags=names[10:])
    return names


# For each way of writing 21 names: the names, and the entries 20 of them match today.
@pytest.mark.parametrize(
    "kind",
    [
        "one_name_repeated",
        "names_that_differ_only_in_case",
        "empty_or_only_spaces",
        "names_the_user_has_no_tag_for",
        "another_users_tag_names",
    ],
)
def test_fr_r1_21_values_are_rejected_and_20_match_exactly_as_before(
    client, migrated_db, alice_token, kind
):
    go = _create(client, alice_token, tags=["Go"])
    _create(client, alice_token, tags=["Python"])
    names, expected = {
        "one_name_repeated": (["Go"] * 21, [go]),
        "names_that_differ_only_in_case": ((["go", "GO", " gO "] * 7), [go]),
        "empty_or_only_spaces": (["", " ", "   "] * 7, []),
        "names_the_user_has_no_tag_for": (_tags(21, "nobody"), []),
        "another_users_tag_names": ([*_bob_tags(migrated_db, client), "Rust"], []),
    }[kind]
    assert len(names) == 21

    assert _fields(_list(client, alice_token, tag=names)) == [("tag", TOO_MANY_TAGS)]
    assert _listed_ids(_list(client, alice_token, tag=names[:20])) == expected
    # The same as without the count limit: one name of the 20 matches the same entries.
    if expected:
        assert _listed_ids(_list(client, alice_token, tag=names[:1])) == expected


def test_fr_r1_list_with_4_categories_answers_200_and_5_answers_422_naming_category(
    client, alice_token
):
    ids = {category: _create(client, alice_token, category=category) for category in CATEGORIES}

    response = _list(client, alice_token, category=list(CATEGORIES))
    assert sorted(_listed_ids(response)) == sorted(ids.values())
    # Repeated values within the count are accepted, as before.
    response = _list(client, alice_token, category=["Learning"] * 4)
    assert _listed_ids(response) == [ids["Learning"]]

    response = _list(client, alice_token, category=[*CATEGORIES, "Learning"])
    assert _fields(response) == [("category", TOO_MANY_CATEGORIES)]


def test_fr_r1_20_names_of_40_characters_are_accepted_and_41_still_names_the_value(
    client, alice_token
):
    names = [f"{number:02d}" + EMOJI * 38 for number in range(20)]
    entry = _create(client, alice_token, tags=names[:10])

    assert _listed_ids(_list(client, alice_token, tag=names)) == [entry]

    response = _list(client, alice_token, tag=[*names[:19], "t" * 41])
    assert [field for field, _ in _fields(response)] == ["tag.19"]


# --- POST /summaries (FR-R3) -------------------------------------------------------------


def test_fr_r3_summary_with_20_tags_is_generated(client, migrated_db, alice_token, contract):
    tags = _tags(20)
    _create(client, alice_token, tags=tags[:10])
    _create(client, alice_token, tags=tags[10:])

    response = client.post(
        "/summaries",
        json={**JANUARY, "tags": tags, "categories": list(CATEGORIES)},
        headers=_auth(alice_token),
    )

    assert response.status_code == 201, response.text
    contract("Summary").validate(response.json())
    assert response.json()["filter"]["tags"] == tags
    assert len(_mock(client).summarise_calls) == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"tags": _tags(21)}, [("tags", TOO_MANY_TAGS)]),
        ({"tags": ["Go"] * 21}, [("tags", TOO_MANY_TAGS)]),
        ({"categories": [*CATEGORIES, "Feedback"]}, [("categories", TOO_MANY_CATEGORIES)]),
    ],
)
@pytest.mark.parametrize(
    ("settings", "situation"),
    [
        ({}, "entries_match"),
        ({}, "no_entries_match"),
        ({"ai_summary_max_input_characters": 1}, "entries_match"),
        ({"ai_daily_summaries_per_user": 0, "ai_daily_requests_global": 0}, "entries_match"),
    ],
    ids=["valid_otherwise", "no_matching_entries", "input_too_large", "daily_limits_reached"],
)
def test_fr_r3_too_many_filter_values_are_rejected_before_every_other_check(
    make_client, migrated_db, contract, body, expected, settings, situation
):
    client = make_client(**settings)
    token = _token(migrated_db, _user(migrated_db))
    date = DAY if situation == "entries_match" else "2026-03-01"
    _create(client, token, text="x" * 100, date=date, tags=["Go"])
    before = _counts(migrated_db)

    response = client.post("/summaries", json={**JANUARY, **body}, headers=_auth(token))

    contract("Error").validate(response.json())
    assert _fields(response) == expected
    # No AI call, no count changed, nothing saved.
    assert _mock(client).summarise_calls == []
    assert _counts(migrated_db) == before


def test_fr_r3_the_other_checks_still_answer_with_20_tags(make_client, migrated_db):
    """With a valid count, the request goes on to the next check, as before."""
    client = make_client()
    token = _token(migrated_db, _user(migrated_db))
    _create(client, token, date="2026-03-01", tags=["Go"])

    response = client.post(
        "/summaries", json={**JANUARY, "tags": ["Go"] * 20}, headers=_auth(token)
    )

    assert response.status_code == 422
    assert response.json()["code"] == NO_MATCHING_ENTRIES


def test_fr_r3_20_names_of_40_characters_generate_and_41_is_rejected(
    client, migrated_db, alice_token
):
    names = [f"{number:02d}" + EMOJI * 38 for number in range(20)]
    _create(client, alice_token, tags=names[:10])

    response = client.post(
        "/summaries", json={**JANUARY, "tags": names}, headers=_auth(alice_token)
    )
    assert response.status_code == 201, response.text
    assert response.json()["filter"]["tags"] == names[:10] + names[10:]

    before = _counts(migrated_db)
    response = client.post(
        "/summaries", json={**JANUARY, "tags": [*names[:19], "t" * 41]}, headers=_auth(alice_token)
    )
    assert [field for field, _ in _fields(response)] == ["tags.19"]
    assert _counts(migrated_db) == before


# --- Saved filters (FR-R4) ---------------------------------------------------------------

# 25 tag names, one of them 50 characters long: more and longer than a filter may hold now.
SAVED_TAGS = [*_tags(24, "saved"), "L" * 50]


def _legacy_summary(engine: Engine, user_id: uuid.UUID) -> str:
    """A summary stored directly, as one saved before the limits may be."""
    with engine.begin() as connection:
        return str(
            connection.execute(
                insert(Summary)
                .values(
                    user_id=user_id,
                    period_start=dt.date(2026, 1, 1),
                    period_end=dt.date(2026, 1, 31),
                    filter_categories=["Learning"],
                    filter_tags=SAVED_TAGS,
                    text="A summary from before the limits.",
                )
                .returning(Summary.id)
            ).scalar_one()
        )


def _saved_filter(engine: Engine, summary_id: str) -> tuple:
    with engine.connect() as connection:
        return connection.execute(
            select(
                Summary.period_start,
                Summary.period_end,
                Summary.filter_categories,
                Summary.filter_tags,
            ).where(Summary.id == uuid.UUID(summary_id))
        ).one()


def test_fr_r4_summary_saved_before_the_limits_is_returned_in_full(
    client, migrated_db, alice, alice_token, bob_token, contract
):
    summary_id = _legacy_summary(migrated_db, alice)
    saved = _saved_filter(migrated_db, summary_id)
    expected_filter = {**JANUARY, "categories": ["Learning"], "tags": SAVED_TAGS}

    listed = client.get("/summaries", headers=_auth(alice_token))
    assert listed.status_code == 200, listed.text
    contract("SummaryList").validate(listed.json())
    [summary] = listed.json()["summaries"]
    contract("Summary").validate(summary)
    assert summary["filter"] == expected_filter

    read = client.get(f"/summaries/{summary_id}", headers=_auth(alice_token))
    assert read.status_code == 200, read.text
    contract("Summary").validate(read.json())
    assert read.json()["filter"] == expected_filter

    edited = client.patch(
        f"/summaries/{summary_id}",
        json={"text": "Edited.", "filter": {**JANUARY, "tags": ["changed"]}},
        headers=_auth(alice_token),
    )
    assert edited.status_code == 200, edited.text
    contract("Summary").validate(edited.json())
    assert edited.json()["filter"] == expected_filter
    assert edited.json()["text"] == "Edited."
    # The saved filter never changes.
    assert _saved_filter(migrated_db, summary_id) == saved

    # Another user still cannot reach it (FR-A3).
    assert client.get(f"/summaries/{summary_id}", headers=_auth(bob_token)).status_code == 404


def test_fr_r4_summary_saved_before_the_limits_is_exported_with_every_tag(
    client, migrated_db, alice, alice_token, contract
):
    summary_id = _legacy_summary(migrated_db, alice)

    exported = client.get("/export/json", headers=_auth(alice_token))
    assert exported.status_code == 200, exported.text
    data = json.loads(exported.content)
    contract("ExportFile").validate(data)
    [summary] = data["summaries"]
    assert summary["id"] == summary_id
    assert summary["filter"]["tags"] == SAVED_TAGS

    markdown = client.get("/export/markdown", headers=_auth(alice_token))
    assert markdown.status_code == 200, markdown.text
    assert f"Tags: {', '.join(SAVED_TAGS)}" in markdown.text
