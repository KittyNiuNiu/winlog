"""Listing and filtering entries through the API (issue #11, `listEntries` in openapi.yaml).

Covers FR-R1 and FR-A3, and the acceptance criteria in product-spec.md §7.4, against real
PostgreSQL. Also covers the shared filter function that summary generation (#17) reuses.
"""

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, insert, inspect, update
from sqlalchemy.orm import Session

from app import entries
from app.auth import hash_token
from app.entries import EntryFilter, filter_entries
from app.models import Entry, EntryTag, Token, User
from app.tags import resolve_tags
from tests.integration.test_entries import _tag, _token, _user
from tests.integration.test_tags import _index_treats_as_one

# --- Helpers ------------------------------------------------------------------------------


def _entry(
    engine: Engine,
    user_id: uuid.UUID,
    date: str,
    category: str = "Achievement",
    tags: tuple[str, ...] = (),
    created_at: dt.datetime | None = None,
) -> str:
    """An entry stored directly, with its tags resolved by #8's rules. Returns its id."""
    with Session(engine) as session:
        user = session.get_one(User, user_id)
        values = {"user_id": user_id, "date": dt.date.fromisoformat(date), "category": category}
        if created_at is not None:
            values["created_at"] = created_at
        entry_id = session.execute(
            insert(Entry).values(text=f"Entry on {date}", **values).returning(Entry.id)
        ).scalar_one()
        for tag in resolve_tags(session, user, list(tags)):
            session.add(EntryTag(entry_id=entry_id, tag_id=tag.id))
        session.commit()
        return str(entry_id)


def _link(engine: Engine, entry_id: str, tag_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(insert(EntryTag).values(entry_id=uuid.UUID(entry_id), tag_id=tag_id))


def _list(client: TestClient, token: str | None, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/entries", params=params, headers=headers)


def _ids(client: TestClient, token: str, params=None) -> list[str]:
    response = _list(client, token, params)
    assert response.status_code == 200
    return [entry["id"] for entry in response.json()["entries"]]


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


@pytest.fixture
def bob(migrated_db: Engine) -> uuid.UUID:
    return _user(migrated_db, "bob@example.com")


@pytest.fixture
def january(migrated_db: Engine, alice: uuid.UUID) -> dict[str, str]:
    """Alice's entries around January 2026, by name."""
    return {
        "dec31": _entry(migrated_db, alice, "2025-12-31", "Learning", ("Python",)),
        "jan01": _entry(migrated_db, alice, "2026-01-01", "Achievement", ("Python", "Go")),
        "jan15": _entry(migrated_db, alice, "2026-01-15", "Feedback", ("Mentoring",)),
        "jan31": _entry(migrated_db, alice, "2026-01-31", "Side project", ()),
        "feb01": _entry(migrated_db, alice, "2026-02-01", "Achievement", ("Go",)),
    }


def _named(entry_ids: dict[str, str], names: list[str]) -> list[str]:
    return [entry_ids[name] for name in names]


# --- Listing ------------------------------------------------------------------------------


def test_fr_r1_list_without_filters_returns_all_entries_with_category_and_tags(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str, contract
):
    created = client.post(
        "/entries",
        json={
            "text": "Gave a talk.",
            "date": "2026-10-31",
            "category": "Learning",
            "tags": ["Testing", "Public speaking"],
            "result_impact": "Two teams adopted it.",
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    ).json()
    other = _entry(migrated_db, alice, "2026-10-01", "Side project")

    response = _list(client, alice_token)

    assert response.status_code == 200
    body = response.json()
    contract("EntryList").validate(body)
    fetched = client.get(
        f"/entries/{created['id']}", headers={"Authorization": f"Bearer {alice_token}"}
    ).json()
    assert body["entries"][0] == fetched
    assert body["entries"][0]["category"] == "Learning"
    assert body["entries"][0]["tags"] == ["Public speaking", "Testing"]
    assert body["entries"][1]["id"] == other
    assert body["entries"][1]["category"] == "Side project"
    assert body["entries"][1]["tags"] == []
    assert body["entries"][1]["result_impact"] is None


def test_fr_r1_list_of_a_user_without_entries_is_empty(
    client: TestClient, alice_token: str, contract
):
    response = _list(client, alice_token)

    assert response.status_code == 200
    contract("EntryList").validate(response.json())
    assert response.json() == {"entries": []}


def test_fr_r1_list_without_filters_is_not_paginated(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    start = dt.date(2025, 1, 1)
    with migrated_db.begin() as connection:
        connection.execute(
            insert(Entry),
            [
                {
                    "user_id": alice,
                    "date": start + dt.timedelta(days=day),
                    "text": "Entry",
                    "category": "Learning",
                }
                for day in range(250)
            ],
        )

    assert len(_ids(client, alice_token)) == 250


def test_fr_r1_list_is_sorted_by_date_then_creation_time_newest_first(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    noon = dt.datetime(2026, 3, 1, 12, tzinfo=dt.UTC)
    # Created in an order that differs from both sort keys.
    old_late = _entry(migrated_db, alice, "2026-01-01", created_at=noon + dt.timedelta(hours=5))
    new_early = _entry(migrated_db, alice, "2026-02-01", created_at=noon - dt.timedelta(hours=1))
    new_late = _entry(migrated_db, alice, "2026-02-01", created_at=noon + dt.timedelta(hours=1))
    new_middle = _entry(migrated_db, alice, "2026-02-01", created_at=noon)
    future = _entry(migrated_db, alice, "2099-12-31", created_at=noon - dt.timedelta(days=9))

    assert _ids(client, alice_token) == [future, new_late, new_middle, new_early, old_late]


def test_fr_r1_entry_tags_are_sorted_ignoring_case_as_in_get(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    entry_id = _entry(migrated_db, alice, "2026-01-01", tags=("beta", "Alpha", "gamma", "Beta2"))

    [listed] = _list(client, alice_token).json()["entries"]
    fetched = client.get(
        f"/entries/{entry_id}", headers={"Authorization": f"Bearer {alice_token}"}
    ).json()

    assert listed["tags"] == ["Alpha", "beta", "Beta2", "gamma"]
    assert listed == fetched


def test_fr_r1_list_is_flat_and_not_grouped_by_category(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    """Grouping by category (FR-R2) happens in the frontend (#31)."""
    first = _entry(migrated_db, alice, "2026-01-03", "Learning")
    second = _entry(migrated_db, alice, "2026-01-02", "Achievement")
    third = _entry(migrated_db, alice, "2026-01-01", "Learning")

    response = _list(client, alice_token)

    assert list(response.json()) == ["entries"]
    assert [entry["id"] for entry in response.json()["entries"]] == [first, second, third]


# --- Period -------------------------------------------------------------------------------


def test_fr_r1_filter_by_period_includes_start_date(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = {"start_date": "2026-01-01", "end_date": "2026-01-14"}

    assert _ids(client, alice_token, params) == _named(january, ["jan01"])


def test_fr_r1_filter_by_period_includes_end_date(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = {"start_date": "2026-01-02", "end_date": "2026-01-31"}

    assert _ids(client, alice_token, params) == _named(january, ["jan31", "jan15"])


def test_fr_r1_filter_by_period_includes_both_days(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = {"start_date": "2026-01-01", "end_date": "2026-01-31"}

    assert _ids(client, alice_token, params) == _named(january, ["jan31", "jan15", "jan01"])


def test_fr_r1_filter_by_period_of_one_day(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = {"start_date": "2026-01-15", "end_date": "2026-01-15"}

    assert _ids(client, alice_token, params) == _named(january, ["jan15"])


def test_fr_r1_filter_by_start_date_alone_is_open_ended(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    assert _ids(client, alice_token, {"start_date": "2026-01-31"}) == _named(
        january, ["feb01", "jan31"]
    )


def test_fr_r1_filter_by_end_date_alone_is_open_ended(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    assert _ids(client, alice_token, {"end_date": "2026-01-01"}) == _named(
        january, ["jan01", "dec31"]
    )


def test_fr_r1_filter_by_period_without_entries_is_empty(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = {"start_date": "2026-03-01", "end_date": "2026-03-31"}

    assert _ids(client, alice_token, params) == []


# --- Categories ---------------------------------------------------------------------------


def test_fr_r1_filter_by_one_category(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    assert _ids(client, alice_token, {"category": "Achievement"}) == _named(
        january, ["feb01", "jan01"]
    )


def test_fr_r1_several_categories_match_entries_in_any_of_them(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = [("category", "Learning"), ("category", "Side project"), ("category", "Feedback")]

    assert _ids(client, alice_token, params) == _named(january, ["jan31", "jan15", "dec31"])


def test_fr_r1_category_given_twice_is_the_same_filter(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = [("category", "Feedback"), ("category", "Feedback")]

    assert _ids(client, alice_token, params) == _named(january, ["jan15"])


# --- Tags ---------------------------------------------------------------------------------


def test_fr_r1_filter_by_one_tag(client: TestClient, alice_token: str, january: dict[str, str]):
    assert _ids(client, alice_token, {"tag": "Go"}) == _named(january, ["feb01", "jan01"])


def test_fr_r1_several_tags_match_entries_with_any_of_them(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = [("tag", "Mentoring"), ("tag", "Go")]

    assert _ids(client, alice_token, params) == _named(january, ["feb01", "jan15", "jan01"])


def test_fr_r1_entry_with_several_selected_tags_appears_once(
    client: TestClient, alice_token: str, january: dict[str, str]
):
    params = [("tag", "Python"), ("tag", "Go"), ("tag", "python")]

    assert _ids(client, alice_token, params) == _named(january, ["feb01", "jan01", "dec31"])


@pytest.mark.parametrize("name", ["python", "PYTHON", "  Python ", "pYtHoN"])
def test_fr_r1_tag_names_match_ignoring_case_and_surrounding_spaces(
    client: TestClient, alice_token: str, january: dict[str, str], name: str
):
    assert _ids(client, alice_token, {"tag": name}) == _named(january, ["jan01", "dec31"])


def test_fr_r1_tag_names_match_with_inner_spaces_collapsed(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    entry_id = _entry(migrated_db, alice, "2026-01-01", tags=("Machine Learning",))

    assert _ids(client, alice_token, {"tag": " machine \t  LEARNING  "}) == [entry_id]
    assert _ids(client, alice_token, {"tag": "machinelearning"}) == []


@pytest.mark.parametrize(
    ("stored", "given"),
    [
        ("Python", "PYTHON"),
        ("Ärger", "ärger"),
        ("Straße", "STRASSE"),
        # Python lower-cases a word-final capital sigma to "ς"; PostgreSQL gives "σ".
        ("ΟΔΟΣ", "οδος"),
        ("Kelvin", "Kelvin"),
    ],
)
def test_fr_r1_tag_names_match_exactly_as_the_tag_index_does(
    client: TestClient,
    migrated_db: Engine,
    alice: uuid.UUID,
    alice_token: str,
    stored: str,
    given: str,
):
    """#8's rule: PostgreSQL's lower(), as in the unique index, never Python's str.lower()."""
    same_for_index = _index_treats_as_one(migrated_db, stored, given)
    entry_id = _entry(migrated_db, alice, "2026-01-01", tags=(stored,))

    assert _ids(client, alice_token, {"tag": given}) == ([entry_id] if same_for_index else [])


def test_fr_r1_tag_names_are_repeated_parameters_and_may_contain_commas(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    with_comma = _entry(migrated_db, alice, "2026-01-02", tags=("Sales, EMEA",))
    sales = _entry(migrated_db, alice, "2026-01-01", tags=("Sales",))

    assert _ids(client, alice_token, {"tag": "Sales, EMEA"}) == [with_comma]
    assert _ids(client, alice_token, [("tag", "Sales"), ("tag", "EMEA")]) == [sales]


def test_fr_r1_unknown_tag_name_matches_nothing_and_is_not_an_error(
    client: TestClient, alice_token: str, january: dict[str, str], contract
):
    response = _list(client, alice_token, {"tag": "Unknown"})

    assert response.status_code == 200
    contract("EntryList").validate(response.json())
    assert response.json() == {"entries": []}
    params = [("tag", "Unknown"), ("tag", "Mentoring")]
    assert _ids(client, alice_token, params) == _named(january, ["jan15"])


def test_fr_r1_unused_tag_name_matches_nothing(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, alice_token: str
):
    _tag(migrated_db, alice, "Unused")
    _entry(migrated_db, alice, "2026-01-01", tags=("Go",))

    assert _ids(client, alice_token, {"tag": "Unused"}) == []


@pytest.mark.parametrize("name", ["", "   "])
def test_fr_r1_empty_tag_name_matches_nothing_and_is_not_an_error(
    client: TestClient, alice_token: str, january: dict[str, str], name: str
):
    assert _ids(client, alice_token, {"tag": name}) == []
    assert _ids(client, alice_token, [("tag", name), ("tag", "Go")]) == _named(
        january, ["feb01", "jan01"]
    )


# --- Combined filters ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"start_date": "2026-01-01", "category": "Achievement"}, ["feb01", "jan01"]),
        ({"end_date": "2026-01-31", "category": "Achievement"}, ["jan01"]),
        ({"start_date": "2026-01-01", "tag": "Python"}, ["jan01"]),
        ({"category": "Learning", "tag": "Python"}, ["dec31"]),
        ({"category": "Learning", "tag": "Go"}, []),
        (
            [
                ("start_date", "2026-01-01"),
                ("end_date", "2026-01-31"),
                ("category", "Achievement"),
                ("category", "Feedback"),
                ("tag", "Go"),
                ("tag", "Mentoring"),
            ],
            ["jan15", "jan01"],
        ),
        (
            [
                ("start_date", "2026-01-02"),
                ("end_date", "2026-02-01"),
                ("category", "Achievement"),
                ("tag", "Python"),
            ],
            [],
        ),
    ],
)
def test_fr_r1_different_filter_types_combine_with_and(
    client: TestClient, alice_token: str, january: dict[str, str], params, expected: list[str]
):
    assert _ids(client, alice_token, params) == _named(january, expected)


# --- Other users (FR-A3) ------------------------------------------------------------------


def test_fr_a3_list_never_contains_another_users_entries(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, bob: uuid.UUID, alice_token: str
):
    alice_entry = _entry(migrated_db, alice, "2026-01-01", "Learning", ("Python",))
    bob_entry = _entry(migrated_db, bob, "2026-01-01", "Learning", ("Python",))
    bob_token = _token(migrated_db, bob)

    for params in (
        None,
        {"tag": "Python"},
        {"category": "Learning"},
        {"start_date": "2026-01-01", "end_date": "2026-01-01"},
    ):
        assert _ids(client, alice_token, params) == [alice_entry]
        assert _ids(client, bob_token, params) == [bob_entry]


def test_fr_a3_another_users_tag_name_never_returns_their_entries(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, bob: uuid.UUID, alice_token: str
):
    _entry(migrated_db, alice, "2026-01-01", tags=("Go",))
    _entry(migrated_db, bob, "2026-01-01", tags=("Cooking",))

    response = _list(client, alice_token, {"tag": "Cooking"})

    assert response.status_code == 200
    assert response.json() == {"entries": []}


def test_fr_a3_tag_filter_ignores_a_link_from_one_users_entry_to_another_users_tag(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, bob: uuid.UUID, alice_token: str
):
    """The database allows such a link (#5), so the filter checks both owners, as /tags does."""
    alice_entry = _entry(migrated_db, alice, "2026-01-01")
    _link(migrated_db, alice_entry, _tag(migrated_db, bob, "Secret"))
    bob_token = _token(migrated_db, bob)

    assert _ids(client, alice_token, {"tag": "Secret"}) == []
    assert _ids(client, bob_token, {"tag": "Secret"}) == []
    assert _ids(client, bob_token) == []
    [listed] = _list(client, alice_token).json()["entries"]
    assert listed["id"] == alice_entry
    assert listed["tags"] == []


# --- Validation and authentication --------------------------------------------------------


def test_fr_r1_start_date_after_end_date_is_a_validation_error(
    client: TestClient, alice_token: str, january: dict[str, str], contract
):
    response = _list(client, alice_token, {"start_date": "2026-02-01", "end_date": "2026-01-31"})

    _assert_validation_error(response, contract, ["end_date"])


@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize(
    "value", ["2026-02-30", "2026-13-01", "2026-1-01", "2026-01-01T00:00:00", "1767225600", ""]
)
def test_fr_r1_date_that_is_not_a_real_date_in_the_contract_format_is_a_validation_error(
    client: TestClient, alice_token: str, contract, field: str, value: str
):
    _assert_validation_error(_list(client, alice_token, {field: value}), contract, [field])


@pytest.mark.parametrize("value", ["Other", "achievement", "", "Side-project"])
def test_fr_r1_category_that_is_not_one_of_the_four_is_a_validation_error(
    client: TestClient, alice_token: str, contract, value: str
):
    response = _list(client, alice_token, [("category", "Learning"), ("category", value)])

    _assert_validation_error(response, contract, ["category.1"])


@pytest.mark.parametrize("value", ["\x00", "Py\x00thon"])
def test_fr_r1_tag_name_the_database_cannot_take_is_a_validation_error(
    client: TestClient, alice_token: str, january: dict[str, str], contract, value: str
):
    response = _list(client, alice_token, [("tag", "Go"), ("tag", value)])

    _assert_validation_error(response, contract, ["tag.1"])
    assert "Py" not in response.text


def test_fr_a3_list_without_a_valid_token_is_not_authenticated(
    client: TestClient, migrated_db: Engine, alice: uuid.UUID, january: dict[str, str], contract
):
    expired = _token(migrated_db, alice)
    with migrated_db.begin() as connection:
        connection.execute(
            update(Token)
            .where(Token.token_hash == hash_token(expired))
            .values(expires_at=func.now() - dt.timedelta(seconds=1))
        )

    for token in (None, "not-a-token", expired):
        for params in (None, {"start_date": "2026-02-30", "category": "Other", "tag": "\x00"}):
            response = _list(client, token, params)
            assert response.status_code == 401
            contract("Error").validate(response.json())
            assert response.json()["code"] == "not_authenticated"
            assert response.headers["WWW-Authenticate"] == "Bearer"
            assert "Python" not in response.text


# --- Shared filter function and index -----------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"start_date": "2026-01-01", "end_date": "2026-01-31"},
        {"categories": ["Achievement", "Feedback"]},
        {"tags": ["python", " MENTORING "]},
        {"start_date": "2026-01-01", "categories": ["Achievement"], "tags": ["Go"]},
    ],
)
def test_fr_r1_shared_filter_function_returns_exactly_the_listed_entries(
    client: TestClient,
    migrated_db: Engine,
    alice: uuid.UUID,
    alice_token: str,
    january: dict[str, str],
    params: dict,
):
    """Summary generation (#17) uses `filter_entries`, so it selects what the list shows."""
    entry_filter = EntryFilter(
        start_date=dt.date.fromisoformat(params["start_date"]) if "start_date" in params else None,
        end_date=dt.date.fromisoformat(params["end_date"]) if "end_date" in params else None,
        categories=params.get("categories", ()),
        tags=params.get("tags", ()),
    )
    query = {
        key: value
        for key, value in (
            ("start_date", params.get("start_date")),
            ("end_date", params.get("end_date")),
            ("category", params.get("categories")),
            ("tag", params.get("tags")),
        )
        if value
    }

    with Session(migrated_db) as session:
        user = session.get_one(User, alice)
        selected = filter_entries(session, user, entry_filter)

    listed = _list(client, alice_token, query).json()["entries"]
    assert [entry.model_dump(mode="json") for entry in selected] == listed
    assert selected


def test_fr_a3_shared_filter_function_only_returns_the_given_users_entries(
    migrated_db: Engine, alice: uuid.UUID, bob: uuid.UUID
):
    alice_entry = _entry(migrated_db, alice, "2026-01-01", tags=("Python",))
    _entry(migrated_db, bob, "2026-01-01", tags=("Python",))

    with Session(migrated_db) as session:
        user = session.get_one(User, alice)
        assert [str(entry.id) for entry in filter_entries(session, user, EntryFilter())] == [
            alice_entry
        ]
        tagged = filter_entries(session, user, EntryFilter(tags=["python"]))
        assert [str(entry.id) for entry in tagged] == [alice_entry]


def test_fr_r1_list_endpoint_uses_the_shared_filter_function(
    client: TestClient, alice_token: str, january: dict[str, str], monkeypatch
):
    calls = []
    original = entries.filter_entries

    def recording(session, user, entry_filter):
        calls.append(entry_filter)
        return original(session, user, entry_filter)

    monkeypatch.setattr(entries, "filter_entries", recording)
    params = [
        ("start_date", "2026-01-01"),
        ("end_date", "2026-01-31"),
        ("category", "Achievement"),
        ("tag", "Go"),
        ("tag", "Python"),
    ]

    assert _ids(client, alice_token, params) == _named(january, ["jan01"])
    assert calls == [
        EntryFilter(
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 31),
            categories=["Achievement"],
            tags=["Go", "Python"],
        )
    ]


def test_fr_r1_migration_adds_an_index_on_entries_user_id_and_date(migrated_db: Engine):
    found = inspect(migrated_db).get_indexes("entries")
    indexes = {index["name"]: index["column_names"] for index in found}

    assert indexes["ix_entries_user_id_date"] == ["user_id", "date"]
