"""Listing, reading, editing and deleting saved summaries through the API (issue #18).

Operations `listSummaries`, `getSummary`, `updateSummary` and `deleteSummary` in openapi.yaml.
Covers FR-R5 and FR-A3, and the acceptance criteria in product-spec.md §7.4, against real
PostgreSQL. Summaries are generated with the mock AI provider or stored directly; no test
calls a real AI.
"""

import datetime as dt
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select

from app.models import Entry, EntryTag, Summary, Tag
from tests.integration.test_entries import (
    NOT_JSON,
    _assert_validation_error,
    _create,
    _token,
    _user,
)

MISSING_ID = "00000000-0000-4000-8000-000000000000"
FILTER = {
    "period_start": "2026-10-01",
    "period_end": "2026-10-31",
    "categories": ["Learning", "Achievement"],
    "tags": ["Testing", "Public speaking"],
}
ENTRY = {
    "text": "Gave a talk on testing.",
    "date": "2026-10-15",
    "category": "Learning",
    "tags": ["Testing", "Public speaking"],
    "result_impact": "Two teams adopted the approach.",
}


# --- Helpers ------------------------------------------------------------------------------


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _list(client: TestClient, token: str | None):
    return client.get("/summaries", headers=_headers(token))


def _get(client: TestClient, token: str | None, summary_id: str):
    return client.get(f"/summaries/{summary_id}", headers=_headers(token))


def _patch(client: TestClient, token: str | None, summary_id: str, body):
    return client.patch(f"/summaries/{summary_id}", json=body, headers=_headers(token))


def _patch_bytes(client: TestClient, token: str | None, summary_id: str, body: bytes):
    return client.patch(
        f"/summaries/{summary_id}",
        content=body,
        headers={**_headers(token), "content-type": "application/json"},
    )


def _delete(client: TestClient, token: str | None, summary_id: str):
    return client.delete(f"/summaries/{summary_id}", headers=_headers(token))


def _call(client: TestClient, method: str, token: str | None, summary_id: str, body=None):
    if method == "get":
        return _get(client, token, summary_id)
    if method == "patch":
        return _patch(client, token, summary_id, {"text": "Changed."} if body is None else body)
    return _delete(client, token, summary_id)


def _get_entry(client: TestClient, token: str, entry_id: str) -> dict:
    response = client.get(f"/entries/{entry_id}", headers=_headers(token))
    assert response.status_code == 200
    return response.json()


def _generate(client: TestClient, token: str, body: dict | None = None) -> dict:
    """A summary generated through #17's endpoint with the mock AI provider."""
    response = client.post("/summaries", json=body or FILTER, headers=_headers(token))
    assert response.status_code == 201
    return response.json()


def _stored(
    engine: Engine,
    user_id: uuid.UUID,
    text: str,
    created_at: dt.datetime | None = None,
    tags: list[str] | None = None,
) -> str:
    """A summary stored directly, optionally with a chosen creation time."""
    values = {
        "user_id": user_id,
        "period_start": dt.date(2026, 1, 1),
        "period_end": dt.date(2026, 3, 31),
        "filter_categories": ["Feedback"],
        "filter_tags": tags or [],
        "text": text,
    }
    if created_at is not None:
        values |= {"created_at": created_at, "updated_at": created_at}
    with engine.begin() as connection:
        return str(
            connection.execute(insert(Summary).values(values).returning(Summary.id)).one().id
        )


def _row(engine: Engine, summary_id: str):
    with engine.connect() as connection:
        return connection.execute(
            select(Summary).where(Summary.id == uuid.UUID(summary_id))
        ).one_or_none()


def _summaries(engine: Engine) -> list:
    with engine.connect() as connection:
        return list(connection.execute(select(Summary).order_by(Summary.id)))


def _entry_state(engine: Engine) -> tuple:
    """Every entry, tag and tag link, in a fixed order."""
    with engine.connect() as connection:
        return (
            list(connection.execute(select(Entry).order_by(Entry.id))),
            list(connection.execute(select(Tag).order_by(Tag.id))),
            list(connection.execute(select(EntryTag).order_by(EntryTag.entry_id, EntryTag.tag_id))),
        )


def _state(engine: Engine) -> tuple:
    return _summaries(engine), _entry_state(engine)


def _not_found(response, contract) -> None:
    assert response.status_code == 404
    contract("Error").validate(response.json())
    assert response.json() == {"code": "not_found", "message": "Not found."}


@pytest.fixture
def alice(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db, "alice@example.com")


@pytest.fixture
def alice_token(migrated_db: Engine, alice: uuid.UUID) -> str:
    return _token(migrated_db, alice)


@pytest.fixture
def bob(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db, "bob@example.com")


@pytest.fixture
def bob_token(migrated_db: Engine, bob: uuid.UUID) -> str:
    return _token(migrated_db, bob)


@pytest.fixture
def entry(client: TestClient, alice_token: str) -> dict:
    """One of Alice's entries, created through the API, matching FILTER."""
    response = _create(client, alice_token, ENTRY)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def summary(client: TestClient, alice_token: str, entry) -> dict:
    """One of Alice's summaries, generated through the API from her entry."""
    return _generate(client, alice_token)


# --- List ---------------------------------------------------------------------------------


def test_fr_r5_list_returns_all_own_summaries_newest_first(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, contract
):
    base = dt.datetime(2026, 11, 1, 12, tzinfo=dt.UTC)
    middle = _stored(migrated_db, alice, "Middle", base, tags=["Testing"])
    oldest = _stored(migrated_db, alice, "Oldest", base - dt.timedelta(days=30))
    newest = _stored(migrated_db, alice, "Newest", base + dt.timedelta(seconds=1))

    response = _list(client, alice_token)

    assert response.status_code == 200
    contract("SummaryList").validate(response.json())
    listed = response.json()["summaries"]
    assert [item["id"] for item in listed] == [newest, middle, oldest]
    assert [item["text"] for item in listed] == ["Newest", "Middle", "Oldest"]
    assert listed[1]["filter"] == {
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "categories": ["Feedback"],
        "tags": ["Testing"],
    }
    assert dt.datetime.fromisoformat(listed[1]["created_at"]) == base


def test_fr_r5_list_shows_generated_summaries_newest_first_with_their_filter(
    client: TestClient, alice_token: str, entry, contract
):
    first = _generate(client, alice_token)
    second = _generate(client, alice_token, {**FILTER, "categories": [], "tags": []})

    listed = _list(client, alice_token).json()["summaries"]

    assert listed == [second, first]
    assert listed[1]["filter"] == FILTER
    for item in listed:
        contract("Summary").validate(item)


def test_fr_r5_list_without_summaries_is_empty(client: TestClient, alice_token: str, entry):
    response = _list(client, alice_token)

    assert response.status_code == 200
    assert response.json() == {"summaries": []}


def test_fr_r5_list_is_not_paginated(client: TestClient, migrated_db: Engine, alice, alice_token):
    for number in range(60):
        _stored(migrated_db, alice, f"Summary {number}")

    response = client.get("/summaries?limit=5&page=2", headers=_headers(alice_token))

    assert response.status_code == 200
    assert len(response.json()["summaries"]) == 60


def test_fr_a3_list_never_shows_other_users_summaries(
    client: TestClient, migrated_db: Engine, alice, alice_token: str, bob, bob_token: str
):
    alices = _stored(migrated_db, alice, "Alice's summary")
    _stored(migrated_db, bob, "Bob's summary")

    assert [item["id"] for item in _list(client, alice_token).json()["summaries"]] == [alices]
    assert [item["text"] for item in _list(client, bob_token).json()["summaries"]] == [
        "Bob's summary"
    ]


# --- Get ----------------------------------------------------------------------------------


def test_fr_r5_get_returns_own_summary(client: TestClient, alice_token: str, summary, contract):
    response = _get(client, alice_token, summary["id"])

    assert response.status_code == 200
    contract("Summary").validate(response.json())
    assert response.json() == summary
    assert response.json()["filter"] == FILTER


def test_fr_r5_get_accepts_the_id_in_upper_case(client: TestClient, alice_token: str, summary):
    response = _get(client, alice_token, summary["id"].upper())

    assert response.status_code == 200
    assert response.json() == summary


# --- Update -------------------------------------------------------------------------------


def test_fr_r5_edit_changes_only_text(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, contract
):
    before = _row(migrated_db, summary["id"])

    response = _patch(
        client,
        alice_token,
        summary["id"],
        {
            "text": "My edited summary.",
            "filter": {
                "period_start": "2020-01-01",
                "period_end": "2020-12-31",
                "categories": ["Feedback"],
                "tags": ["Other"],
            },
            "period_start": "2020-01-01",
            "filter_tags": ["Other"],
        },
    )

    assert response.status_code == 200
    contract("Summary").validate(response.json())
    body = response.json()
    assert body["text"] == "My edited summary."
    assert body["filter"] == summary["filter"] == FILTER
    assert (body["id"], body["created_at"]) == (summary["id"], summary["created_at"])
    after = _row(migrated_db, summary["id"])._asdict()
    assert after.pop("text") == "My edited summary."
    assert after.pop("updated_at") > before._asdict().pop("updated_at")
    unchanged = {k: v for k, v in before._asdict().items() if k not in {"text", "updated_at"}}
    assert after == unchanged
    assert (after["period_start"], after["filter_tags"]) == (
        dt.date(2026, 10, 1),
        ["Testing", "Public speaking"],
    )
    assert _get(client, alice_token, summary["id"]).json() == body


@pytest.mark.parametrize(
    "text",
    [
        "  Leading and trailing spaces  ",
        "Line one\n\n- point\n\tindented\r\n",
        "Ünïcödé, emoji \U0001f389 and 漢字",
        "x",
    ],
)
def test_fr_r5_edit_stores_text_exactly_as_typed(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, text: str
):
    response = _patch(client, alice_token, summary["id"], {"text": text})

    assert response.status_code == 200
    assert response.json()["text"] == text
    assert _row(migrated_db, summary["id"]).text == text
    assert _get(client, alice_token, summary["id"]).json()["text"] == text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"filter": FILTER},
        {"text": ""},
        {"text": "   \n\t "},
        {"text": " 　"},
        {"text": None},
        {"text": 5},
        {"text": "Has a NUL\x00"},
    ],
)
def test_fr_r5_missing_or_blank_text_is_a_validation_error_and_changes_nothing(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, contract, body
):
    before = _state(migrated_db)

    response = _patch(client, alice_token, summary["id"], body)

    _assert_validation_error(response, contract, ["text"])
    assert _state(migrated_db) == before


@pytest.mark.parametrize("body", [*NOT_JSON[:3], b'["text"]', b'"text"'])
def test_fr_r5_edit_body_must_be_a_json_object(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, contract, body: bytes
):
    before = _state(migrated_db)

    response = _patch_bytes(client, alice_token, summary["id"], body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert _state(migrated_db) == before


@pytest.mark.parametrize("text", ["A new text.", None], ids=["changed", "identical"])
def test_fr_r5_edit_changes_updated_at_and_keeps_created_at(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, text
):
    text = text or summary["text"]
    created_at = dt.datetime.fromisoformat(summary["created_at"])
    updated_at = dt.datetime.fromisoformat(summary["updated_at"])

    after = _patch(client, alice_token, summary["id"], {"text": text}).json()

    assert dt.datetime.fromisoformat(after["created_at"]) == created_at
    assert dt.datetime.fromisoformat(after["updated_at"]) > updated_at
    row = _row(migrated_db, summary["id"])
    assert row.created_at == created_at
    assert row.updated_at == dt.datetime.fromisoformat(after["updated_at"])

    again = _patch(client, alice_token, summary["id"], {"text": text}).json()

    assert dt.datetime.fromisoformat(again["updated_at"]) > dt.datetime.fromisoformat(
        after["updated_at"]
    )
    assert dt.datetime.fromisoformat(again["created_at"]) == created_at


def test_fr_r5_last_of_two_edits_wins(
    client: TestClient, migrated_db: Engine, alice_token: str, summary
):
    first = _patch(client, alice_token, summary["id"], {"text": "First edit."})
    second = _patch(client, alice_token, summary["id"], {"text": "Second edit."})

    assert (first.status_code, second.status_code) == (200, 200)
    assert _get(client, alice_token, summary["id"]).json()["text"] == "Second edit."
    assert _row(migrated_db, summary["id"]).text == "Second edit."
    assert _list(client, alice_token).json()["summaries"][0]["text"] == "Second edit."


def test_fr_r5_edit_never_changes_entries(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, summary
):
    """§7.4: editing a summary changes no entry, no tag and no tag link."""
    before = _entry_state(migrated_db)
    entry_before = _get_entry(client, alice_token, entry["id"])
    assert len(before[0]) == 1

    response = _patch(
        client,
        alice_token,
        summary["id"],
        {"text": "Rewrote everything.", "tags": ["Brand new"], "entries": [entry["id"]]},
    )

    assert response.status_code == 200
    assert _entry_state(migrated_db) == before
    assert _get_entry(client, alice_token, entry["id"]) == entry_before


def test_fr_a3_edit_ignores_ids_and_owner_in_the_body(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, bob, summary
):
    other_id = str(uuid.uuid4())

    response = _patch(
        client,
        alice_token,
        summary["id"],
        {
            "text": "Edited.",
            "id": other_id,
            "user_id": str(bob),
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == summary["id"]
    assert response.json()["created_at"] == summary["created_at"]
    row = _row(migrated_db, summary["id"])
    assert row.user_id == alice
    assert row.updated_at.year != 2000
    assert _row(migrated_db, other_id) is None


# --- Delete -------------------------------------------------------------------------------


def test_fr_r5_delete_removes_the_summary_and_keeps_the_entries(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, summary
):
    other = _generate(client, alice_token)
    entries_before = _entry_state(migrated_db)
    entry_before = _get_entry(client, alice_token, entry["id"])

    response = _delete(client, alice_token, summary["id"])

    assert response.status_code == 204
    assert response.content == b""
    assert _row(migrated_db, summary["id"]) is None
    assert [item["id"] for item in _list(client, alice_token).json()["summaries"]] == [other["id"]]
    assert _get(client, alice_token, other["id"]).json() == other
    assert _entry_state(migrated_db) == entries_before
    assert _get_entry(client, alice_token, entry["id"]) == entry_before


def test_fr_r5_deleting_the_same_summary_again_is_not_found(
    client: TestClient, alice_token: str, summary, contract
):
    assert _delete(client, alice_token, summary["id"]).status_code == 204

    _not_found(_delete(client, alice_token, summary["id"]), contract)
    _not_found(_get(client, alice_token, summary["id"]), contract)
    _not_found(_patch(client, alice_token, summary["id"], {"text": "Back?"}), contract)


# --- Missing summaries, other users and ids -----------------------------------------------


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_fr_a3_summary_that_does_not_exist_is_not_found(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, contract, method
):
    before = _state(migrated_db)

    response = _call(client, method, alice_token, MISSING_ID)

    _not_found(response, contract)
    assert _state(migrated_db) == before
    assert _row(migrated_db, MISSING_ID) is None


def test_fr_a3_cannot_read_other_users_summary(
    client: TestClient, bob_token: str, summary, contract
):
    response = _get(client, bob_token, summary["id"])

    _not_found(response, contract)
    assert response.json() == _get(client, bob_token, MISSING_ID).json()
    assert summary["text"] not in response.text


def test_fr_a3_cannot_edit_other_users_summary(
    client: TestClient, migrated_db: Engine, alice_token: str, bob_token: str, summary, contract
):
    before = _state(migrated_db)

    response = _patch(client, bob_token, summary["id"], {"text": "Bob was here."})

    _not_found(response, contract)
    assert response.json() == _patch(client, bob_token, MISSING_ID, {"text": "x"}).json()
    assert _state(migrated_db) == before
    assert _get(client, alice_token, summary["id"]).json() == summary


def test_fr_a3_cannot_delete_other_users_summary(
    client: TestClient, migrated_db: Engine, alice_token: str, bob_token: str, summary, contract
):
    before = _state(migrated_db)

    response = _delete(client, bob_token, summary["id"])

    _not_found(response, contract)
    assert response.json() == _delete(client, bob_token, MISSING_ID).json()
    assert _state(migrated_db) == before
    assert _get(client, alice_token, summary["id"]).json() == summary


def test_fr_a3_own_summaries_still_work_next_to_another_users(
    client: TestClient, migrated_db: Engine, bob, alice_token: str, bob_token: str, summary
):
    bobs = _stored(migrated_db, bob, "Bob's summary")
    bobs_before = _get(client, bob_token, bobs).json()

    assert _patch(client, alice_token, summary["id"], {"text": "Mine."}).status_code == 200
    assert _delete(client, alice_token, summary["id"]).status_code == 204
    assert _get(client, bob_token, bobs).json() == bobs_before


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
@pytest.mark.parametrize(
    "summary_id",
    [
        "not-a-uuid",
        "123",
        "00000000-0000-4000-8000-00000000000",
        "00000000-0000-4000-8000-0000000000000",
        "00000000000040008000000000000000",
        "{00000000-0000-4000-8000-000000000000}",
        "urn:uuid:00000000-0000-4000-8000-000000000000",
        "0000000g-0000-4000-8000-000000000000",
        "00000000-0000-4000-8000-000000000000%20",
        "%2000000000-0000-4000-8000-000000000000",
    ],
)
def test_fr_a3_id_in_the_wrong_format_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, contract, method, summary_id
):
    before = _state(migrated_db)

    response = _call(client, method, alice_token, summary_id)

    _assert_validation_error(response, contract, ["summaryId"])
    assert _state(migrated_db) == before


def test_fr_a3_wrong_id_format_of_an_existing_summary_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, summary, contract
):
    """Another spelling of a real summary's id is not accepted, even for its owner."""
    compact = summary["id"].replace("-", "")

    _assert_validation_error(_delete(client, alice_token, compact), contract, ["summaryId"])
    assert _row(migrated_db, summary["id"]) is not None


# --- Authentication -----------------------------------------------------------------------


@pytest.mark.parametrize("method", ["list", "get", "patch", "delete"])
@pytest.mark.parametrize("token", [None, "not-a-real-token", "expired"])
@pytest.mark.parametrize("which", ["own", "missing", "wrong format"])
def test_fr_a3_without_a_valid_token_all_four_are_not_authenticated(
    client: TestClient,
    migrated_db: Engine,
    alice: uuid.UUID,
    summary,
    contract,
    method,
    token,
    which,
):
    if token == "expired":
        token = _token(migrated_db, alice, valid_for=dt.timedelta(seconds=-1))
    summary_id = {"own": summary["id"], "missing": MISSING_ID, "wrong format": "nope"}[which]
    before = _state(migrated_db)

    if method == "list":
        response = _list(client, token)
    else:
        response = _call(client, method, token, summary_id, {"text": "Changed by a stranger."})

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert summary["text"] not in response.text
    assert _state(migrated_db) == before


@pytest.mark.parametrize("body", [*NOT_JSON, b"{}", b'{"text": ""}'])
@pytest.mark.parametrize("token", [None, "not-a-real-token", "expired"])
def test_fr_a3_edit_with_an_invalid_body_and_no_valid_token_is_not_authenticated(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, summary, contract, token, body
):
    """The token is checked first, although FastAPI reads the body before any dependency."""
    if token == "expired":
        token = _token(migrated_db, alice, valid_for=dt.timedelta(seconds=-1))
    before = _state(migrated_db)

    response = _patch_bytes(client, token, summary["id"], body)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert _state(migrated_db) == before


# --- Privacy ------------------------------------------------------------------------------


def test_privacy_summary_text_is_never_logged(
    client: TestClient,
    migrated_db: Engine,
    alice,
    alice_token: str,
    bob_token: str,
    summary,
    caplog,
):
    caplog.set_level(logging.DEBUG)
    stored = "Confidential stored summary text"
    edited = "Confidential edited summary text"
    other = _stored(migrated_db, alice, stored)

    _list(client, alice_token)
    _get(client, alice_token, other)
    _patch(client, alice_token, summary["id"], {"text": edited})
    _patch(client, alice_token, summary["id"], {"text": edited + "\x00"})
    _patch(client, alice_token, "not-a-uuid", {"text": edited})
    _patch(client, bob_token, summary["id"], {"text": edited})
    _patch(client, None, summary["id"], {"text": edited})
    _get(client, bob_token, other)
    _delete(client, alice_token, other)

    for text in (stored, edited, summary["text"]):
        assert text not in caplog.text
