"""Tags: the name rules, the shared resolve and lookup functions, and the tag list (issue #8).

Covers FR-E3, FR-A3 and the tag rules in docs/product-spec.md §7.2, §7.3 and §10.5.

Name rules:

- A name is trimmed, and every run of whitespace inside it becomes one space.
- Names are matched without regard to case, with PostgreSQL's `lower()`, the same function
  the unique index `uq_tags_user_id_lower_name` uses. A tag keeps the spelling it was first
  created with.
- A name that is empty after trimming is invalid. Request models use `TagName`, which turns
  it into the shared validation error naming the field (for example `tags.1`). `TagName` also
  rejects NUL and unpaired surrogates, which the database cannot store (app/text_rules.py).
- A name has at most `MAX_TAG_NAME_CHARACTERS` characters, measured as sent (issue #43).
  Cleaning only makes a name shorter, so a stored name is never longer. Filter names
  (`FilterTagName`) have the same limit.
- A filter holds at most `MAX_FILTER_TAG_NAMES` names (`FilterTagNames`, issue #88), in
  `GET /entries` and in `POST /summaries`. They are counted as sent, before any cleaning, so
  duplicates, names that differ only in case and names that are empty after trimming all
  count. A saved summary's filter is not checked: summaries saved before the limit can hold
  more names.

`resolve_tags` (entry create and update) and `lookup_tags` (suggestions) are the only places
that turn names into tag records. Both only ever read or create the given user's tags.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import AfterValidator, BaseModel, BeforeValidator
from pydantic_core import PydanticCustomError
from sqlalchemy import Text, column, func, select, values
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import AuthenticateFirstRoute, CurrentUser
from app.db import get_session
from app.models import Entry, EntryTag, Tag, User
from app.text_rules import at_most, reject_unstorable_characters

router = APIRouter(tags=["Tags"], route_class=AuthenticateFirstRoute)


def normalise_tag_name(name: str) -> str:
    """Trim the name and turn every run of whitespace inside it into one space."""
    return " ".join(name.split())


# product-spec.md §6 and openapi.yaml (`maxLength: 40` on tag names): counted in Unicode
# characters, as sent. A fixed rule of the data model, not a setting.
MAX_TAG_NAME_CHARACTERS = 40

_check_tag_name_length = at_most(MAX_TAG_NAME_CHARACTERS, "Tag name")


def _validate_tag_name(name: str) -> str:
    reject_unstorable_characters(name)
    # As sent, before cleaning, so the contract's maxLength is exact (#43).
    _check_tag_name_length(name)
    normalised = normalise_tag_name(name)
    if not normalised:
        raise PydanticCustomError("tag_name_empty", "Tag name must not be empty.")
    return normalised


TagName = Annotated[str, AfterValidator(_validate_tag_name)]
"""A tag name in a request model: normalised, and a validation error if it is empty, longer
than `MAX_TAG_NAME_CHARACTERS` as sent, or has a character the database cannot store."""

FilterTagName = Annotated[
    str, AfterValidator(reject_unstorable_characters), AfterValidator(_check_tag_name_length)
]
"""A tag name to filter by (issue #11): a validation error only if it has a character the
database cannot store or is longer than `MAX_TAG_NAME_CHARACTERS` as sent (#43).
`lookup_tags` normalises it; a name that no tag has, including one that is empty after
trimming, matches nothing and is not an error."""

# openapi.yaml (`maxItems: 20` on the `tag` parameter of `listEntries` and on
# `SummaryFilter.tags`): the most tag names one filter holds, counted as sent (issue #88). A
# fixed rule of the contract, not a setting. Twice the tags of one entry, and the largest
# valid `GET /entries` URL with it (about 9.8 KB) stays well within uvicorn's 16 KiB for the
# request line and headers.
MAX_FILTER_TAG_NAMES = 20


def _check_filter_tag_count(value: object) -> object:
    # Counted as sent, before each name is checked or cleaned, so `maxItems` is exact. A value
    # that is not a list is left to the list validator.
    if isinstance(value, list) and len(value) > MAX_FILTER_TAG_NAMES:
        raise PydanticCustomError(
            "too_many_tags", f"A filter can have at most {MAX_FILTER_TAG_NAMES} tag names."
        )
    return value


FilterTagNames = Annotated[list[FilterTagName], BeforeValidator(_check_filter_tag_count)]
"""The tag names of a filter (issue #88): at most `MAX_FILTER_TAG_NAMES` as sent, each a
`FilterTagName`. Too many names is a validation error naming the whole list."""


def match_keys(session: Session, names: Sequence[str]) -> dict[str, str]:
    """PostgreSQL's lower() of each name, so matching follows exactly the index's rule.

    Python's str.lower() differs from PostgreSQL's lower() for some characters (for example
    a final Greek sigma), so the comparison key always comes from the database.
    """
    given = values(column("name", Text), name="given_names").data([(name,) for name in names])
    rows = session.execute(select(given.c.name, func.lower(given.c.name)))
    return {name: key for name, key in rows}


def _unique_by_key(session: Session, names: Sequence[str]) -> dict[str, str]:
    """Normalised names keyed by their match key, first spelling first, in input order."""
    normalised = [normalise_tag_name(name) for name in names]
    normalised = [name for name in normalised if name]
    if not normalised:
        return {}
    keys = match_keys(session, normalised)
    unique: dict[str, str] = {}
    for name in normalised:
        unique.setdefault(keys[name], name)
    return unique


def _existing_by_key(session: Session, user: User, keys: Sequence[str]) -> dict[str, Tag]:
    rows = session.execute(
        select(Tag, func.lower(Tag.name)).where(
            Tag.user_id == user.id, func.lower(Tag.name).in_(keys)
        )
    ).all()
    return {key: tag for tag, key in rows}


def lookup_tags(session: Session, user: User, names: Sequence[str]) -> list[Tag]:
    """The user's tags that match the names, ignoring case. Creates nothing.

    Names without a matching tag, and names that are empty after trimming, are left out.
    The result follows the order of the names, with each tag once.
    """
    unique = _unique_by_key(session, names)
    if not unique:
        return []
    existing = _existing_by_key(session, user, list(unique))
    return [existing[key] for key in unique if key in existing]


def resolve_tags(session: Session, user: User, names: Sequence[str]) -> list[Tag]:
    """The user's tags for the names, creating the ones the user does not have yet.

    Matching ignores case, and an existing tag (used or not) keeps its spelling. A name given
    several times becomes one tag. The result follows the order of the names, with each tag
    once.

    Runs in the caller's transaction and does not commit: if the caller rolls back, for
    example because the entry cannot be saved, the new tags are gone too (§7.3).

    Two transactions creating the same new tag at the same time both end up with the one tag:
    `ON CONFLICT DO NOTHING` makes the second insert wait for the first transaction and then
    skip the row, and the select that follows sees the committed tag. New rows are inserted
    in key order, so two transactions with several new tags cannot deadlock.

    Raises ValueError for a name that is empty after trimming; request models reject those
    first with `TagName`.
    """
    if any(not normalise_tag_name(name) for name in names):
        raise ValueError("Tag names must not be empty.")
    unique = _unique_by_key(session, names)
    if not unique:
        return []
    keys = list(unique)
    existing = _existing_by_key(session, user, keys)
    missing = sorted(key for key in keys if key not in existing)
    if missing:
        session.execute(
            insert(Tag)
            .values([{"user_id": user.id, "name": unique[key]} for key in missing])
            .on_conflict_do_nothing(index_elements=[Tag.user_id, func.lower(Tag.name)])
        )
        existing = _existing_by_key(session, user, keys)
    return [existing[key] for key in keys]


def used_tag_names(session: Session, user_id: uuid.UUID) -> list[str]:
    """Names of the user's tags that at least one of the user's entries uses.

    Sorted alphabetically without regard to case. Tags that no entry uses stay in the
    database but are left out. Both the tag and the entry must belong to the user.
    """
    used = (
        select(EntryTag.tag_id)
        .join(Entry, Entry.id == EntryTag.entry_id)
        .where(EntryTag.tag_id == Tag.id, Entry.user_id == user_id)
        .exists()
    )
    return list(
        session.scalars(
            select(Tag.name)
            .where(Tag.user_id == user_id, used)
            .order_by(func.lower(Tag.name), Tag.name)
        )
    )


class TagList(BaseModel):
    tags: list[str]


@router.get(
    "/tags",
    operation_id="listTags",
    summary="List the user's tags that at least one entry uses.",
    response_model=TagList,
)
def list_tags(user: CurrentUser, session: Annotated[Session, Depends(get_session)]) -> TagList:
    return TagList(tags=used_tag_names(session, user.id))
