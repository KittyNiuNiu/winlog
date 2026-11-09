"""Creating entries through the API (issue #9, `createEntry` in openapi.yaml).

Covers FR-E1, FR-E2, FR-E3 and FR-A3, and the acceptance criteria in product-spec.md §7.2
and §7.3, against real PostgreSQL.
"""

import datetime as dt
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import entries
from app.auth import hash_token
from app.models import Entry, EntryTag, Tag, Token, User

DATE = "2026-11-08"
VALID = {"text": "Shipped the release.", "date": DATE, "category": "Achievement"}


# --- Helpers ------------------------------------------------------------------------------


def _user(engine: Engine, email: str) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(User).values(email=email, password_hash="hash").returning(User.id)
        ).scalar_one()


def _token(engine: Engine, user_id: uuid.UUID, valid_for: dt.timedelta | None = None) -> str:
    """A login for the user, without going through the password check."""
    token = f"test-token-{uuid.uuid4()}"
    with engine.begin() as connection:
        connection.execute(
            insert(Token).values(
                user_id=user_id,
                token_hash=hash_token(token),
                expires_at=dt.datetime.now(dt.UTC) + (valid_for or dt.timedelta(days=1)),
            )
        )
    return token


def _tag(engine: Engine, user_id: uuid.UUID, name: str) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(Tag).values(user_id=user_id, name=name).returning(Tag.id)
        ).scalar_one()


def _create(client: TestClient, token: str | None, body: dict):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/entries", json=body, headers=headers)


def _create_raw(client: TestClient, token: str, raw: str):
    """Send the JSON as written, so it can contain escapes such as a lone surrogate."""
    return client.post(
        "/entries",
        content=raw.encode("ascii"),
        headers={"Authorization": f"Bearer {token}", "content-type": "application/json"},
    )


def _entries(engine: Engine) -> list:
    with engine.connect() as connection:
        return list(connection.execute(select(Entry).order_by(Entry.created_at)))


def _tags(engine: Engine) -> list[tuple]:
    """(id, user_id, name) of every stored tag."""
    with engine.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(select(Tag.id, Tag.user_id, Tag.name).order_by(Tag.name))
        ]


def _links(engine: Engine) -> list[tuple]:
    with engine.connect() as connection:
        return [
            tuple(row) for row in connection.execute(select(EntryTag.entry_id, EntryTag.tag_id))
        ]


def _linked_tags(engine: Engine, entry_id: str) -> list[tuple]:
    """(id, user_id, name) of the tags linked to the entry, sorted by name."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(Tag.id, Tag.user_id, Tag.name)
            .join(EntryTag, EntryTag.tag_id == Tag.id)
            .where(EntryTag.entry_id == uuid.UUID(entry_id))
            .order_by(Tag.name)
        )
        return [tuple(row) for row in rows]


def _assert_validation_error(response, contract, fields: list[str]) -> None:
    assert response.status_code == 422
    body = response.json()
    contract("Error").validate(body)
    assert body["code"] == "validation_failed"
    assert [item["field"] for item in body["fields"]] == fields


@pytest.fixture
def alice(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db, "alice@example.com")


@pytest.fixture
def alice_token(migrated_db: Engine, alice: uuid.UUID) -> str:
    return _token(migrated_db, alice)


# --- Saving -------------------------------------------------------------------------------


def test_fr_e1_valid_request_creates_an_entry_for_the_user(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, contract
):
    response = _create(client, alice_token, VALID)

    assert response.status_code == 201
    body = response.json()
    contract("Entry").validate(body)
    [row] = _entries(migrated_db)
    assert body == {
        "id": str(row.id),
        "date": DATE,
        "text": "Shipped the release.",
        "category": "Achievement",
        "tags": [],
        "result_impact": None,
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }
    assert row.user_id == alice
    assert row.date == dt.date(2026, 11, 8)
    assert row.category == "Achievement"
    assert dt.datetime.fromisoformat(body["created_at"]) == row.created_at
    assert dt.datetime.fromisoformat(body["updated_at"]) == row.updated_at


@pytest.mark.parametrize("category", ["Achievement", "Learning", "Feedback", "Side project"])
def test_fr_e2_each_of_the_four_categories_can_be_saved(
    client: TestClient, migrated_db: Engine, alice_token: str, category: str
):
    response = _create(client, alice_token, {**VALID, "category": category})

    assert response.status_code == 201
    assert response.json()["category"] == category
    assert [row.category for row in _entries(migrated_db)] == [category]


def test_fr_e1_one_text_creates_one_entry(
    client: TestClient, migrated_db: Engine, alice_token: str
):
    text = (
        "Three wins this week:\n"
        "- Shipped the billing release.\n"
        "- Fixed the login bug.\n"
        "- Mentored a new colleague.\n"
        "\n"
        "Second paragraph: also gave a talk on testing.\n"
        "\n"
        "1. One more achievement\n"
        "2. And another one"
    )

    response = _create(client, alice_token, {**VALID, "text": text})

    assert response.status_code == 201
    [row] = _entries(migrated_db)
    assert row.text == text
    assert response.json()["id"] == str(row.id)


def test_fr_e1_each_request_creates_its_own_entry(
    client: TestClient, migrated_db: Engine, alice_token: str
):
    first = _create(client, alice_token, VALID).json()
    second = _create(client, alice_token, VALID).json()

    assert first["id"] != second["id"]
    assert len(_entries(migrated_db)) == 2


def test_fr_a3_entry_belongs_to_the_token_owner_and_a_user_id_in_the_body_is_ignored(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    bob = _user(migrated_db, "bob@example.com")
    forced_id = str(uuid.uuid4())

    response = _create(
        client,
        alice_token,
        {**VALID, "user_id": str(bob), "id": forced_id, "created_at": "2000-01-01T00:00:00Z"},
    )

    assert response.status_code == 201
    [row] = _entries(migrated_db)
    assert row.user_id == alice
    assert str(row.id) != forced_id
    assert response.json()["id"] == str(row.id)
    assert row.created_at.year != 2000


@pytest.mark.parametrize(
    "text",
    [
        "  Leading and trailing spaces  ",
        "\tTabs\tinside\t",
        "Line one\nLine two\n\n\nAfter blank lines\n",
        "Windows line ends\r\nsecond line\r\n",
        "Unicode: Größe, naïve, 日本語, emoji 🎉, combining é",
        "Emoji 😀 outside the Basic Multilingual Plane",
        "   Non-breaking space kept  ",
        "<b>Markup</b> & 'quotes' \"kept\" \\ backslash",
    ],
)
def test_fr_e1_text_is_stored_exactly_as_typed(
    client: TestClient, migrated_db: Engine, alice_token: str, text: str
):
    response = _create(client, alice_token, {**VALID, "text": text})

    assert response.status_code == 201
    assert response.json()["text"] == text
    [row] = _entries(migrated_db)
    assert row.text == text


def test_fr_e1_escaped_surrogate_pair_is_one_valid_character(
    client: TestClient, migrated_db: Engine, alice_token: str
):
    raw = '{"text": "Party \\ud83c\\udf89", "date": "2026-11-08", "category": "Achievement"}'

    response = _create_raw(client, alice_token, raw)

    assert response.status_code == 201
    assert response.json()["text"] == "Party \U0001f389"
    [row] = _entries(migrated_db)
    assert row.text == "Party \U0001f389"


@pytest.mark.parametrize(
    "result_impact",
    ["missing", None, "", " ", "   \n\t  ", " 　", "﻿"],
)
def test_fr_e2_result_impact_missing_empty_or_whitespace_is_stored_as_null(
    client: TestClient, migrated_db: Engine, alice_token: str, result_impact
):
    body = dict(VALID)
    if result_impact != "missing":
        body["result_impact"] = result_impact

    response = _create(client, alice_token, body)

    assert response.status_code == 201
    assert response.json()["result_impact"] is None
    [row] = _entries(migrated_db)
    assert row.result_impact is None


@pytest.mark.parametrize("result_impact", ["Saved 2 hours a week.", "  Cut costs by 10%.\n"])
def test_fr_e2_result_impact_is_stored_as_typed(
    client: TestClient, migrated_db: Engine, alice_token: str, result_impact: str
):
    response = _create(client, alice_token, {**VALID, "result_impact": result_impact})

    assert response.status_code == 201
    assert response.json()["result_impact"] == result_impact
    [row] = _entries(migrated_db)
    assert row.result_impact == result_impact


def test_fr_e2_entry_is_saved_without_an_ai_provider(
    test_database_url: str,
    migrated_db: Engine,
    alice_token: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """§7.2: an entry can be saved without AI suggestions, with no AI provider configured."""
    import os

    from app.main import create_app
    from app.settings import Settings

    for name in list(os.environ):
        if name.startswith(("AI_", "ANTHROPIC", "OPENAI")):
            monkeypatch.delenv(name)
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=["http://localhost:5173"],
        ai_provider="mock",
    )
    client = TestClient(create_app(settings))

    response = _create(client, alice_token, {**VALID, "tags": ["Python"]})

    assert response.status_code == 201
    assert len(_entries(migrated_db)) == 1


def test_fr_e2_entry_with_every_field_is_saved(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, contract
):
    body = {
        "text": "Gave a talk on testing.",
        "date": "2026-10-31",
        "category": "Learning",
        "tags": ["Testing", "Public speaking"],
        "result_impact": "Two teams adopted the approach.",
    }

    response = _create(client, alice_token, body)

    assert response.status_code == 201
    contract("Entry").validate(response.json())
    assert {key: response.json()[key] for key in body} == body
    [row] = _entries(migrated_db)
    assert (row.text, row.date, row.category, row.result_impact) == (
        "Gave a talk on testing.",
        dt.date(2026, 10, 31),
        "Learning",
        "Two teams adopted the approach.",
    )
    assert [name for _, _, name in _linked_tags(migrated_db, response.json()["id"])] == [
        "Public speaking",
        "Testing",
    ]


# --- Tags ---------------------------------------------------------------------------------


@pytest.mark.parametrize("tags", ["missing", []])
def test_fr_e2_tags_are_optional(client: TestClient, migrated_db: Engine, alice_token: str, tags):
    body = dict(VALID)
    if tags != "missing":
        body["tags"] = tags

    response = _create(client, alice_token, body)

    assert response.status_code == 201
    assert response.json()["tags"] == []
    assert _tags(migrated_db) == []
    assert _links(migrated_db) == []


def test_fr_e3_new_tag_created_on_save(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    response = _create(client, alice_token, {**VALID, "tags": ["  machine   learning ", "Go"]})

    assert response.status_code == 201
    assert response.json()["tags"] == ["machine learning", "Go"]
    stored = _tags(migrated_db)
    assert [(user_id, name) for _, user_id, name in stored] == [
        (alice, "Go"),
        (alice, "machine learning"),
    ]
    assert _linked_tags(migrated_db, response.json()["id"]) == stored


def test_fr_e3_existing_tag_is_reused_in_any_case_with_its_stored_spelling(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    python = _tag(migrated_db, alice, "Python")

    response = _create(client, alice_token, {**VALID, "tags": ["python", "PYTHON ", "Rust"]})

    assert response.status_code == 201
    assert response.json()["tags"] == ["Python", "Rust"]
    names = [(name, tag_id == python) for tag_id, _, name in _tags(migrated_db)]
    assert names == [("Python", True), ("Rust", False)]
    assert [name for _, _, name in _linked_tags(migrated_db, response.json()["id"])] == [
        "Python",
        "Rust",
    ]


def test_fr_e3_tag_created_by_one_entry_is_reused_by_the_next(
    client: TestClient, migrated_db: Engine, alice_token: str
):
    first = _create(client, alice_token, {**VALID, "tags": ["Kubernetes"]})
    second = _create(client, alice_token, {**VALID, "tags": ["kubernetes"]})

    assert second.json()["tags"] == ["Kubernetes"]
    [(tag_id, _, _)] = _tags(migrated_db)
    assert _linked_tags(migrated_db, first.json()["id"]) == _linked_tags(
        migrated_db, second.json()["id"]
    )
    assert _linked_tags(migrated_db, second.json()["id"])[0][0] == tag_id


def test_fr_a3_entry_uses_the_users_own_tag_never_another_users_tag_of_the_same_name(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    bob = _user(migrated_db, "bob@example.com")
    bobs_python = _tag(migrated_db, bob, "Python")
    alices_python = _tag(migrated_db, alice, "Python")

    response = _create(client, alice_token, {**VALID, "tags": ["Python"]})

    assert response.status_code == 201
    assert _linked_tags(migrated_db, response.json()["id"]) == [(alices_python, alice, "Python")]
    assert (bobs_python, bob, "Python") in _tags(migrated_db)


def test_fr_a3_another_users_tag_is_never_reused_and_the_user_gets_their_own(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    bob = _user(migrated_db, "bob@example.com")
    bobs_python = _tag(migrated_db, bob, "PYTHON")

    response = _create(client, alice_token, {**VALID, "tags": ["Python"]})

    assert response.status_code == 201
    assert response.json()["tags"] == ["Python"]
    [(tag_id, user_id, name)] = _linked_tags(migrated_db, response.json()["id"])
    assert (user_id, name) == (alice, "Python")
    assert tag_id != bobs_python
    assert (bobs_python, bob, "PYTHON") in _tags(migrated_db)


def test_fr_e3_failed_save_stores_neither_the_entry_nor_any_new_tag(
    test_database_url: str,
    migrated_db: Engine,
    alice: uuid.UUID,
    alice_token: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
):
    """§7.3: new tags are only created when the entry is saved; a failed save keeps nothing."""
    from app.main import create_app
    from app.settings import Settings

    existing = _tag(migrated_db, alice, "Python")

    def link_to_a_missing_tag(session: Session, entry, tags) -> None:
        # The entry and the new tags are already in the transaction when the save fails.
        assert entry.id is not None and len(tags) == 3
        session.add(EntryTag(entry_id=entry.id, tag_id=uuid.uuid4()))
        session.flush()  # foreign key violation in the database

    monkeypatch.setattr(entries, "_link_tags", link_to_a_missing_tag)
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=["http://localhost:5173"],
        ai_provider="mock",
    )
    client = TestClient(create_app(settings), raise_server_exceptions=False)
    caplog.set_level(logging.DEBUG)
    text = "Secret entry text that must not be logged"

    response = _create(
        client, alice_token, {**VALID, "text": text, "tags": ["python", "Kubernetes", "Go"]}
    )

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == [(existing, alice, "Python")]
    assert _links(migrated_db) == []
    assert text not in caplog.text


def test_fr_e1_database_errors_do_not_repeat_the_values_of_the_statement(
    client: TestClient, migrated_db: Engine
):
    """A failed insert names the statement but not its values, so a logged traceback does not
    repeat the entry text (AGENTS.md: never log entry text)."""
    text = "Private entry text"

    with Session(client.app.state.engine) as session:
        # A user that does not exist: a foreign key violation, whose database message names
        # only the key.
        session.add(
            Entry(user_id=uuid.uuid4(), date=dt.date(2026, 11, 8), text=text, category="Learning")
        )
        with pytest.raises(IntegrityError) as error:
            session.flush()

    assert "SQL parameters hidden" in str(error.value)
    assert text not in str(error.value)
    assert text not in repr(error.value)


# --- Validation ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["missing", None, "", " ", "  \n\t \r\n", " 　﻿"])
def test_fr_e2_entry_requires_text(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, text
):
    body = dict(VALID)
    if text == "missing":
        del body["text"]
    else:
        body["text"] = text

    _assert_validation_error(_create(client, alice_token, body), contract, ["text"])
    assert _entries(migrated_db) == []


@pytest.mark.parametrize("date", ["missing", None, ""])
def test_fr_e2_entry_requires_date(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, date
):
    """The API never fills in a date; the form (#27) pre-fills today's date."""
    body = dict(VALID)
    if date == "missing":
        del body["date"]
    else:
        body["date"] = date

    _assert_validation_error(_create(client, alice_token, body), contract, ["date"])
    assert _entries(migrated_db) == []


@pytest.mark.parametrize(
    "date",
    [
        "2026-02-30",
        "2025-02-29",
        "2026-13-01",
        "2026-00-10",
        "2026-04-31",
        "0000-01-01",
        "2026-11-8",
        "26-11-08",
        "08.11.2026",
        "2026/11/08",
        "20261108",
        " 2026-11-08",
        "2026-11-08\n",
        "2026-11-08T00:00:00",
        "2026-11-08T00:00:00Z",
        "２０２６-11-08",
        "+2026-11-08",
        "today",
        1762560000,
        20261108,
        True,
        ["2026-11-08"],
        {"year": 2026},
    ],
)
def test_fr_e2_date_must_be_a_real_calendar_date_in_the_contract_format(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, date
):
    response = _create(client, alice_token, {**VALID, "date": date})

    _assert_validation_error(response, contract, ["date"])
    assert _entries(migrated_db) == []


@pytest.mark.parametrize(
    "date", ["2026-11-08", "2099-12-31", "2028-02-29", "1999-01-01", "0001-01-01", "9999-12-31"]
)
def test_fr_e2_any_real_date_is_accepted_including_future_dates(
    client: TestClient, migrated_db: Engine, alice_token: str, date: str
):
    response = _create(client, alice_token, {**VALID, "date": date})

    assert response.status_code == 201
    assert response.json()["date"] == date
    [row] = _entries(migrated_db)
    assert row.date == dt.date.fromisoformat(date)


@pytest.mark.parametrize(
    "category",
    ["missing", None, "", "achievement", "ACHIEVEMENT", " Achievement", "Side Project", "Other", 1],
)
def test_fr_e2_entry_requires_one_of_the_four_categories(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, category
):
    body = dict(VALID)
    if category == "missing":
        del body["category"]
    else:
        body["category"] = category

    _assert_validation_error(_create(client, alice_token, body), contract, ["category"])
    assert _entries(migrated_db) == []


def test_fr_e2_missing_text_date_and_category_are_all_named(
    client: TestClient, migrated_db: Engine, alice_token: str, contract
):
    response = _create(client, alice_token, {"tags": ["Python"]})

    _assert_validation_error(response, contract, ["text", "date", "category"])
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == []


@pytest.mark.parametrize("empty", ["", " ", "\t\n", "   "])
def test_fr_e3_tag_name_empty_after_trimming_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, empty: str
):
    response = _create(client, alice_token, {**VALID, "tags": ["Python", empty]})

    _assert_validation_error(response, contract, ["tags.1"])
    assert response.json()["fields"][0]["reason"] == "Tag name must not be empty."
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == []


@pytest.mark.parametrize(
    ("tags", "field"),
    [(None, "tags"), ("Python", "tags"), ({"name": "Python"}, "tags"), (["Go", 5], "tags.1")],
)
def test_fr_e3_tags_must_be_a_list_of_names(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, tags, field: str
):
    response = _create(client, alice_token, {**VALID, "tags": tags})

    _assert_validation_error(response, contract, [field])
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == []


@pytest.mark.parametrize("result_impact", [5, True, ["Saved time"], {"text": "x"}])
def test_fr_e2_result_impact_must_be_text_or_null(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, result_impact
):
    response = _create(client, alice_token, {**VALID, "result_impact": result_impact})

    _assert_validation_error(response, contract, ["result_impact"])
    assert _entries(migrated_db) == []


@pytest.mark.parametrize("text", [5, True, ["Shipped"], {"text": "Shipped"}])
def test_fr_e2_text_must_be_a_string(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, text
):
    _assert_validation_error(
        _create(client, alice_token, {**VALID, "text": text}), contract, ["text"]
    )
    assert _entries(migrated_db) == []


@pytest.mark.parametrize("character", ["\\u0000", "\\ud800", "\\udfff", "\\ude00\\ud83d"])
@pytest.mark.parametrize("field", ["text", "result_impact", "tag"])
def test_fr_e2_nul_or_unpaired_surrogate_is_a_validation_error_not_a_server_error(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, character, field
):
    """PostgreSQL cannot store NUL, and a lone surrogate has no UTF-8 form (AGENTS.md:
    validate all input at the API boundary)."""
    values = {"text": "Shipped it", "result_impact": "Saved time", "tag": "Python"}
    values[field] = f"Before{character}after"
    raw = (
        f'{{"text": "{values["text"]}", "date": "{DATE}", "category": "Achievement", '
        f'"tags": ["Go", "{values["tag"]}"], "result_impact": "{values["result_impact"]}"}}'
    )

    response = _create_raw(client, alice_token, raw)

    _assert_validation_error(response, contract, ["tags.1" if field == "tag" else field])
    assert "Before" not in response.text
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == []


@pytest.mark.parametrize("raw", ["[]", '"text"', "null", "{", ""])
def test_fr_e2_body_must_be_a_json_object(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, raw: str
):
    response = _create_raw(client, alice_token, raw)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert _entries(migrated_db) == []


# --- Authentication -----------------------------------------------------------------------


@pytest.mark.parametrize("body", [VALID, {}])
@pytest.mark.parametrize("token", [None, "not-a-real-token"])
def test_fr_a3_create_without_a_valid_token_is_not_authenticated(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, contract, token, body
):
    response = _create(client, token, body)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _entries(migrated_db) == []


NOT_JSON = [b"junk", b'{"text":', b"\xff\xfe", b"\x80"]
"""Bodies FastAPI cannot read: not JSON, cut off, a UTF-16 mark only, and not UTF-8."""


def _create_bytes(client: TestClient, token: str | None, body: bytes):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/entries", content=body, headers={**headers, "content-type": "application/json"}
    )


@pytest.mark.parametrize("body", NOT_JSON)
@pytest.mark.parametrize("token", [None, "not-a-real-token", "expired"])
def test_fr_a3_create_with_a_body_that_is_not_json_and_no_valid_token_is_not_authenticated(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, contract, token, body: bytes
):
    """The token is checked first, although FastAPI reads the body before any dependency."""
    if token == "expired":
        token = _token(migrated_db, alice, valid_for=dt.timedelta(seconds=-1))

    response = _create_bytes(client, token, body)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == []


@pytest.mark.parametrize("body", NOT_JSON[:3])
def test_fr_a3_create_with_a_valid_token_and_a_body_that_is_not_json_is_a_validation_error(
    client: TestClient, migrated_db: Engine, alice_token: str, contract, body: bytes
):
    response = _create_bytes(client, alice_token, body)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert _entries(migrated_db) == []


def test_fr_a3_create_with_an_expired_token_is_not_authenticated(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, contract
):
    expired = _token(migrated_db, alice, valid_for=dt.timedelta(seconds=-1))

    response = _create(client, expired, {**VALID, "tags": ["Python"]})

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert _entries(migrated_db) == []
    assert _tags(migrated_db) == []


# --- Privacy ------------------------------------------------------------------------------


def test_fr_e1_entry_text_is_never_logged(
    client: TestClient, migrated_db: Engine, alice_token: str, caplog
):
    caplog.set_level(logging.DEBUG)
    text = "Confidential achievement text"
    impact = "Confidential impact text"

    _create(client, alice_token, {**VALID, "text": text, "result_impact": impact})
    _create(client, alice_token, {**VALID, "text": text, "date": "2026-02-30"})
    _create(client, None, {**VALID, "text": text})

    assert text not in caplog.text
    assert impact not in caplog.text
