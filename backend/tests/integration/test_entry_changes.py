"""Reading, replacing and deleting entries through the API (issue #10).

Operations `getEntry`, `updateEntry` and `deleteEntry` in openapi.yaml. Covers FR-E4 and
FR-A3, and the acceptance criteria in product-spec.md §7.1 and §7.2, against real PostgreSQL.
"""

import datetime as dt
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from app import entries
from app.models import Entry, EntryTag, Summary
from tests.integration.test_entries import (
    VALID,
    _assert_validation_error,
    _create,
    _linked_tags,
    _links,
    _tag,
    _tags,
    _token,
    _user,
)

FULL = {
    "text": "Gave a talk on testing.",
    "date": "2026-10-31",
    "category": "Learning",
    "tags": ["Testing", "Public speaking"],
    "result_impact": "Two teams adopted the approach.",
}
CHANGED = {
    "text": "  Rewrote the talk.\nSecond line  ",
    "date": "2026-11-02",
    "category": "Feedback",
    "tags": ["Public speaking", "Mentoring"],
    "result_impact": "Asked to repeat it.",
}
MISSING_ID = "00000000-0000-4000-8000-000000000000"


# --- Helpers ------------------------------------------------------------------------------


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _get(client: TestClient, token: str | None, entry_id: str):
    return client.get(f"/entries/{entry_id}", headers=_headers(token))


def _put(client: TestClient, token: str | None, entry_id: str, body):
    return client.put(f"/entries/{entry_id}", json=body, headers=_headers(token))


def _put_raw(client: TestClient, token: str, entry_id: str, raw: str):
    """Send the JSON as written, so it can contain escapes such as a lone surrogate."""
    return client.put(
        f"/entries/{entry_id}",
        content=raw.encode("ascii"),
        headers={**_headers(token), "content-type": "application/json"},
    )


def _delete(client: TestClient, token: str | None, entry_id: str):
    return client.delete(f"/entries/{entry_id}", headers=_headers(token))


def _call(client: TestClient, method: str, token: str | None, entry_id: str, body=None):
    if method == "get":
        return _get(client, token, entry_id)
    if method == "put":
        return _put(client, token, entry_id, VALID if body is None else body)
    return _delete(client, token, entry_id)


def _row(engine: Engine, entry_id: str):
    with engine.connect() as connection:
        return connection.execute(
            select(Entry).where(Entry.id == uuid.UUID(entry_id))
        ).one_or_none()


def _snapshot(engine: Engine, entry_id: str) -> tuple:
    """Everything stored about the entry: its row, and its tag links with their tags."""
    return _row(engine, entry_id), _linked_tags(engine, entry_id)


def _tag_list(client: TestClient, token: str) -> list[str]:
    response = client.get("/tags", headers=_headers(token))
    assert response.status_code == 200
    return response.json()["tags"]


def _summary(engine: Engine, user_id: uuid.UUID, text: str, tags: list[str]) -> uuid.UUID:
    """A saved summary, stored directly: no summary endpoints exist yet (#17)."""
    with engine.begin() as connection:
        return connection.execute(
            insert(Summary)
            .values(
                user_id=user_id,
                period_start=dt.date(2026, 10, 1),
                period_end=dt.date(2026, 11, 30),
                filter_categories=["Learning"],
                filter_tags=tags,
                text=text,
            )
            .returning(Summary.id)
        ).scalar_one()


def _summaries(engine: Engine) -> list:
    with engine.connect() as connection:
        return list(connection.execute(select(Summary).order_by(Summary.text)))


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
    """One of Alice's entries, created through the API with every field."""
    response = _create(client, alice_token, FULL)
    assert response.status_code == 201
    return response.json()


# --- Get ----------------------------------------------------------------------------------


def test_fr_e4_get_returns_own_entry_with_its_tags_as_names(
    client: TestClient, migrated_db: Engine, alice_token: str, entry: dict, contract
):
    response = _get(client, alice_token, entry["id"])

    assert response.status_code == 200
    body = response.json()
    contract("Entry").validate(body)
    # Tags have no stored order; they come sorted like the tag list.
    assert body == {**entry, "tags": ["Public speaking", "Testing"]}
    row = _row(migrated_db, entry["id"])
    assert dt.datetime.fromisoformat(body["created_at"]) == row.created_at
    assert dt.datetime.fromisoformat(body["updated_at"]) == row.updated_at


def test_fr_e4_get_returns_tags_with_their_stored_spelling_sorted_ignoring_case(
    client: TestClient, alice: uuid.UUID, alice_token: str, migrated_db: Engine
):
    _tag(migrated_db, alice, "Python")
    created = _create(client, alice_token, {**VALID, "tags": ["rust", "python", "Go", "alpha"]})

    response = _get(client, alice_token, created.json()["id"])

    assert response.json()["tags"] == ["alpha", "Go", "Python", "rust"]


def test_fr_e4_get_entry_without_tags_or_result_impact(
    client: TestClient, alice_token: str, contract
):
    created = _create(client, alice_token, VALID).json()

    response = _get(client, alice_token, created["id"])

    assert response.status_code == 200
    contract("Entry").validate(response.json())
    assert response.json() == created
    assert response.json()["tags"] == []
    assert response.json()["result_impact"] is None


def test_fr_e4_get_accepts_the_id_in_upper_case(client: TestClient, alice_token: str, entry):
    response = _get(client, alice_token, entry["id"].upper())

    assert response.status_code == 200
    assert response.json()["id"] == entry["id"]


def test_fr_a3_get_shows_only_the_owners_tags(
    client: TestClient, migrated_db: Engine, alice_token: str, bob: uuid.UUID, entry: dict
):
    """The schema allows a link to another user's tag; it never shows (as in the tag list)."""
    bobs_tag = _tag(migrated_db, bob, "Bob's secret project")
    with migrated_db.begin() as connection:
        connection.execute(
            insert(EntryTag).values(entry_id=uuid.UUID(entry["id"]), tag_id=bobs_tag)
        )

    response = _get(client, alice_token, entry["id"])

    assert response.json()["tags"] == ["Public speaking", "Testing"]


# --- Update -------------------------------------------------------------------------------


def test_fr_e4_update_replaces_every_field_and_returns_the_entry(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, entry, contract
):
    response = _put(client, alice_token, entry["id"], CHANGED)

    assert response.status_code == 200
    body = response.json()
    contract("Entry").validate(body)
    assert {key: body[key] for key in CHANGED} == CHANGED
    assert body["id"] == entry["id"]
    row = _row(migrated_db, entry["id"])
    assert (row.user_id, row.text, row.date, row.category, row.result_impact) == (
        alice,
        CHANGED["text"],
        dt.date(2026, 11, 2),
        "Feedback",
        "Asked to repeat it.",
    )
    assert dt.datetime.fromisoformat(body["updated_at"]) == row.updated_at
    assert _get(client, alice_token, entry["id"]).json() == {
        **body,
        "tags": ["Mentoring", "Public speaking"],
    }


def test_fr_e4_update_replaces_tags(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, entry
):
    before = {name: tag_id for tag_id, _, name in _tags(migrated_db)}

    response = _put(client, alice_token, entry["id"], CHANGED)

    assert response.json()["tags"] == ["Public speaking", "Mentoring"]
    linked = _linked_tags(migrated_db, entry["id"])
    assert [(user_id, name) for _, user_id, name in linked] == [
        (alice, "Mentoring"),
        (alice, "Public speaking"),
    ]
    # The kept tag is the same record; the new one was created for Alice.
    assert {name: tag_id for tag_id, _, name in linked}["Public speaking"] == (
        before["Public speaking"]
    )
    assert {name for _, _, name in _tags(migrated_db)} == {
        "Mentoring",
        "Public speaking",
        "Testing",
    }


def test_fr_e4_update_reuses_existing_tags_in_any_case_with_their_stored_spelling(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, entry
):
    python = _tag(migrated_db, alice, "Python")

    response = _put(
        client, alice_token, entry["id"], {**FULL, "tags": ["python", " PYTHON ", "testing"]}
    )

    assert response.status_code == 200
    assert response.json()["tags"] == ["Python", "Testing"]
    linked = _linked_tags(migrated_db, entry["id"])
    assert [name for _, _, name in linked] == ["Python", "Testing"]
    assert linked[0][0] == python
    assert len(_tags(migrated_db)) == 3


def test_fr_a3_update_never_links_another_users_tag(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, bob, entry
):
    bobs_rust = _tag(migrated_db, bob, "Rust")

    response = _put(client, alice_token, entry["id"], {**FULL, "tags": ["rust"]})

    assert response.json()["tags"] == ["rust"]
    [(tag_id, user_id, name)] = _linked_tags(migrated_db, entry["id"])
    assert (user_id, name) == (alice, "rust")
    assert tag_id != bobs_rust


@pytest.mark.parametrize("tags", ["missing", []])
def test_fr_e4_update_with_missing_or_empty_tags_removes_all_tags(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, tags
):
    body = {key: value for key, value in FULL.items() if key != "tags"}
    if tags != "missing":
        body["tags"] = tags

    response = _put(client, alice_token, entry["id"], body)

    assert response.status_code == 200
    assert response.json()["tags"] == []
    assert _linked_tags(migrated_db, entry["id"]) == []
    assert _get(client, alice_token, entry["id"]).json()["tags"] == []


def test_fr_e4_update_with_the_same_tags_keeps_them(
    client: TestClient, migrated_db: Engine, alice_token: str, entry
):
    before = _linked_tags(migrated_db, entry["id"])

    response = _put(client, alice_token, entry["id"], FULL)

    assert response.status_code == 200
    assert _linked_tags(migrated_db, entry["id"]) == before


def test_fr_e4_tags_removed_by_update_stay_and_unused_ones_leave_the_tag_list(
    client: TestClient, migrated_db: Engine, alice_token: str, entry
):
    other = _create(client, alice_token, {**VALID, "tags": ["Testing"]}).json()
    stored = _tags(migrated_db)
    assert _tag_list(client, alice_token) == ["Public speaking", "Testing"]

    _put(client, alice_token, entry["id"], {**FULL, "tags": []})

    assert _tags(migrated_db) == stored
    # "Testing" is still used by the other entry; "Public speaking" is used by none.
    assert _tag_list(client, alice_token) == ["Testing"]

    _put(client, alice_token, other["id"], {**VALID, "tags": []})

    assert _tags(migrated_db) == stored
    assert _tag_list(client, alice_token) == []

    _put(client, alice_token, entry["id"], {**FULL, "tags": ["public speaking"]})

    assert _tags(migrated_db) == stored
    assert _tag_list(client, alice_token) == ["Public speaking"]


@pytest.mark.parametrize("result_impact", ["missing", None, "", " ", "  \n\t ", " 　﻿"])
def test_fr_e4_update_with_missing_empty_or_whitespace_result_impact_clears_it(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, result_impact
):
    body = {key: value for key, value in FULL.items() if key != "result_impact"}
    if result_impact != "missing":
        body["result_impact"] = result_impact

    response = _put(client, alice_token, entry["id"], body)

    assert response.status_code == 200
    assert response.json()["result_impact"] is None
    assert _row(migrated_db, entry["id"]).result_impact is None


def test_fr_e4_update_stores_text_and_result_impact_exactly_as_typed(
    client: TestClient, migrated_db: Engine, alice_token: str, entry
):
    text = "  Tabs\tand lines\r\nkept, 日本語 🎉  "
    impact = "  10% faster \n"

    response = _put(
        client, alice_token, entry["id"], {**FULL, "text": text, "result_impact": impact}
    )

    assert (response.json()["text"], response.json()["result_impact"]) == (text, impact)
    row = _row(migrated_db, entry["id"])
    assert (row.text, row.result_impact) == (text, impact)


@pytest.mark.parametrize("body", [CHANGED, FULL], ids=["changed", "identical"])
def test_fr_e4_update_changes_updated_at_and_keeps_created_at(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, body
):
    created_at = dt.datetime.fromisoformat(entry["created_at"])
    updated_at = dt.datetime.fromisoformat(entry["updated_at"])

    response = _put(client, alice_token, entry["id"], body)

    after = response.json()
    assert dt.datetime.fromisoformat(after["created_at"]) == created_at
    assert dt.datetime.fromisoformat(after["updated_at"]) > updated_at
    row = _row(migrated_db, entry["id"])
    assert row.created_at == created_at
    assert row.updated_at == dt.datetime.fromisoformat(after["updated_at"])

    again = _put(client, alice_token, entry["id"], body).json()

    assert dt.datetime.fromisoformat(again["updated_at"]) > dt.datetime.fromisoformat(
        after["updated_at"]
    )
    assert dt.datetime.fromisoformat(again["created_at"]) == created_at


def test_fr_e4_last_of_two_updates_wins(
    client: TestClient, migrated_db: Engine, alice_token: str, entry
):
    first = _put(client, alice_token, entry["id"], CHANGED)
    second = _put(
        client,
        alice_token,
        entry["id"],
        {"text": "Final", "date": "2026-11-05", "category": "Side project", "tags": ["Go"]},
    )

    assert (first.status_code, second.status_code) == (200, 200)
    body = _get(client, alice_token, entry["id"]).json()
    assert {key: body[key] for key in ("text", "date", "category", "tags", "result_impact")} == {
        "text": "Final",
        "date": "2026-11-05",
        "category": "Side project",
        "tags": ["Go"],
        "result_impact": None,
    }
    assert [name for _, _, name in _linked_tags(migrated_db, entry["id"])] == ["Go"]


def test_fr_a3_update_ignores_ids_and_owner_in_the_body(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, bob, entry
):
    other_id = str(uuid.uuid4())

    response = _put(
        client,
        alice_token,
        entry["id"],
        {
            **CHANGED,
            "id": other_id,
            "user_id": str(bob),
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == entry["id"]
    assert response.json()["created_at"] == entry["created_at"]
    row = _row(migrated_db, entry["id"])
    assert row.user_id == alice
    assert row.updated_at.year != 2000
    assert _row(migrated_db, other_id) is None


# Each body fails #9's validation; the fields named are the ones the error lists.
INVALID_UPDATES = [
    ({key: value for key, value in CHANGED.items() if key != "text"}, ["text"]),
    ({**CHANGED, "text": "   \n "}, ["text"]),
    ({**CHANGED, "text": None}, ["text"]),
    ({key: value for key, value in CHANGED.items() if key != "date"}, ["date"]),
    ({**CHANGED, "date": "2026-02-30"}, ["date"]),
    ({**CHANGED, "date": "2026-11-08T00:00:00"}, ["date"]),
    ({key: value for key, value in CHANGED.items() if key != "category"}, ["category"]),
    ({**CHANGED, "category": "achievement"}, ["category"]),
    ({**CHANGED, "tags": ["New tag", "  "]}, ["tags.1"]),
    ({**CHANGED, "tags": "New tag"}, ["tags"]),
    ({**CHANGED, "tags": None}, ["tags"]),
    ({**CHANGED, "result_impact": 5}, ["result_impact"]),
    ({"tags": ["New tag"]}, ["text", "date", "category"]),
]


@pytest.mark.parametrize(("body", "fields"), INVALID_UPDATES)
def test_fr_e4_failed_validation_leaves_the_entry_unchanged_and_creates_no_tag(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, contract, body, fields
):
    before = _snapshot(migrated_db, entry["id"])
    tags = _tags(migrated_db)

    response = _put(client, alice_token, entry["id"], body)

    _assert_validation_error(response, contract, fields)
    assert _snapshot(migrated_db, entry["id"]) == before
    assert _tags(migrated_db) == tags


@pytest.mark.parametrize("character", ["\\u0000", "\\ud800", "\\udfff"])
@pytest.mark.parametrize("field", ["text", "result_impact", "tag"])
def test_fr_e4_nul_or_unpaired_surrogate_in_an_update_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, contract, character, field
):
    values = {"text": "Changed", "result_impact": "Changed impact", "tag": "Brand new"}
    values[field] = f"Before{character}after"
    raw = (
        f'{{"text": "{values["text"]}", "date": "2026-11-02", "category": "Feedback", '
        f'"tags": ["Another new", "{values["tag"]}"], '
        f'"result_impact": "{values["result_impact"]}"}}'
    )
    before = _snapshot(migrated_db, entry["id"])
    tags = _tags(migrated_db)

    response = _put_raw(client, alice_token, entry["id"], raw)

    _assert_validation_error(response, contract, ["tags.1" if field == "tag" else field])
    assert "Before" not in response.text
    assert _snapshot(migrated_db, entry["id"]) == before
    assert _tags(migrated_db) == tags


@pytest.mark.parametrize("raw", ["[]", '"text"', "null", "{", ""])
def test_fr_e4_update_body_must_be_a_json_object(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, contract, raw: str
):
    before = _snapshot(migrated_db, entry["id"])

    response = _put_raw(client, alice_token, entry["id"], raw)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert _snapshot(migrated_db, entry["id"]) == before


def test_fr_e4_failed_update_keeps_the_old_entry_its_tags_and_creates_no_tag(
    test_database_url: str,
    migrated_db: Engine,
    alice: uuid.UUID,
    alice_token: str,
    entry,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
):
    """The entry, its new tags and its new links are saved in one transaction, or not at all."""
    from app.main import create_app
    from app.settings import Settings

    before = _snapshot(migrated_db, entry["id"])
    tags = _tags(migrated_db)

    def link_to_a_missing_tag(session: Session, entry_row, resolved) -> None:
        # The entry is updated, its old links deleted and the new tags created by now.
        assert entry_row.text == "Secret new text" and len(resolved) == 2
        session.add(EntryTag(entry_id=entry_row.id, tag_id=uuid.uuid4()))
        session.flush()  # foreign key violation in the database

    monkeypatch.setattr(entries, "_link_tags", link_to_a_missing_tag)
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=["http://localhost:5173"],
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    caplog.set_level(logging.DEBUG)

    response = _put(
        client,
        alice_token,
        entry["id"],
        {**CHANGED, "text": "Secret new text", "tags": ["Brand new", "Testing"]},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert _snapshot(migrated_db, entry["id"]) == before
    assert _tags(migrated_db) == tags
    assert "Secret new text" not in caplog.text


# --- Delete -------------------------------------------------------------------------------


def test_fr_e4_delete_removes_the_entry_and_its_tag_links_but_keeps_the_tags(
    client: TestClient, migrated_db: Engine, alice_token: str, entry
):
    other = _create(client, alice_token, {**VALID, "tags": ["Testing"]}).json()
    tags = _tags(migrated_db)

    response = _delete(client, alice_token, entry["id"])

    assert response.status_code == 204
    assert response.content == b""
    assert _row(migrated_db, entry["id"]) is None
    assert [entry_id for entry_id, _ in _links(migrated_db)] == [uuid.UUID(other["id"])]
    assert _tags(migrated_db) == tags
    # "Public speaking" is used by no entry any more; "Testing" still is.
    assert _tag_list(client, alice_token) == ["Testing"]
    assert _get(client, alice_token, other["id"]).status_code == 200


def test_fr_e4_deleting_the_same_entry_again_is_not_found(
    client: TestClient, alice_token: str, entry, contract
):
    assert _delete(client, alice_token, entry["id"]).status_code == 204

    _not_found(_delete(client, alice_token, entry["id"]), contract)
    _not_found(_get(client, alice_token, entry["id"]), contract)
    _not_found(_put(client, alice_token, entry["id"], CHANGED), contract)


# --- Missing entries, other users and ids -------------------------------------------------


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_fr_a3_entry_that_does_not_exist_is_not_found(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, contract, method
):
    tags = _tags(migrated_db)

    response = _call(client, method, alice_token, MISSING_ID, {**VALID, "tags": ["Brand new"]})

    _not_found(response, contract)
    assert _tags(migrated_db) == tags
    assert _row(migrated_db, MISSING_ID) is None


def test_fr_a3_cannot_get_other_users_entry(
    client: TestClient, alice_token: str, bob_token: str, entry, contract
):
    response = _get(client, bob_token, entry["id"])

    _not_found(response, contract)
    assert response.json() == _get(client, bob_token, MISSING_ID).json()
    assert "Gave a talk" not in response.text


def test_fr_a3_cannot_update_other_users_entry(
    client: TestClient, migrated_db: Engine, bob_token: str, entry, contract
):
    before = _snapshot(migrated_db, entry["id"])
    tags = _tags(migrated_db)

    response = _put(client, bob_token, entry["id"], {**CHANGED, "tags": ["Bob's new tag"]})

    _not_found(response, contract)
    assert response.json() == _put(client, bob_token, MISSING_ID, CHANGED).json()
    assert _snapshot(migrated_db, entry["id"]) == before
    # Neither Alice nor Bob got a new tag.
    assert _tags(migrated_db) == tags


def test_fr_a3_cannot_delete_other_users_entry(
    client: TestClient, migrated_db: Engine, alice_token: str, bob_token: str, entry, contract
):
    before = _snapshot(migrated_db, entry["id"])

    response = _delete(client, bob_token, entry["id"])

    _not_found(response, contract)
    assert response.json() == _delete(client, bob_token, MISSING_ID).json()
    assert _snapshot(migrated_db, entry["id"]) == before
    assert _get(client, alice_token, entry["id"]).status_code == 200


def test_fr_a3_own_entries_still_work_next_to_another_users(
    client: TestClient, migrated_db: Engine, alice_token: str, bob_token: str, entry
):
    bobs = _create(client, bob_token, {**VALID, "tags": ["Testing"]}).json()

    assert _put(client, alice_token, entry["id"], CHANGED).status_code == 200
    assert _delete(client, alice_token, entry["id"]).status_code == 204
    assert _get(client, bob_token, bobs["id"]).json() == bobs


@pytest.mark.parametrize("method", ["get", "put", "delete"])
@pytest.mark.parametrize(
    "entry_id",
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
        "%EF%BC%90" * 8 + "-0000-4000-8000-000000000000",
    ],
)
def test_fr_a3_id_in_the_wrong_format_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, contract, method, entry_id
):
    before = _snapshot(migrated_db, entry["id"])

    response = _call(client, method, alice_token, entry_id)

    _assert_validation_error(response, contract, ["entryId"])
    assert _snapshot(migrated_db, entry["id"]) == before


def test_fr_a3_wrong_id_format_of_an_existing_entry_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, entry, contract
):
    """Another spelling of a real entry's id is not accepted, even for its owner."""
    compact = entry["id"].replace("-", "")

    _assert_validation_error(_delete(client, alice_token, compact), contract, ["entryId"])
    assert _row(migrated_db, entry["id"]) is not None


# --- Summaries ----------------------------------------------------------------------------


def test_fr_e4_editing_or_deleting_an_entry_never_changes_a_saved_summary(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, entry
):
    """§7.2: summaries keep their text and filter. They have no link to entries."""
    _summary(migrated_db, alice, "Summary A: gave a talk on testing.", ["Testing"])
    _summary(migrated_db, alice, "Summary B: public speaking.", ["Public speaking", "Testing"])
    before = _summaries(migrated_db)
    assert len(before) == 2

    assert _put(client, alice_token, entry["id"], {**CHANGED, "tags": []}).status_code == 200
    assert _summaries(migrated_db) == before

    assert _delete(client, alice_token, entry["id"]).status_code == 204
    assert _summaries(migrated_db) == before


# --- Authentication -----------------------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "put", "delete"])
@pytest.mark.parametrize("token", [None, "not-a-real-token", "expired"])
@pytest.mark.parametrize("which", ["own", "missing", "wrong format"])
def test_fr_a3_without_a_valid_token_all_three_are_not_authenticated(
    client: TestClient,
    migrated_db: Engine,
    alice: uuid.UUID,
    entry,
    contract,
    method,
    token,
    which,
):
    if token == "expired":
        token = _token(migrated_db, alice, valid_for=dt.timedelta(seconds=-1))
    entry_id = {"own": entry["id"], "missing": MISSING_ID, "wrong format": "nope"}[which]
    before = _snapshot(migrated_db, entry["id"])
    tags = _tags(migrated_db)

    response = _call(client, method, token, entry_id, {**CHANGED, "tags": ["Brand new"]})

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "Gave a talk" not in response.text
    assert _snapshot(migrated_db, entry["id"]) == before
    assert _tags(migrated_db) == tags


# --- Privacy ------------------------------------------------------------------------------


def test_fr_e4_entry_text_is_never_logged(
    client: TestClient, alice_token: str, bob_token: str, entry, caplog
):
    caplog.set_level(logging.DEBUG)
    text = "Confidential edited text"
    impact = "Confidential edited impact"
    body = {**CHANGED, "text": text, "result_impact": impact}

    _put(client, alice_token, entry["id"], body)
    _get(client, alice_token, entry["id"])
    _put(client, alice_token, entry["id"], {**body, "date": "2026-02-30"})
    _put(client, bob_token, entry["id"], body)
    _put(client, None, entry["id"], body)
    _delete(client, alice_token, entry["id"])

    assert text not in caplog.text
    assert impact not in caplog.text
