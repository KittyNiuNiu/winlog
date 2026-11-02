"""The rules the database itself enforces (issue #5)."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import Engine, delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from app.models import AiUsage, Entry, EntryTag, Summary, Tag, User

TODAY = dt.date(2026, 11, 2)


def _user(engine: Engine, email: str) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(User).values(email=email, password_hash="hash").returning(User.id)
        ).scalar_one()


def _entry(engine: Engine, user_id: uuid.UUID, **values) -> uuid.UUID:
    row = {"user_id": user_id, "date": TODAY, "text": "Shipped it", "category": "Achievement"}
    row.update(values)
    with engine.begin() as connection:
        return connection.execute(insert(Entry).values(**row).returning(Entry.id)).scalar_one()


def _tag(engine: Engine, user_id: uuid.UUID, name: str) -> uuid.UUID:
    with engine.begin() as connection:
        return connection.execute(
            insert(Tag).values(user_id=user_id, name=name).returning(Tag.id)
        ).scalar_one()


def _link(engine: Engine, entry_id: uuid.UUID, tag_id: uuid.UUID) -> None:
    with engine.begin() as connection:
        connection.execute(insert(EntryTag).values(entry_id=entry_id, tag_id=tag_id))


def _summary(engine: Engine, user_id: uuid.UUID, **values) -> uuid.UUID:
    row = {
        "user_id": user_id,
        "period_start": dt.date(2026, 1, 1),
        "period_end": dt.date(2026, 6, 30),
        "filter_categories": ["Achievement"],
        "filter_tags": ["Python"],
        "text": "A good half year.",
    }
    row.update(values)
    with engine.begin() as connection:
        return connection.execute(insert(Summary).values(**row).returning(Summary.id)).scalar_one()


def _ai_usage(engine: Engine, user_id: uuid.UUID, request_type: str = "suggestion") -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(AiUsage).values(
                user_id=user_id, day=TODAY, request_type=request_type, request_count=1
            )
        )


def _count(engine: Engine, statement) -> int:
    with engine.connect() as connection:
        return connection.execute(statement).scalar_one()


# --- Uniqueness ---------------------------------------------------------------------------


def test_duplicate_email_is_rejected(migrated_db: Engine):
    _user(migrated_db, "alice@example.com")

    with pytest.raises(IntegrityError):
        _user(migrated_db, "alice@example.com")


def test_duplicate_tag_name_for_the_same_user_is_rejected(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    _tag(migrated_db, alice, "Python")

    with pytest.raises(IntegrityError):
        _tag(migrated_db, alice, "Python")


def test_same_tag_name_for_two_users_is_allowed(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    bob = _user(migrated_db, "bob@example.com")

    _tag(migrated_db, alice, "Python")
    _tag(migrated_db, bob, "Python")

    assert _count(migrated_db, select(func.count()).select_from(Tag)) == 2


def test_an_entry_tag_link_exists_at_most_once(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    entry = _entry(migrated_db, alice)
    tag = _tag(migrated_db, alice, "Python")
    _link(migrated_db, entry, tag)

    with pytest.raises(IntegrityError):
        _link(migrated_db, entry, tag)


def test_ai_usage_has_one_row_per_user_day_and_type(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    _ai_usage(migrated_db, alice, "suggestion")
    _ai_usage(migrated_db, alice, "summary")

    with pytest.raises(IntegrityError):
        _ai_usage(migrated_db, alice, "suggestion")


# --- Required values and allowed values ---------------------------------------------------


@pytest.mark.parametrize("category", ["Achievement", "Learning", "Feedback", "Side project"])
def test_the_four_categories_are_accepted(migrated_db: Engine, category: str):
    alice = _user(migrated_db, "alice@example.com")

    _entry(migrated_db, alice, category=category)


@pytest.mark.parametrize("category", ["Other", "achievement", "Side Project", ""])
def test_fr_e2_a_category_outside_the_four_is_rejected(migrated_db: Engine, category: str):
    alice = _user(migrated_db, "alice@example.com")

    with pytest.raises(IntegrityError):
        _entry(migrated_db, alice, category=category)


@pytest.mark.parametrize("missing", ["date", "text", "category"])
def test_fr_e2_entry_without_date_text_or_category_is_rejected(migrated_db: Engine, missing: str):
    alice = _user(migrated_db, "alice@example.com")

    with pytest.raises(IntegrityError):
        _entry(migrated_db, alice, **{missing: None})


def test_entry_result_impact_may_be_empty(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    _entry(migrated_db, alice, result_impact=None)


@pytest.mark.parametrize("missing", ["period_start", "period_end", "text"])
def test_summary_without_period_or_text_is_rejected(migrated_db: Engine, missing: str):
    alice = _user(migrated_db, "alice@example.com")

    with pytest.raises(IntegrityError):
        _summary(migrated_db, alice, **{missing: None})


def test_summary_period_must_not_end_before_it_starts(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")

    with pytest.raises(IntegrityError):
        _summary(
            migrated_db, alice, period_start=dt.date(2026, 6, 1), period_end=dt.date(2026, 5, 1)
        )


def test_summary_stores_its_filter_as_values(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    summary = _summary(migrated_db, alice, filter_categories=[], filter_tags=["Python", "AWS"])

    with migrated_db.connect() as connection:
        row = connection.execute(
            select(Summary.filter_categories, Summary.filter_tags).where(Summary.id == summary)
        ).one()

    assert row.filter_categories == []
    assert row.filter_tags == ["Python", "AWS"]


# --- updated_at ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", [Entry, Summary])
def test_updated_at_changes_on_every_update(migrated_db: Engine, model):
    alice = _user(migrated_db, "alice@example.com")
    row_id = _entry(migrated_db, alice) if model is Entry else _summary(migrated_db, alice)
    columns = select(model.created_at, model.updated_at).where(model.id == row_id)
    with migrated_db.connect() as connection:
        before = connection.execute(columns).one()

    with migrated_db.begin() as connection:
        connection.execute(update(model).where(model.id == row_id).values(text="Edited"))
    with migrated_db.connect() as connection:
        after = connection.execute(columns).one()

    assert after.created_at == before.created_at
    assert after.updated_at > before.updated_at
    assert after.updated_at.tzinfo is not None


# --- Cascading deletes --------------------------------------------------------------------


def _rows_of(engine: Engine, user_id: uuid.UUID, entry_ids: list[uuid.UUID]) -> dict[str, int]:
    return {
        "entries": _count(
            engine, select(func.count()).select_from(Entry).where(Entry.user_id == user_id)
        ),
        "tags": _count(engine, select(func.count()).select_from(Tag).where(Tag.user_id == user_id)),
        "entry_tags": _count(
            engine,
            select(func.count()).select_from(EntryTag).where(EntryTag.entry_id.in_(entry_ids)),
        ),
        "summaries": _count(
            engine, select(func.count()).select_from(Summary).where(Summary.user_id == user_id)
        ),
        "ai_usage": _count(
            engine, select(func.count()).select_from(AiUsage).where(AiUsage.user_id == user_id)
        ),
        "users": _count(engine, select(func.count()).select_from(User).where(User.id == user_id)),
    }


def _user_with_data(engine: Engine, email: str) -> tuple[uuid.UUID, list[uuid.UUID]]:
    user = _user(engine, email)
    entry = _entry(engine, user)
    _link(engine, entry, _tag(engine, user, "Python"))
    _summary(engine, user)
    _ai_usage(engine, user)
    return user, [entry]


def test_fr_d2_deleting_a_user_removes_all_their_rows(migrated_db: Engine):
    alice, alice_entries = _user_with_data(migrated_db, "alice@example.com")
    bob, bob_entries = _user_with_data(migrated_db, "bob@example.com")

    with migrated_db.begin() as connection:
        connection.execute(delete(User).where(User.id == alice))

    assert set(_rows_of(migrated_db, alice, alice_entries).values()) == {0}
    assert set(_rows_of(migrated_db, bob, bob_entries).values()) == {1}


def test_deleting_an_entry_removes_its_links_but_keeps_the_tags(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    entry = _entry(migrated_db, alice)
    tag = _tag(migrated_db, alice, "Python")
    _link(migrated_db, entry, tag)

    with migrated_db.begin() as connection:
        connection.execute(delete(Entry).where(Entry.id == entry))

    assert _count(migrated_db, select(func.count()).select_from(EntryTag)) == 0
    assert _count(migrated_db, select(func.count()).select_from(Tag).where(Tag.id == tag)) == 1


def test_deleting_a_tag_removes_its_links_but_keeps_the_entry(migrated_db: Engine):
    alice = _user(migrated_db, "alice@example.com")
    entry = _entry(migrated_db, alice)
    tag = _tag(migrated_db, alice, "Python")
    _link(migrated_db, entry, tag)

    with migrated_db.begin() as connection:
        connection.execute(delete(Tag).where(Tag.id == tag))

    assert _count(migrated_db, select(func.count()).select_from(EntryTag)) == 0
    assert (
        _count(migrated_db, select(func.count()).select_from(Entry).where(Entry.id == entry)) == 1
    )
