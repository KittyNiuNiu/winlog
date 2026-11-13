"""Maximum input sizes against real PostgreSQL (issue #43, product-spec.md §6, §7.2, §7.4).

Covers FR-E2 (entry limits), FR-S1 (suggestions), FR-R1 (filter tag names), FR-R3 (the
summary input limit, `summary_input_too_large`) and FR-R5 (edited summary text), each with
the success case, validation errors and another user (FR-A3). Data saved before the limits
existed is stored directly, as the API can no longer create it. Every AI call goes to the
mock provider.
"""

import datetime as dt
import logging
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select

from app.ai import MockProvider, Suggestion
from app.auth import hash_token
from app.main import create_app
from app.models import AiUsage, AiUsageGlobal, Entry, EntryTag, Summary, Tag, Token, User
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

EMOJI = "🎉"
JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
DAY = "2026-01-10"
SECRET = "Secretword"
TOO_LARGE = {
    "code": "summary_input_too_large",
    "message": "The matching entries are too large to summarise in one request. Narrow the filter.",
}
NO_MATCHING_ENTRIES = {
    "code": "no_matching_entries",
    "message": "No entries match this filter, so no summary was generated.",
}


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
    """Build the app with the given settings, connected to the migrated test database."""

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


def _body(**fields) -> dict:
    return {"text": "Shipped it.", "date": DAY, "category": "Achievement", **fields}


def _create(client: TestClient, token: str, **fields):
    return client.post("/entries", json=_body(**fields), headers=_auth(token))


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


def _entry_row(engine: Engine, entry_id: str) -> tuple:
    with engine.connect() as connection:
        return tuple(connection.execute(select(Entry).where(Entry.id == uuid.UUID(entry_id))).one())


def _summary_row(engine: Engine, summary_id: str) -> tuple:
    with engine.connect() as connection:
        return tuple(
            connection.execute(select(Summary).where(Summary.id == uuid.UUID(summary_id))).one()
        )


def _fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "validation_failed"
    assert SECRET not in response.text
    return [item["field"] for item in body["fields"]]


def _legacy_entry(engine: Engine, user_id: uuid.UUID, tags: list[str], **values) -> str:
    """An entry stored directly, as it may have been saved before the limits existed."""
    with engine.begin() as connection:
        entry_id = connection.execute(
            insert(Entry)
            .values(user_id=user_id, date=dt.date(2026, 1, 10), category="Learning", **values)
            .returning(Entry.id)
        ).scalar_one()
        for name in tags:
            tag_id = connection.execute(
                insert(Tag).values(user_id=user_id, name=name).returning(Tag.id)
            ).scalar_one()
            connection.execute(insert(EntryTag).values(entry_id=entry_id, tag_id=tag_id))
    return str(entry_id)


def _legacy_summary(engine: Engine, user_id: uuid.UUID, text: str) -> str:
    with engine.begin() as connection:
        return str(
            connection.execute(
                insert(Summary)
                .values(
                    user_id=user_id,
                    period_start=dt.date(2026, 1, 1),
                    period_end=dt.date(2026, 1, 31),
                    filter_categories=[],
                    filter_tags=[],
                    text=text,
                )
                .returning(Summary.id)
            ).scalar_one()
        )


# --- Entries (FR-E2, FR-E4) ---------------------------------------------------------------


def test_fr_e2_entry_at_every_limit_is_saved_exactly(client, migrated_db, alice_token, contract):
    tags = [f"{number}" + EMOJI * 39 for number in range(10)]
    response = _create(
        client, alice_token, text=EMOJI * 2_000, result_impact=EMOJI * 500, tags=tags
    )

    assert response.status_code == 201, response.text
    entry = response.json()
    contract("Entry").validate(entry)
    assert entry["text"] == EMOJI * 2_000
    assert entry["result_impact"] == EMOJI * 500
    assert sorted(entry["tags"]) == sorted(tags)
    stored = client.get(f"/entries/{entry['id']}", headers=_auth(alice_token)).json()
    assert stored == entry


@pytest.mark.parametrize(
    ("fields", "named"),
    [
        ({"text": SECRET * 201}, ["text"]),
        ({"result_impact": SECRET * 51}, ["result_impact"]),
        ({"result_impact": " " * 501}, ["result_impact"]),
        ({"tags": [f"t{number}" for number in range(11)]}, ["tags"]),
        ({"tags": ["Go", SECRET * 5]}, ["tags.1"]),
    ],
)
def test_fr_e2_entry_over_a_limit_is_rejected_and_nothing_is_saved(
    client, migrated_db, alice_token, contract, fields, named
):
    before = _counts(migrated_db)

    response = _create(client, alice_token, **fields)

    contract("Error").validate(response.json())
    assert _fields(response) == named
    assert _counts(migrated_db) == before


def test_fr_e2_9000_character_tag_gets_a_validation_error_not_a_500(
    client, migrated_db, alice_token, contract
):
    """#9's QA: PostgreSQL's index on tag names rejected it with a 500 before #43."""
    response = _create(client, alice_token, tags=[SECRET * 900])

    contract("Error").validate(response.json())
    assert _fields(response) == ["tags.0"]
    assert _counts(migrated_db)["tags"] == 0


def test_fr_e4_update_over_a_limit_changes_nothing(client, migrated_db, alice_token):
    entry = _create(client, alice_token).json()
    before = _entry_row(migrated_db, entry["id"])

    response = client.put(
        f"/entries/{entry['id']}",
        json=_body(text=SECRET * 201, tags=["t" * 41]),
        headers=_auth(alice_token),
    )

    assert _fields(response) == ["text", "tags.0"]
    assert _entry_row(migrated_db, entry["id"]) == before


def test_fr_a3_another_user_cannot_update_an_entry_within_the_limits(
    client, migrated_db, alice_token, bob_token
):
    entry = _create(client, alice_token).json()
    before = _entry_row(migrated_db, entry["id"])

    response = client.put(
        f"/entries/{entry['id']}", json=_body(text="x" * 2_000), headers=_auth(bob_token)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert _entry_row(migrated_db, entry["id"]) == before


def test_fr_e2_entry_saved_before_the_limits_can_be_read_listed_and_exported(
    client, migrated_db, alice, alice_token
):
    long_tags = [f"Tag {number}" for number in range(11)] + ["L" * 50]
    entry_id = _legacy_entry(
        migrated_db, alice, long_tags, text="T" * 2_500, result_impact="R" * 600
    )

    entry = client.get(f"/entries/{entry_id}", headers=_auth(alice_token)).json()
    assert entry["text"] == "T" * 2_500
    assert entry["result_impact"] == "R" * 600
    assert len(entry["tags"]) == 12
    listed = client.get("/entries", headers=_auth(alice_token)).json()["entries"]
    assert [item["id"] for item in listed] == [entry_id]
    for path in ("/export/json", "/export/markdown"):
        response = client.get(path, headers=_auth(alice_token))
        assert response.status_code == 200
        assert "T" * 2_500 in response.text
        assert "L" * 50 in response.text


def test_fr_e2_entry_saved_before_the_limits_is_rejected_unchanged_and_saved_shortened(
    client, migrated_db, alice, alice_token
):
    long_tags = [f"Tag {number}" for number in range(10)] + ["L" * 50]
    entry_id = _legacy_entry(
        migrated_db, alice, long_tags, text="T" * 2_500, result_impact="R" * 600
    )
    entry = client.get(f"/entries/{entry_id}", headers=_auth(alice_token)).json()
    unchanged = {key: entry[key] for key in ("text", "date", "category", "tags", "result_impact")}
    before = _entry_row(migrated_db, entry_id)

    response = client.put(f"/entries/{entry_id}", json=unchanged, headers=_auth(alice_token))

    assert response.status_code == 422
    fields = [item["field"] for item in response.json()["fields"]]
    assert fields[0] == "text" and fields[-1] == "result_impact"
    assert any(field.startswith("tags.") for field in fields)
    assert _entry_row(migrated_db, entry_id) == before

    shortened = {
        **unchanged,
        "text": "T" * 2_000,
        "result_impact": "R" * 500,
        "tags": [name for name in entry["tags"] if len(name) <= 40][:10],
    }
    response = client.put(f"/entries/{entry_id}", json=shortened, headers=_auth(alice_token))

    assert response.status_code == 200, response.text
    assert response.json()["text"] == "T" * 2_000
    assert len(response.json()["tags"]) == 10


# --- Filter tag names (FR-R1) -------------------------------------------------------------


def test_fr_r1_list_filter_tag_of_40_characters_matches_and_41_is_rejected(
    client, alice_token, bob_token, contract
):
    name = "t" * 40
    entry = _create(client, alice_token, tags=[name]).json()

    found = client.get("/entries", params={"tag": name}, headers=_auth(alice_token))
    assert [item["id"] for item in found.json()["entries"]] == [entry["id"]]
    # Another user's filter with the same name matches nothing (FR-A3).
    other = client.get("/entries", params={"tag": name}, headers=_auth(bob_token))
    assert other.json()["entries"] == []

    response = client.get("/entries", params={"tag": name + "t"}, headers=_auth(alice_token))
    contract("Error").validate(response.json())
    assert _fields(response) == ["tag.0"]


# --- Suggestions (FR-S1, FR-S3) -----------------------------------------------------------


def test_fr_s1_suggestion_text_of_2000_characters_is_sent(client, alice_token):
    response = client.post("/suggestions", json={"text": EMOJI * 2_000}, headers=_auth(alice_token))

    assert response.status_code == 200, response.text
    assert _mock(client).suggest_calls == [EMOJI * 2_000]


def test_fr_s1_suggestion_text_over_2000_characters_makes_no_ai_call_and_counts_nothing(
    client, migrated_db, alice_token, contract
):
    response = client.post("/suggestions", json={"text": SECRET * 201}, headers=_auth(alice_token))

    contract("Error").validate(response.json())
    assert _fields(response) == ["text"]
    assert _mock(client).suggest_calls == []
    assert _counts(migrated_db)["ai_usage"] == 0


def test_fr_s3_suggested_tags_over_40_characters_are_left_out_before_taking_five(
    client, alice_token, contract
):
    long = "L" * 41
    _mock(client).return_suggestion(
        Suggestion(
            category="Learning",
            tags=[long, "One", "  " + "t" * 40 + "  ", "Two", long + "x", "Three", "Four", "Five"],
        )
    )

    response = client.post("/suggestions", json={"text": "Learned Go."}, headers=_auth(alice_token))

    assert response.status_code == 200
    contract("Suggestion").validate(response.json())
    # The 40-character name is valid after cleaning; the two 41+ names are left out.
    assert response.json()["tags"] == ["One", "t" * 40, "Two", "Three", "Four"]


def test_fr_s3_every_suggested_tag_can_be_saved(client, alice_token):
    _mock(client).return_suggestion(
        Suggestion(category="Learning", tags=["L" * 60, EMOJI * 40, "Go"])
    )
    tags = client.post(
        "/suggestions", json={"text": "Learned Go."}, headers=_auth(alice_token)
    ).json()["tags"]

    assert tags == [EMOJI * 40, "Go"]
    assert _create(client, alice_token, tags=tags).status_code == 201


# --- Summary input (FR-R3) ----------------------------------------------------------------


def _summary_entries(client: TestClient, token: str) -> int:
    """Two January entries with 300 characters together: text, Result/Impact and tag names."""
    _create(client, token, text="a" * 100, result_impact="b" * 50, tags=["Go", "Python"])
    _create(client, token, text=EMOJI * 142)
    return 100 + 50 + 2 + 6 + 142


def test_fr_r3_summary_input_exactly_at_the_limit_is_generated(make_client, migrated_db):
    client = make_client(ai_summary_max_input_characters=300)
    token = _token(migrated_db, _user(migrated_db))
    assert _summary_entries(client, token) == 300

    response = client.post("/summaries", json=JANUARY, headers=_auth(token))

    assert response.status_code == 201, response.text
    assert len(_mock(client).summarise_calls) == 1


def test_fr_r3_summary_input_over_the_limit_makes_no_ai_call_counts_nothing_and_saves_nothing(
    make_client, migrated_db, contract
):
    client = make_client(ai_summary_max_input_characters=299)
    token = _token(migrated_db, _user(migrated_db))
    _summary_entries(client, token)
    before = _counts(migrated_db)

    response = client.post("/summaries", json=JANUARY, headers=_auth(token))

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json() == TOO_LARGE
    assert _mock(client).summarise_calls == []
    assert _counts(migrated_db) == before


def test_fr_r3_summary_input_counts_only_the_matching_entries(make_client, migrated_db):
    client = make_client(ai_summary_max_input_characters=300)
    token = _token(migrated_db, _user(migrated_db))
    _summary_entries(client, token)
    _create(client, token, text="x" * 2_000, date="2026-02-10")
    # Another user's entries never count (FR-A3).
    other = _token(migrated_db, _user(migrated_db))
    _create(client, other, text="y" * 2_000)

    response = client.post("/summaries", json=JANUARY, headers=_auth(token))

    assert response.status_code == 201, response.text


def test_fr_r3_default_summary_input_limit_is_50000(client, migrated_db, alice_token):
    for day in range(1, 26):
        assert _create(client, alice_token, text="x" * 2_000, date=f"2026-01-{day:02}").is_success
    at_limit = client.post("/summaries", json=JANUARY, headers=_auth(alice_token))
    assert at_limit.status_code == 201, at_limit.text

    _create(client, alice_token, text="x", date="2026-01-31")
    over = client.post("/summaries", json=JANUARY, headers=_auth(alice_token))
    assert over.json() == TOO_LARGE


def test_fr_r3_no_matching_entries_is_checked_before_the_input_size(make_client, migrated_db):
    client = make_client(ai_summary_max_input_characters=1)
    token = _token(migrated_db, _user(migrated_db))
    _create(client, token, text="Shipped it.", date="2026-03-01")

    response = client.post("/summaries", json=JANUARY, headers=_auth(token))

    assert response.json() == NO_MATCHING_ENTRIES


def test_fr_r3_request_validation_is_checked_before_the_input_size(make_client, migrated_db):
    client = make_client(ai_summary_max_input_characters=1)
    token = _token(migrated_db, _user(migrated_db))
    _create(client, token)

    response = client.post(
        "/summaries", json={**JANUARY, "categories": ["Hobby"]}, headers=_auth(token)
    )

    assert _fields(response) == ["categories.0"]


def test_fr_r3_too_much_text_is_answered_even_when_todays_summaries_are_used(
    make_client, migrated_db
):
    """The input size is checked before the daily limits, so it never counts (#15)."""
    client = make_client(
        ai_summary_max_input_characters=10,
        ai_daily_summaries_per_user=0,
        ai_daily_requests_global=0,
    )
    token = _token(migrated_db, _user(migrated_db))
    _create(client, token, text="x" * 100)
    before = _counts(migrated_db)

    response = client.post("/summaries", json=JANUARY, headers=_auth(token))

    assert response.json() == TOO_LARGE
    assert _counts(migrated_db) == before


def test_fr_r3_entries_saved_before_the_limits_can_be_summarised_within_the_input_limit(
    client, migrated_db, alice, alice_token
):
    _legacy_entry(migrated_db, alice, ["L" * 50], text="T" * 2_500, result_impact="R" * 600)

    response = client.post("/summaries", json=JANUARY, headers=_auth(alice_token))

    assert response.status_code == 201, response.text
    [[sent]] = _mock(client).summarise_calls
    assert sent.text == "T" * 2_500
    assert sent.tags == ("L" * 50,)


def test_fr_r3_summary_filter_tag_of_40_characters_is_valid_and_41_is_rejected(
    client, migrated_db, alice_token, contract
):
    name = "t" * 40
    _create(client, alice_token, tags=[name])

    response = client.post(
        "/summaries", json={**JANUARY, "tags": [name]}, headers=_auth(alice_token)
    )
    assert response.status_code == 201, response.text
    assert response.json()["filter"]["tags"] == [name]

    before = _counts(migrated_db)
    response = client.post(
        "/summaries", json={**JANUARY, "tags": [name + "t"]}, headers=_auth(alice_token)
    )
    contract("Error").validate(response.json())
    assert _fields(response) == ["tags.0"]
    assert _counts(migrated_db) == before


# --- Edited summary text (FR-R5) ----------------------------------------------------------


def test_fr_r5_summary_text_of_10000_characters_is_saved(client, migrated_db, alice, alice_token):
    summary_id = _legacy_summary(migrated_db, alice, "Short.")

    response = client.patch(
        f"/summaries/{summary_id}", json={"text": EMOJI * 10_000}, headers=_auth(alice_token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["text"] == EMOJI * 10_000


def test_fr_r5_summary_text_over_10000_characters_is_rejected_and_changes_nothing(
    client, migrated_db, alice, alice_token, contract
):
    summary_id = _legacy_summary(migrated_db, alice, "Short.")
    before = _summary_row(migrated_db, summary_id)

    response = client.patch(
        f"/summaries/{summary_id}", json={"text": SECRET * 1_001}, headers=_auth(alice_token)
    )

    contract("Error").validate(response.json())
    assert _fields(response) == ["text"]
    assert _summary_row(migrated_db, summary_id) == before


def test_fr_a3_another_user_cannot_edit_a_summary_within_the_limit(
    client, migrated_db, alice, bob_token
):
    summary_id = _legacy_summary(migrated_db, alice, "Short.")
    before = _summary_row(migrated_db, summary_id)

    response = client.patch(
        f"/summaries/{summary_id}", json={"text": "s" * 10_000}, headers=_auth(bob_token)
    )

    assert response.status_code == 404
    assert _summary_row(migrated_db, summary_id) == before


def test_fr_r5_summary_saved_before_the_limit_can_be_read_and_saved_shortened(
    client, migrated_db, alice, alice_token
):
    summary_id = _legacy_summary(migrated_db, alice, "S" * 12_000)

    assert (
        client.get(f"/summaries/{summary_id}", headers=_auth(alice_token)).json()["text"]
        == "S" * 12_000
    )
    listed = client.get("/summaries", headers=_auth(alice_token)).json()["summaries"]
    assert listed[0]["text"] == "S" * 12_000

    unchanged = client.patch(
        f"/summaries/{summary_id}", json={"text": "S" * 12_000}, headers=_auth(alice_token)
    )
    assert unchanged.status_code == 422
    shortened = client.patch(
        f"/summaries/{summary_id}", json={"text": "S" * 10_000}, headers=_auth(alice_token)
    )
    assert shortened.status_code == 200
    assert shortened.json()["text"] == "S" * 10_000


# --- Privacy ------------------------------------------------------------------------------


def test_privacy_over_limit_text_is_never_logged(make_client, migrated_db, caplog):
    client = make_client(ai_summary_max_input_characters=10)
    token = _token(migrated_db, _user(migrated_db))
    caplog.set_level(logging.DEBUG)

    _create(client, token, text=SECRET * 201, tags=[SECRET * 5])
    client.post("/suggestions", json={"text": SECRET * 201}, headers=_auth(token))
    _create(client, token, text=SECRET)
    client.post("/summaries", json=JANUARY, headers=_auth(token))

    assert SECRET not in caplog.text
