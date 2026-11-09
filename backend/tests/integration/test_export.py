"""The data export through the API, against real PostgreSQL (issue #19).

Operations `exportJson` and `exportMarkdown` in openapi.yaml. Covers FR-D1 and FR-A3, and the
acceptance criteria in product-spec.md §7.6 and §8. Summaries are generated with the mock AI
provider or stored directly; no test calls a real AI.
"""

import datetime as dt
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, select

from app.ai import MockProvider
from app.auth import hash_token
from app.main import create_app
from app.models import AiUsage, AiUsageGlobal, Entry, EntryTag, Summary, Tag, Token, User
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN
from tests.integration.test_entries import _token, _user

JSON_PATH = "/export/json"
MARKDOWN_PATH = "/export/markdown"
PATHS = [JSON_PATH, MARKDOWN_PATH]
FILTER = {"period_start": "2026-10-01", "period_end": "2026-10-31"}
ENTRIES = [
    {
        "text": "Gave a talk on testing.",
        "date": "2026-10-15",
        "category": "Learning",
        "tags": ["Testing", "Public speaking"],
        "result_impact": "Two teams adopted the approach.",
    },
    {
        "text": "Shipped the release.",
        "date": "2026-10-20",
        "category": "Achievement",
        "tags": [],
    },
    {
        "text": "Got feedback on the design review.",
        "date": "2026-10-15",
        "category": "Feedback",
        "tags": ["Design"],
        "result_impact": "Clearer reviews.",
    },
    {
        "text": "Built a bird feeder.",
        "date": "2026-09-01",
        "category": "Side project",
        "tags": ["Woodwork"],
    },
]


# --- Helpers ------------------------------------------------------------------------------


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _export(client: TestClient, token: str | None, path: str):
    return client.get(path, headers=_headers(token))


def _json(client: TestClient, token: str) -> dict:
    response = _export(client, token, JSON_PATH)
    assert response.status_code == 200
    return response.json()


def _markdown(client: TestClient, token: str) -> str:
    response = _export(client, token, MARKDOWN_PATH)
    assert response.status_code == 200
    return response.text


def _create(client: TestClient, token: str, body: dict) -> dict:
    response = client.post("/entries", json=body, headers=_headers(token))
    assert response.status_code == 201
    return response.json()


def _generate(client: TestClient, token: str, body: dict | None = None) -> dict:
    response = client.post("/summaries", json=body or FILTER, headers=_headers(token))
    assert response.status_code == 201
    return response.json()


def _stored_summary(
    engine: Engine,
    user_id: uuid.UUID,
    text: str,
    created_at: dt.datetime,
    categories: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    values = {
        "user_id": user_id,
        "period_start": dt.date(2026, 1, 1),
        "period_end": dt.date(2026, 3, 31),
        "filter_categories": categories or [],
        "filter_tags": tags or [],
        "text": text,
        "created_at": created_at,
        "updated_at": created_at,
    }
    with engine.begin() as connection:
        return str(
            connection.execute(insert(Summary).values(values).returning(Summary.id)).one().id
        )


def _list(client: TestClient, token: str, path: str) -> list[dict]:
    response = client.get(path, headers=_headers(token))
    assert response.status_code == 200
    return response.json()[path.strip("/")]


def _counts(engine: Engine) -> dict[str, int]:
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


def _entry_markdown(entry: dict) -> str:
    lines = [f"### {entry['date']} · {entry['category']}", entry["text"]]
    if entry["result_impact"] is not None:
        lines.append(f"Result/Impact: {entry['result_impact']}")
    lines.append(f"Tags: {', '.join(entry['tags']) or 'None'}")
    return "\n\n".join(lines) + "\n\n"


def _summary_heading(summary: dict) -> str:
    summary_filter = summary["filter"]
    created = dt.datetime.fromisoformat(summary["created_at"]).astimezone(dt.UTC).date()
    return (
        f"### {created.isoformat()} · {summary_filter['period_start']} to "
        f"{summary_filter['period_end']} · "
        f"Categories: {', '.join(summary_filter['categories']) or 'all'} · "
        f"Tags: {', '.join(summary_filter['tags']) or 'all'}"
    )


@pytest.fixture
def alice(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db, "alice@example.com")


@pytest.fixture
def alice_token(migrated_db: Engine, alice: uuid.UUID) -> str:
    return _token(migrated_db, alice)


@pytest.fixture
def filled(client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str) -> None:
    """Alice's four entries, a generated summary and two stored ones with older dates."""
    for body in ENTRIES:
        _create(client, alice_token, body)
    _stored_summary(
        migrated_db,
        alice,
        "The first quarter.",
        dt.datetime(2026, 4, 1, 10, 0, tzinfo=dt.UTC),
        categories=["Feedback"],
        tags=["Design"],
    )
    _stored_summary(
        migrated_db, alice, "The second quarter.", dt.datetime(2026, 7, 1, 10, 0, tzinfo=dt.UTC)
    )
    _generate(client, alice_token, {**FILTER, "categories": ["Learning"], "tags": ["testing"]})


# --- Shared data and order ----------------------------------------------------------------


def test_fr_d1_json_export_contains_every_entry(client, alice_token, filled, contract):
    exported = _json(client, alice_token)

    contract("ExportFile").validate(exported)
    # Every entry, with all fields and in the entry list's order (#11).
    assert exported["entries"] == _list(client, alice_token, "/entries")
    assert len(exported["entries"]) == len(ENTRIES)
    assert [(entry["date"], entry["category"]) for entry in exported["entries"]] == [
        ("2026-10-20", "Achievement"),
        ("2026-10-15", "Feedback"),  # same date: created later, so first
        ("2026-10-15", "Learning"),
        ("2026-09-01", "Side project"),
    ]
    learning = exported["entries"][2]
    assert learning["tags"] == ["Public speaking", "Testing"]
    assert learning["result_impact"] == "Two teams adopted the approach."
    assert exported["entries"][0]["result_impact"] is None
    assert exported["entries"][0]["tags"] == []


def test_fr_d1_json_export_contains_every_summary(client, alice_token, filled, contract):
    exported = _json(client, alice_token)

    # Every summary with its filter, newest first by creation time (#18).
    assert exported["summaries"] == _list(client, alice_token, "/summaries")
    texts = [summary["text"] for summary in exported["summaries"]]
    assert texts[1:] == ["The second quarter.", "The first quarter."]
    assert texts[0].startswith("Mock summary")
    assert exported["summaries"][0]["filter"] == {
        **FILTER,
        "categories": ["Learning"],
        "tags": ["Testing"],  # the stored spelling
    }
    assert exported["summaries"][2]["filter"]["categories"] == ["Feedback"]
    assert exported["summaries"][2]["filter"]["tags"] == ["Design"]


def test_fr_d1_json_export_has_format_version_and_export_time(client, alice_token, filled):
    before = dt.datetime.now(dt.UTC)
    exported = _json(client, alice_token)
    after = dt.datetime.now(dt.UTC)

    assert set(exported) == {"format_version", "exported_at", "entries", "summaries"}
    assert exported["format_version"] == 1
    exported_at = dt.datetime.fromisoformat(exported["exported_at"])
    assert exported_at.utcoffset() == dt.timedelta(0)
    assert before <= exported_at <= after


def test_fr_d1_markdown_export_contains_every_entry(client, alice_token, filled):
    markdown = _markdown(client, alice_token)
    entries = _list(client, alice_token, "/entries")

    section = markdown[markdown.index("## Entries") : markdown.index("## Summaries")]
    positions = []
    for entry in entries:
        block = _entry_markdown(entry)
        assert section.count(block) == 1, block
        positions.append(section.index(block))
    # The entry list's order.
    assert positions == sorted(positions)
    assert "Tags: Public speaking, Testing" in section
    assert "Result/Impact: Two teams adopted the approach." in section
    assert section.count("Result/Impact:") == 2


def test_fr_d1_markdown_export_contains_every_summary(client, alice_token, filled):
    markdown = _markdown(client, alice_token)
    summaries = _list(client, alice_token, "/summaries")

    section = markdown[markdown.index("## Summaries") :]
    positions = []
    for summary in summaries:
        block = f"{_summary_heading(summary)}\n\n{summary['text']}"
        assert section.count(block) == 1, block
        positions.append(section.index(block))
    assert positions == sorted(positions)
    assert (
        "### 2026-04-01 · 2026-01-01 to 2026-03-31 · Categories: Feedback · Tags: Design\n\n"
        "The first quarter.\n"
    ) in section
    assert "Categories: all · Tags: all\n\nThe second quarter." in section
    assert "2026-10-01 to 2026-10-31 · Categories: Learning · Tags: Testing" in section


def test_fr_d1_both_formats_hold_the_same_data(client, alice_token, filled):
    exported = _json(client, alice_token)
    markdown = _markdown(client, alice_token)

    assert markdown.startswith(f"# Winlog export\n\nExported on {exported['exported_at'][:10]}")
    for entry in exported["entries"]:
        assert _entry_markdown(entry) in markdown
    for summary in exported["summaries"]:
        assert f"{_summary_heading(summary)}\n\n{summary['text']}" in markdown
    assert markdown.count("\n### ") == len(exported["entries"]) + len(exported["summaries"])


def test_fr_d1_export_text_is_included_exactly_as_written(client, alice_token, migrated_db, alice):
    text = "# Not a heading\n\n* star _under_ `code` <b>bold</b> \\ [x](y)\n    indented  "
    result = "**Saved** 3 days & <time>"
    _create(
        client,
        alice_token,
        {"text": text, "date": "2026-10-01", "category": "Learning", "result_impact": result},
    )
    _stored_summary(migrated_db, alice, text, dt.datetime(2026, 10, 2, tzinfo=dt.UTC))

    exported = _json(client, alice_token)
    markdown = _markdown(client, alice_token)

    assert exported["entries"][0]["text"] == text
    assert exported["entries"][0]["result_impact"] == result
    assert exported["summaries"][0]["text"] == text
    assert markdown.count(text) == 2
    assert f"Result/Impact: {result}" in markdown


# --- Empty account ------------------------------------------------------------------------


def test_fr_d1_empty_account_gets_empty_lists_in_json(client, alice_token, contract):
    response = _export(client, alice_token, JSON_PATH)

    assert response.status_code == 200
    contract("ExportFile").validate(response.json())
    assert response.json()["entries"] == []
    assert response.json()["summaries"] == []


def test_fr_d1_empty_account_gets_title_and_none_in_markdown(client, alice_token):
    response = _export(client, alice_token, MARKDOWN_PATH)

    assert response.status_code == 200
    date = response.headers["content-disposition"][-14:-4]
    assert response.text == (
        f"# Winlog export\n\nExported on {date}\n\n## Entries\n\nNone\n\n## Summaries\n\nNone\n"
    )


# --- Downloads ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "content_type", "extension"),
    [
        (JSON_PATH, "application/json; charset=utf-8", "json"),
        (MARKDOWN_PATH, "text/markdown; charset=utf-8", "md"),
    ],
)
def test_fr_d1_export_is_a_utf8_file_download_named_after_the_utc_date(
    client, alice_token, filled, path: str, content_type: str, extension: str
):
    before = dt.datetime.now(dt.UTC).date()
    response = _export(client, alice_token, path)
    after = dt.datetime.now(dt.UTC).date()

    assert response.status_code == 200
    assert response.headers["content-type"] == content_type
    names = {f'attachment; filename="winlog-export-{day}.{extension}"' for day in (before, after)}
    assert response.headers["content-disposition"] in names


def test_fr_d1_export_file_names_match_the_export_time(client, alice_token):
    response = _export(client, alice_token, JSON_PATH)

    day = response.json()["exported_at"][:10]
    assert response.headers["content-disposition"] == (
        f'attachment; filename="winlog-export-{day}.json"'
    )


def test_fr_d1_export_cors_response_exposes_the_file_name(client, alice_token):
    response = client.get(
        MARKDOWN_PATH,
        headers={**_headers(alice_token), "Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    assert "content-disposition" in response.headers["access-control-expose-headers"].lower()


def test_fr_d1_export_keeps_non_english_text_unchanged(client, alice_token, migrated_db, alice):
    text = "Ärger mit dem Build 日本語のテキスト 🎉👩‍💻"
    _create(
        client,
        alice_token,
        {
            "text": text,
            "date": "2026-10-01",
            "category": "Feedback",
            "tags": ["Größe", "日本"],
            "result_impact": "Café ✓",
        },
    )
    _stored_summary(
        migrated_db, alice, f"Zusammenfassung: {text}", dt.datetime(2026, 10, 2, tzinfo=dt.UTC)
    )

    json_response = _export(client, alice_token, JSON_PATH)
    markdown_response = _export(client, alice_token, MARKDOWN_PATH)

    raw_json = json_response.content.decode("utf-8")
    assert text in raw_json and "Größe" in raw_json and "Café ✓" in raw_json
    assert "\\u" not in raw_json
    assert json_response.json()["entries"][0]["text"] == text
    assert json_response.json()["summaries"][0]["text"] == f"Zusammenfassung: {text}"
    markdown = markdown_response.content.decode("utf-8")
    assert markdown.count(text) == 2
    assert "Tags: Größe, 日本" in markdown
    assert "Result/Impact: Café ✓" in markdown


# --- What the export leaves out -----------------------------------------------------------


@pytest.mark.parametrize("path", PATHS)
def test_fr_d1_export_contains_no_email_password_hash_token_or_usage(
    client, migrated_db, alice, alice_token, filled, path: str
):
    with migrated_db.connect() as connection:
        password_hash = connection.execute(
            select(User.password_hash).where(User.id == alice)
        ).scalar_one()
        usage = connection.execute(select(func.count()).select_from(AiUsage)).scalar_one()
    assert usage == 1  # the generated summary was counted

    body = _export(client, alice_token, path).content.decode("utf-8")

    assert "alice@example.com" not in body
    assert "example.com" not in body
    assert password_hash not in body
    assert alice_token not in body
    assert hash_token(alice_token) not in body
    assert str(alice) not in body  # not even the user id
    for word in ("email", "password", "token", "request_count", "usage"):
        assert word not in body.lower()


def test_fr_d1_json_export_has_exactly_the_contract_fields(client, alice_token, filled):
    exported = _json(client, alice_token)

    for entry in exported["entries"]:
        assert set(entry) == {
            "id",
            "date",
            "text",
            "category",
            "tags",
            "result_impact",
            "created_at",
            "updated_at",
        }
    for summary in exported["summaries"]:
        assert set(summary) == {"id", "text", "filter", "created_at", "updated_at"}
        assert set(summary["filter"]) == {"period_start", "period_end", "categories", "tags"}


# --- The AI is never called (§8) ----------------------------------------------------------


@pytest.mark.parametrize("failure", ["raise_timeout", "raise_provider_error"])
@pytest.mark.parametrize("path", PATHS)
def test_fr_d1_export_works_when_the_ai_is_unavailable(
    client, migrated_db, alice_token, filled, path: str, failure: str
):
    provider = client.app.state.ai_provider
    assert isinstance(provider, MockProvider)
    getattr(provider, failure)()
    provider.suggest_calls.clear()
    provider.summarise_calls.clear()
    before = _counts(migrated_db)

    response = _export(client, alice_token, path)

    assert response.status_code == 200
    assert "Gave a talk on testing." in response.text
    assert provider.suggest_calls == []
    assert provider.summarise_calls == []
    # Nothing is written: no usage is counted and no data changes.
    assert _counts(migrated_db) == before


@pytest.mark.parametrize("path", PATHS)
def test_fr_d1_export_works_when_the_ai_limits_are_reached(
    test_database_url, migrated_db, alice_token, filled, path: str
):
    limited = TestClient(
        create_app(
            Settings(
                _env_file=None,
                database_url=test_database_url,
                cors_allowed_origins=[ALLOWED_ORIGIN],
                ai_provider="mock",
                ai_daily_requests_global=1,
            )
        )
    )

    # The summary generated for the fixture used up the global limit of 1.
    assert limited.post("/summaries", json=FILTER, headers=_headers(alice_token)).status_code == 429

    response = _export(limited, alice_token, path)

    assert response.status_code == 200
    assert "Gave a talk on testing." in response.text


# --- Authentication and other users (FR-A3) -----------------------------------------------


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("token", [None, "not-a-real-token", "expired"])
def test_fr_a3_export_without_a_valid_token_is_not_authenticated(
    client, migrated_db, alice, filled, contract, path: str, token
):
    if token == "expired":
        token = _token(migrated_db, alice, valid_for=dt.timedelta(seconds=-1))

    response = _export(client, token, path)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert "content-disposition" not in response.headers
    assert "Gave a talk on testing." not in response.text


@pytest.mark.parametrize("path", PATHS)
def test_fr_a3_export_never_contains_another_users_data(
    client, migrated_db, alice, alice_token, filled, path: str
):
    bob = _user(migrated_db, "bob@example.com")
    bob_token = _token(migrated_db, bob)
    bob_entry = _create(
        client,
        bob_token,
        {
            "text": "Bob's secret entry.",
            "date": "2026-10-15",
            "category": "Learning",
            "tags": ["Testing", "Bob tag"],
            "result_impact": "Bob's result.",
        },
    )
    bob_summary = _stored_summary(
        migrated_db, bob, "Bob's secret summary.", dt.datetime(2026, 10, 3, tzinfo=dt.UTC)
    )

    alice_body = _export(client, alice_token, path).text
    bob_body = _export(client, bob_token, path).text

    for leaked in ("Bob's secret entry.", "Bob's result.", "Bob tag", "Bob's secret summary."):
        assert leaked not in alice_body
        assert leaked in bob_body
    assert bob_entry["id"] not in alice_body
    assert bob_summary not in alice_body
    for body in ENTRIES:
        assert body["text"] not in bob_body
    assert "The first quarter." not in bob_body


def test_fr_a3_json_export_of_two_users_splits_their_data(client, migrated_db, alice_token, filled):
    bob = _user(migrated_db, "bob@example.com")
    bob_token = _token(migrated_db, bob)
    _create(
        client, bob_token, {"text": "Bob's entry.", "date": "2026-10-15", "category": "Learning"}
    )

    alice_export = _json(client, alice_token)
    bob_export = _json(client, bob_token)

    assert len(alice_export["entries"]) == len(ENTRIES)
    assert len(alice_export["summaries"]) == 3
    assert [entry["text"] for entry in bob_export["entries"]] == ["Bob's entry."]
    assert bob_export["summaries"] == []


# --- Privacy ------------------------------------------------------------------------------


def test_privacy_export_never_logs_entry_or_summary_text(client, alice_token, filled, caplog):
    with caplog.at_level(logging.DEBUG):
        for path in PATHS:
            assert _export(client, alice_token, path).status_code == 200

    formatter = logging.Formatter()
    logged = "\n".join(formatter.format(record) for record in caplog.records)
    for body in ENTRIES:
        assert body["text"] not in logged
    assert "The first quarter." not in logged
    assert "Mock summary" not in logged
    assert json.dumps(ENTRIES[0]["text"]) not in logged
