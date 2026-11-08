"""Tag name rules, the resolve and lookup functions, and the tag list (issue #8).

Covers FR-E3, FR-A3 and the tag rules in product-spec.md §7.2, §7.3 and §10.5. Entries cannot
be created through the API yet (#9), so the tests add entries and links directly.
"""

import datetime as dt
import threading
import uuid
from collections.abc import Callable
from functools import partial

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_token
from app.db import violates
from app.models import TAG_NAME_UNIQUE_INDEX, Entry, EntryTag, Tag, Token, User
from app.tags import lookup_tags, resolve_tags

TODAY = dt.date(2026, 11, 8)
WAIT_SECONDS = 10


# --- Helpers ------------------------------------------------------------------------------


def _user(engine: Engine, email: str) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(User).values(email=email, password_hash="hash").returning(User.id)
        ).scalar_one()


def _token(engine: Engine, user_id: uuid.UUID) -> str:
    """A valid login for the user, without going through the password check."""
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


def _entry(engine: Engine, user_id: uuid.UUID) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(Entry)
            .values(user_id=user_id, date=TODAY, text="Shipped it", category="Achievement")
            .returning(Entry.id)
        ).scalar_one()


def _tag(engine: Engine, user_id: uuid.UUID, name: str) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(Tag).values(user_id=user_id, name=name).returning(Tag.id)
        ).scalar_one()


def _link(engine: Engine, entry_id: uuid.UUID, tag_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(insert(EntryTag).values(entry_id=entry_id, tag_id=tag_id))


def _unlink(engine: Engine, entry_id: uuid.UUID, tag_id: uuid.UUID) -> None:
    """What an entry edit (#10) does when it drops a tag from the entry."""
    with engine.begin() as connection:
        connection.execute(
            delete(EntryTag).where(EntryTag.entry_id == entry_id, EntryTag.tag_id == tag_id)
        )


def _tags_in_db(engine: Engine, user_id: uuid.UUID | None = None) -> list[tuple]:
    """(id, user_id, name) of every stored tag, or of one user's tags."""
    query = select(Tag.id, Tag.user_id, Tag.name).order_by(Tag.name)
    if user_id is not None:
        query = query.where(Tag.user_id == user_id)
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(query)]


def _resolve(engine: Engine, user_id: uuid.UUID, names: list[str]) -> list[tuple]:
    """Resolve in a session of its own and commit, as an entry save would."""
    with Session(engine) as session:
        tags = resolve_tags(session, session.get(User, user_id), names)
        result = [(tag.id, tag.user_id, tag.name) for tag in tags]
        session.commit()
    return result


def _lookup(engine: Engine, user_id: uuid.UUID, names: list[str]) -> list[tuple]:
    with Session(engine) as session:
        tags = lookup_tags(session, session.get(User, user_id), names)
        return [(tag.id, tag.user_id, tag.name) for tag in tags]


def _list(client: TestClient, token: str):
    return client.get("/tags", headers={"Authorization": f"Bearer {token}"})


def _listed(client: TestClient, token: str) -> list[str]:
    response = _list(client, token)
    assert response.status_code == 200
    return response.json()["tags"]


# --- Name rules ---------------------------------------------------------------------------


def test_fr_e3_tag_name_is_trimmed_and_inner_spaces_become_one(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    [(_, _, name)] = _resolve(migrated_db, alice, ["  machine   learning "])

    assert name == "machine learning"
    assert [row[2] for row in _tags_in_db(migrated_db)] == ["machine learning"]


def test_fr_e3_trimmed_name_matches_the_existing_tag(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    tag = _tag(migrated_db, alice, "machine learning")

    [(tag_id, _, name)] = _resolve(migrated_db, alice, ["  Machine \t  Learning\n"])

    assert (tag_id, name) == (tag, "machine learning")
    assert len(_tags_in_db(migrated_db)) == 1


def test_fr_e3_tag_names_match_ignoring_case_and_keep_the_first_spelling(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    python = _tag(migrated_db, alice, "Python")

    assert _resolve(migrated_db, alice, ["python"]) == [(python, alice, "Python")]
    assert _resolve(migrated_db, alice, ["PYTHON"]) == [(python, alice, "Python")]
    assert _lookup(migrated_db, alice, ["pYtHoN"]) == [(python, alice, "Python")]
    assert _tags_in_db(migrated_db) == [(python, alice, "Python")]


def test_fr_e3_new_tag_keeps_the_spelling_it_was_created_with(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    [(created, _, _)] = _resolve(migrated_db, alice, ["GraphQL"])

    assert _resolve(migrated_db, alice, ["graphql"]) == [(created, alice, "GraphQL")]


def test_fr_e3_same_name_twice_in_one_request_becomes_one_tag(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    tags = _resolve(migrated_db, alice, ["Rust", "rust", " RUST ", "Go", "rust"])

    assert [name for _, _, name in tags] == ["Rust", "Go"]
    assert sorted(row[2] for row in _tags_in_db(migrated_db)) == ["Go", "Rust"]


def test_fr_e3_same_existing_name_twice_returns_the_tag_once(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    python = _tag(migrated_db, alice, "Python")

    assert _resolve(migrated_db, alice, ["python", "Python"]) == [(python, alice, "Python")]
    assert _lookup(migrated_db, alice, ["PYTHON", "python"]) == [(python, alice, "Python")]


def test_fr_e3_resolve_rejects_a_name_that_is_empty_after_trimming(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    for names in (["Python", "   "], [""], ["\t\n"]):
        with Session(migrated_db) as session, pytest.raises(ValueError):
            resolve_tags(session, session.get(User, alice), names)

    assert _tags_in_db(migrated_db) == []


def test_fr_e3_resolve_and_lookup_of_no_names_return_nothing(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    assert _resolve(migrated_db, alice, []) == []
    assert _lookup(migrated_db, alice, []) == []
    assert _lookup(migrated_db, alice, ["  "]) == []


# --- The lower(name) index ----------------------------------------------------------------


def test_fr_e3_migration_makes_tag_names_unique_per_user_ignoring_case(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    _tag(migrated_db, alice, "Python")

    with pytest.raises(IntegrityError) as caught:
        _tag(migrated_db, alice, "python")

    assert violates(caught.value, TAG_NAME_UNIQUE_INDEX)
    with migrated_db.connect() as connection:
        definition = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": TAG_NAME_UNIQUE_INDEX},
        ).scalar_one()
    assert definition == (
        f"CREATE UNIQUE INDEX {TAG_NAME_UNIQUE_INDEX} ON public.tags USING btree "
        "(user_id, lower(name))"
    )


def test_fr_a3_two_users_can_each_have_a_tag_called_python(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    bob = _user(migrated_db, "bob@example.com")

    [(alice_tag, _, _)] = _resolve(migrated_db, alice, ["Python"])
    [(bob_tag, _, _)] = _resolve(migrated_db, bob, ["python"])

    assert alice_tag != bob_tag
    assert _tags_in_db(migrated_db, alice) == [(alice_tag, alice, "Python")]
    assert _tags_in_db(migrated_db, bob) == [(bob_tag, bob, "python")]


def _index_treats_as_one(engine: Engine, first: str, second: str) -> bool:
    """Whether the unique index rejects `second` once a user has a tag called `first`."""
    user = _user(engine, f"probe-{uuid.uuid4()}@example.com")
    _tag(engine, user, first)
    try:
        _tag(engine, user, second)
    except IntegrityError:
        return True
    return False


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Python", "PYTHON"),
        ("Ärger", "ärger"),
        ("Straße", "STRASSE"),
        # Python lower-cases a word-final capital sigma to "ς"; PostgreSQL gives "σ".
        ("ΟΔΟΣ", "οδος"),
        ("Kelvin", "Kelvin"),
    ],
)
def test_fr_e3_resolve_and_lookup_match_names_exactly_as_the_index_does(
    migrated_db: Engine, first: str, second: str
):
    same_for_index = _index_treats_as_one(migrated_db, first, second)
    alice = _user(migrated_db, "alice@example.com")

    resolved = _resolve(migrated_db, alice, [first, second])
    looked_up = _lookup(migrated_db, alice, [second])

    assert len(resolved) == (1 if same_for_index else 2)
    assert len(_tags_in_db(migrated_db, alice)) == len(resolved)
    assert looked_up == [resolved[0] if same_for_index else resolved[1]]


# --- Resolve ------------------------------------------------------------------------------


def test_fr_e3_resolve_creates_missing_tags_and_reuses_existing_ones(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    python = _tag(migrated_db, alice, "Python")

    tags = _resolve(migrated_db, alice, ["FastAPI", "python", "SQL"])

    assert [name for _, _, name in tags] == ["FastAPI", "Python", "SQL"]
    assert tags[1][0] == python
    assert {row[2] for row in _tags_in_db(migrated_db, alice)} == {"FastAPI", "Python", "SQL"}
    assert all(user_id == alice for _, user_id, _ in tags)


def test_fr_e3_resolve_reuses_an_unused_tag(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    unused = _tag(migrated_db, alice, "Pyhton")

    assert _resolve(migrated_db, alice, ["pyhton"]) == [(unused, alice, "Pyhton")]
    assert len(_tags_in_db(migrated_db)) == 1


def test_fr_a3_resolve_never_returns_or_reuses_another_users_tag(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    bob = _user(migrated_db, "bob@example.com")
    bob_python = _tag(migrated_db, bob, "Python")
    bob_go = _tag(migrated_db, bob, "Go")

    tags = _resolve(migrated_db, alice, ["Python", "go"])

    assert {tag_id for tag_id, _, _ in tags}.isdisjoint({bob_python, bob_go})
    assert [(user_id, name) for _, user_id, name in tags] == [(alice, "Python"), (alice, "go")]
    assert _tags_in_db(migrated_db, bob) == [(bob_go, bob, "Go"), (bob_python, bob, "Python")]


def test_fr_e3_resolve_does_not_commit(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    with Session(migrated_db) as session:
        [tag] = resolve_tags(session, session.get(User, alice), ["Python"])
        assert tag.name == "Python"
        # Another connection does not see the tag before the caller commits.
        assert _tags_in_db(migrated_db) == []
        session.commit()

    assert [row[2] for row in _tags_in_db(migrated_db)] == ["Python"]


def test_fr_s2_new_tags_are_gone_when_the_entry_save_fails(migrated_db: Engine):
    """§7.3: tags that do not exist yet are only created when the entry is saved."""
    alice = _user(migrated_db, "alice@example.com")
    existing = _tag(migrated_db, alice, "Python")

    with Session(migrated_db) as session:
        user = session.get(User, alice)
        tags = resolve_tags(session, user, ["python", "Kubernetes", "Terraform"])
        assert len(tags) == 3
        # The entry save fails (here: a category the database rejects).
        with pytest.raises(IntegrityError):
            entry = Entry(user_id=alice, date=TODAY, text="Shipped it", category="Not a category")
            session.add(entry)
            session.flush()
            session.add_all(EntryTag(entry_id=entry.id, tag_id=tag.id) for tag in tags)
            session.flush()
        session.rollback()

    assert _tags_in_db(migrated_db) == [(existing, alice, "Python")]


def test_fr_e3_rolled_back_resolve_leaves_no_new_tags(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    with Session(migrated_db) as session:
        resolve_tags(session, session.get(User, alice), ["Kubernetes"])
        session.rollback()

    assert _tags_in_db(migrated_db) == []


# --- Lookup -------------------------------------------------------------------------------


def test_fr_s1_lookup_returns_only_existing_tags_and_creates_nothing(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    python = _tag(migrated_db, alice, "Python")
    sql = _tag(migrated_db, alice, "SQL")

    with Session(migrated_db) as session:
        tags = lookup_tags(session, session.get(User, alice), ["sql", "Kubernetes", " python "])
        result = [(tag.id, tag.name) for tag in tags]
        session.commit()

    assert result == [(sql, "SQL"), (python, "Python")]
    assert {row[2] for row in _tags_in_db(migrated_db)} == {"Python", "SQL"}


def test_fr_a3_lookup_never_returns_another_users_tag(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    bob = _user(migrated_db, "bob@example.com")
    _tag(migrated_db, bob, "Python")

    assert _lookup(migrated_db, alice, ["Python", "python"]) == []

    alice_python = _tag(migrated_db, alice, "python")
    assert _lookup(migrated_db, alice, ["PYTHON"]) == [(alice_python, alice, "python")]


# --- Simultaneous creation ----------------------------------------------------------------


def _in_thread(work: Callable[[], object]) -> tuple[threading.Thread, dict]:
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["result"] = work()
        except Exception as error:  # reported by the test
            outcome["error"] = error

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


def test_fr_e3_simultaneous_creation_of_the_same_tag_ends_with_one_tag(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    with Session(migrated_db) as first:
        [created] = resolve_tags(first, first.get(User, alice), ["Python"])
        # The second request inserts the same name while the first has not committed yet.
        thread, outcome = _in_thread(lambda: _resolve(migrated_db, alice, ["python"]))
        thread.join(timeout=0.5)
        assert thread.is_alive(), "the second insert should wait for the first transaction"
        first.commit()
        created_id = created.id

    thread.join(timeout=WAIT_SECONDS)
    assert not thread.is_alive()
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"] == [(created_id, alice, "Python")]
    assert _tags_in_db(migrated_db) == [(created_id, alice, "Python")]


def test_fr_e3_simultaneous_creation_after_a_rollback_creates_the_tag_once(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    with Session(migrated_db) as first:
        resolve_tags(first, first.get(User, alice), ["Python"])
        thread, outcome = _in_thread(lambda: _resolve(migrated_db, alice, ["python"]))
        thread.join(timeout=0.5)
        assert thread.is_alive()
        first.rollback()

    thread.join(timeout=WAIT_SECONDS)
    assert "error" not in outcome, outcome.get("error")
    [(tag_id, user_id, name)] = outcome["result"]
    assert (user_id, name) == (alice, "python")
    assert _tags_in_db(migrated_db) == [(tag_id, alice, "python")]


def test_fr_e3_simultaneous_requests_with_several_new_tags_share_them(migrated_db: Engine):
    """Requests that start together, with the names in different orders and cases."""
    alice = _user(migrated_db, "alice@example.com")
    orders = [["Alpha", "beta", "Gamma"], ["gamma", "BETA", "alpha"]]

    def work(names: list[str], barrier: threading.Barrier) -> list[tuple]:
        barrier.wait(timeout=WAIT_SECONDS)
        return _resolve(migrated_db, alice, names)

    for round_number in range(10):
        barrier = threading.Barrier(len(orders))
        runs = [
            _in_thread(partial(work, [f"{name} {round_number}" for name in order], barrier))
            for order in orders
        ]
        results = []
        for thread, outcome in runs:
            thread.join(timeout=WAIT_SECONDS)
            assert not thread.is_alive()
            assert "error" not in outcome, outcome.get("error")
            results.append({tag_id for tag_id, _, _ in outcome["result"]})
        assert results[0] == results[1]
        assert len(results[0]) == 3

    assert len(_tags_in_db(migrated_db)) == 30


def test_fr_e3_new_tags_are_inserted_in_a_fixed_order_so_requests_cannot_deadlock(
    migrated_db: Engine,
):
    """The second request asks for `beta` before `alpha`, but inserts `alpha` first.

    So it waits for the first transaction without holding `beta`, and the first transaction
    can still create `beta`. Inserting in the given order would deadlock here.
    """
    alice = _user(migrated_db, "alice@example.com")

    with Session(migrated_db) as first:
        user = first.get(User, alice)
        resolve_tags(first, user, ["alpha"])
        thread, outcome = _in_thread(lambda: _resolve(migrated_db, alice, ["beta", "alpha"]))
        thread.join(timeout=0.5)
        assert thread.is_alive()
        resolve_tags(first, user, ["beta"])
        first.commit()

    thread.join(timeout=WAIT_SECONDS)
    assert "error" not in outcome, outcome.get("error")
    assert [name for _, _, name in outcome["result"]] == ["beta", "alpha"]
    assert [row[2] for row in _tags_in_db(migrated_db)] == ["alpha", "beta"]


# --- Tag list endpoint --------------------------------------------------------------------


def test_fr_e3_list_returns_used_tags_sorted_ignoring_case(
    client: TestClient, migrated_db: Engine, contract
):
    alice = _user(migrated_db, "alice@example.com")
    entry = _entry(migrated_db, alice)
    for name in ("gamma", "Beta", "alpha", "Delta"):
        _link(migrated_db, entry, _tag(migrated_db, alice, name))
    _tag(migrated_db, alice, "Unused")

    response = _list(client, _token(migrated_db, alice))

    assert response.status_code == 200
    contract("TagList").validate(response.json())
    assert response.json() == {"tags": ["alpha", "Beta", "Delta", "gamma"]}


def test_fr_e3_list_shows_a_tag_used_by_several_entries_once(
    client: TestClient, migrated_db: Engine
):
    alice = _user(migrated_db, "alice@example.com")
    python = _tag(migrated_db, alice, "Python")
    for _ in range(3):
        _link(migrated_db, _entry(migrated_db, alice), python)

    assert _listed(client, _token(migrated_db, alice)) == ["Python"]


def test_fr_e3_list_is_empty_for_a_new_user(client: TestClient, migrated_db: Engine, contract):
    alice = _user(migrated_db, "alice@example.com")

    response = _list(client, _token(migrated_db, alice))

    assert response.status_code == 200
    contract("TagList").validate(response.json())
    assert response.json() == {"tags": []}


def test_fr_e3_list_hides_a_tag_after_its_last_entry_is_edited_and_shows_it_again(
    client: TestClient, migrated_db: Engine
):
    alice = _user(migrated_db, "alice@example.com")
    token = _token(migrated_db, alice)
    entry = _entry(migrated_db, alice)
    [(typo, _, _)] = _resolve(migrated_db, alice, ["Pyhton"])
    _link(migrated_db, entry, typo)
    assert _listed(client, token) == ["Pyhton"]

    # The user fixes the entry: the typo is replaced by the right tag.
    _unlink(migrated_db, entry, typo)
    [(python, _, _)] = _resolve(migrated_db, alice, ["Python"])
    _link(migrated_db, entry, python)

    assert _listed(client, token) == ["Python"]
    assert (typo, alice, "Pyhton") in _tags_in_db(migrated_db)

    # Using the name again brings back the same tag, with its first spelling.
    other_entry = _entry(migrated_db, alice)
    [(reused, _, _)] = _resolve(migrated_db, alice, ["PYHTON"])
    _link(migrated_db, other_entry, reused)

    assert reused == typo
    assert _listed(client, token) == ["Pyhton", "Python"]


def test_fr_e3_list_hides_a_tag_after_its_last_entry_is_deleted_and_shows_it_again(
    client: TestClient, migrated_db: Engine
):
    alice = _user(migrated_db, "alice@example.com")
    token = _token(migrated_db, alice)
    first, second = _entry(migrated_db, alice), _entry(migrated_db, alice)
    python = _tag(migrated_db, alice, "Python")
    _link(migrated_db, first, python)
    _link(migrated_db, second, python)

    with migrated_db.begin() as connection:
        connection.execute(delete(Entry).where(Entry.id == first))
    assert _listed(client, token) == ["Python"]

    with migrated_db.begin() as connection:
        connection.execute(delete(Entry).where(Entry.id == second))
    assert _listed(client, token) == []
    assert _tags_in_db(migrated_db) == [(python, alice, "Python")]

    _link(migrated_db, _entry(migrated_db, alice), python)
    assert _listed(client, token) == ["Python"]


def test_fr_a3_list_shows_each_user_only_their_own_tags(client: TestClient, migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    bob = _user(migrated_db, "bob@example.com")
    _link(migrated_db, _entry(migrated_db, alice), _tag(migrated_db, alice, "Python"))
    _link(migrated_db, _entry(migrated_db, alice), _tag(migrated_db, alice, "Leadership"))
    _link(migrated_db, _entry(migrated_db, bob), _tag(migrated_db, bob, "python"))
    _link(migrated_db, _entry(migrated_db, bob), _tag(migrated_db, bob, "Cooking"))

    assert _listed(client, _token(migrated_db, alice)) == ["Leadership", "Python"]
    assert _listed(client, _token(migrated_db, bob)) == ["Cooking", "python"]


def test_fr_a3_list_ignores_links_between_one_users_entry_and_another_users_tag(
    client: TestClient, migrated_db: Engine
):
    """The database allows such a link (#5), so the list checks both owners."""
    alice = _user(migrated_db, "alice@example.com")
    bob = _user(migrated_db, "bob@example.com")
    bob_tag = _tag(migrated_db, bob, "Secret")
    _link(migrated_db, _entry(migrated_db, alice), bob_tag)

    assert _listed(client, _token(migrated_db, alice)) == []
    assert _listed(client, _token(migrated_db, bob)) == []


def test_fr_a3_list_without_a_valid_token_is_not_authenticated(
    client: TestClient, migrated_db: Engine, contract
):
    alice = _user(migrated_db, "alice@example.com")
    _link(migrated_db, _entry(migrated_db, alice), _tag(migrated_db, alice, "Python"))
    expired = _token(migrated_db, alice)
    with migrated_db.begin() as connection:
        connection.execute(
            update(Token)
            .where(Token.token_hash == hash_token(expired))
            .values(expires_at=func.now() - dt.timedelta(seconds=1))
        )

    for headers in (
        {},
        {"Authorization": "Bearer not-a-token"},
        {"Authorization": f"Bearer {expired}"},
    ):
        response = client.get("/tags", headers=headers)
        assert response.status_code == 401
        contract("Error").validate(response.json())
        assert response.json()["code"] == "not_authenticated"
        assert "Python" not in response.text
