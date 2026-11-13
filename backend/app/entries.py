"""Entries: creating (issue #9), reading, replacing and deleting an entry (issue #10), and
listing them with a filter (issue #11).

Operations `createEntry`, `getEntry`, `updateEntry`, `deleteEntry` and `listEntries` in
openapi.yaml. Covers FR-E1 to FR-E4, FR-R1 and FR-A3, and the acceptance criteria in
product-spec.md §7.1, §7.2, §7.3 and §7.4.

Create:

- One request always creates exactly one entry, whatever the text contains (FR-E1).
- The entry belongs to the user who owns the token. Fields the contract does not define, such
  as a user id, are ignored.
- The text is stored exactly as typed. Text that is empty or only whitespace counts as missing.
- A missing, empty or whitespace-only Result/Impact is stored as null.
- The date is required and never filled in by the API. Any real calendar date is accepted,
  including future dates.
- Tag names are resolved with `resolve_tags` in the entry's own transaction, so a failed save
  stores neither the entry nor any new tag (§7.3).
- Saving makes no AI call (§7.2).
- Maximum sizes (issue #43, product-spec.md §6): text up to `MAX_ENTRY_TEXT_CHARACTERS`,
  Result/Impact up to `MAX_RESULT_IMPACT_CHARACTERS` (also when it is only whitespace), up to
  `MAX_TAGS_PER_ENTRY` tags as sent, and tag names as `app.tags.TagName` says. Lengths are
  Unicode characters. A longer value is the shared validation error naming the field, and
  nothing is saved. Entries saved before the limits existed can be longer: they are still
  read and listed as they are, and only a new save is checked.

Read, update and delete (FR-E4, FR-A3):

- Every query is scoped to the authenticated user. Another user's entry gets the same
  `not_found` error as an id that does not exist, and stays unchanged.
- The entry id must be a UUID in the hyphenated form of `format: uuid`; anything else is the
  shared validation error naming `entryId`.
- Update is a full replacement with the same input and validation as create. The entry's tags
  become exactly the list sent, resolved in the same transaction. The row is always written,
  so the database trigger sets `updated_at` even if nothing changed. The last update wins.
- Tags that an update or delete unlinks stay in the database. The tag list (#8) hides the ones
  no entry uses any more.
- Saved summaries have no link to entries, so editing or deleting an entry never changes one.

List and filter (FR-R1, FR-A3):

- `filter_entries` is the one shared filter. The list endpoint uses it, and summary generation
  (#17) must use it too, so a summary is based on exactly the entries the list shows.
- Every filter is optional, and different filter types combine with AND. Both dates include
  their own day. Several categories, or several tags, match entries with any of them.
- Tag names are matched with #8's rules (`lookup_tags`): trimmed, inner spaces collapsed, and
  case ignored with PostgreSQL's `lower()`. A name the user has no tag for matches nothing.
  Both the entry and the tag must belong to the user, because the schema itself does not stop
  a link to another user's tag.
- Entries are sorted by date, newest first, then by creation time, newest first. Each entry
  appears once, and its tags are sorted as in `getEntry`. The list is flat and not paginated:
  the frontend groups it by category (FR-R2, #31).
- A start date after the end date is a validation error naming `end_date`, as `period_end`
  in openapi.yaml must not be before `period_start`.

The entry text and Result/Impact are never logged.
"""

import datetime as dt
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.exceptions import RequestValidationError
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict
from pydantic_core import PydanticCustomError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models
from app.auth import AuthenticateFirstRoute, CurrentUser
from app.db import get_session
from app.errors import ApiError
from app.tags import FilterTagName, TagName, lookup_tags, resolve_tags
from app.text_rules import at_most, is_blank, reject_unstorable_characters

router = APIRouter(tags=["Entries"], route_class=AuthenticateFirstRoute)

# The four categories of openapi.yaml (components.schemas.Category), as in models.CATEGORIES.
Category = Literal["Achievement", "Learning", "Feedback", "Side project"]

# product-spec.md §6 and openapi.yaml (`EntryInput`): counted in Unicode characters. Fixed rules
# of the data model, not settings (#43).
MAX_ENTRY_TEXT_CHARACTERS = 2_000
MAX_RESULT_IMPACT_CHARACTERS = 500
MAX_TAGS_PER_ENTRY = 10

# `format: date` in openapi.yaml: an RFC 3339 full-date, YYYY-MM-DD with ASCII digits.
_FULL_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

# `format: uuid` in openapi.yaml: the hyphenated 8-4-4-4-12 form, hex digits in either case.
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _require_full_date(value: Any) -> Any:
    """Accept only a YYYY-MM-DD string; pydantic then checks that it is a real date.

    Without this, pydantic would also accept a date-time such as `2026-11-08T00:00:00` or a
    Unix timestamp, which `format: date` does not allow.
    """
    if not isinstance(value, str) or not _FULL_DATE.fullmatch(value):
        raise PydanticCustomError("date_format", "Date must be a date in the format YYYY-MM-DD.")
    return value


def _require_uuid(value: Any) -> Any:
    """Accept only the hyphenated UUID form; pydantic then turns it into a UUID.

    Without this, pydantic would also accept forms that `format: uuid` does not allow, such as
    32 digits without hyphens, `{...}` or `urn:uuid:...`.
    """
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise PydanticCustomError(
            "uuid_format", "Must be a UUID in the format xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx."
        )
    return value


def _require_text(text: str) -> str:
    if is_blank(text):
        raise PydanticCustomError("text_missing", "Text must not be empty.")
    return text


def _blank_to_none(value: str | None) -> str | None:
    if value is None or is_blank(value):
        return None
    return value


EntryText = Annotated[
    str,
    AfterValidator(reject_unstorable_characters),
    AfterValidator(_require_text),
    AfterValidator(at_most(MAX_ENTRY_TEXT_CHARACTERS, "Text")),
]
"""An entry's text (and a suggestion request's text): required, not only whitespace, storable,
and at most `MAX_ENTRY_TEXT_CHARACTERS` characters."""
EntryDate = Annotated[dt.date, BeforeValidator(_require_full_date)]
EntryId = Annotated[uuid.UUID, BeforeValidator(_require_uuid), Path(alias="entryId")]
"""The `entryId` path parameter (components.parameters.EntryId)."""


def _reject_unstorable_optional(value: str | None) -> str | None:
    return value if value is None else reject_unstorable_characters(value)


_check_result_impact_length = at_most(MAX_RESULT_IMPACT_CHARACTERS, "Result/Impact")


def _check_result_impact_length_optional(value: str | None) -> str | None:
    return value if value is None else _check_result_impact_length(value)


# The length is checked before blank text becomes None, so an over-long Result/Impact that is
# only whitespace is rejected too (#43).
ResultImpact = Annotated[
    str | None,
    AfterValidator(_reject_unstorable_optional),
    AfterValidator(_check_result_impact_length_optional),
    AfterValidator(_blank_to_none),
]


def _check_tag_count(tags: list[str]) -> list[str]:
    # Counted as sent, before names that match each other become one tag (`maxItems: 10`).
    if len(tags) > MAX_TAGS_PER_ENTRY:
        raise PydanticCustomError(
            "too_many_tags", f"An entry can have at most {MAX_TAGS_PER_ENTRY} tags."
        )
    return tags


EntryTags = Annotated[list[TagName], AfterValidator(_check_tag_count)]


class EntryInput(BaseModel):
    """The request body for create and update."""

    # Fields the contract does not define, such as `user_id`, are ignored.
    model_config = ConfigDict(extra="ignore")

    text: EntryText
    date: EntryDate
    category: Category
    tags: EntryTags = []
    result_impact: ResultImpact = None


class Entry(BaseModel):
    """An entry as the API returns it (components.schemas.Entry)."""

    id: uuid.UUID
    date: dt.date
    text: str
    category: Category
    tags: list[str]
    result_impact: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


def _link_tags(session: Session, entry: models.Entry, tags: Sequence[models.Tag]) -> None:
    session.add_all(models.EntryTag(entry_id=entry.id, tag_id=tag.id) for tag in tags)
    session.flush()


def _to_api(entry: models.Entry, tag_names: list[str]) -> Entry:
    return Entry(
        id=entry.id,
        date=entry.date,
        text=entry.text,
        category=entry.category,
        tags=tag_names,
        result_impact=entry.result_impact,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def not_found() -> ApiError:
    """The same error for an entry that does not exist and another user's entry (FR-A3)."""
    return ApiError(404, "not_found", "Not found.")


def _own_entry(
    session: Session, user: models.User, entry_id: uuid.UUID, *, for_update: bool = False
) -> models.Entry:
    """The user's entry with this id, or `not_found`. Never returns another user's entry."""
    query = select(models.Entry).where(models.Entry.id == entry_id, models.Entry.user_id == user.id)
    if for_update:
        # Concurrent updates of one entry wait for each other, so the last one wins whole.
        query = query.with_for_update()
    entry = session.scalars(query).one_or_none()
    if entry is None:
        raise not_found()
    return entry


def _tag_names(session: Session, entry: models.Entry) -> list[str]:
    """Names of the entry's tags, sorted like the tag list: alphabetically, ignoring case.

    Only the entry owner's tags count, as in the tag list (#8): the schema itself does not
    stop a link to another user's tag.
    """
    return list(
        session.scalars(
            select(models.Tag.name)
            .join(models.EntryTag, models.EntryTag.tag_id == models.Tag.id)
            .where(models.EntryTag.entry_id == entry.id, models.Tag.user_id == entry.user_id)
            .order_by(func.lower(models.Tag.name), models.Tag.name)
        )
    )


class EntryList(BaseModel):
    """The list response (components.schemas.EntryList)."""

    entries: list[Entry]


@dataclass(frozen=True)
class EntryFilter:
    """A filter for the user's entries (FR-R1). Every part is optional.

    `None` for a date, or an empty list of categories or tags, means no restriction. Callers
    validate the parts first: dates are real dates with the start not after the end, the
    categories are among the four, and tag names have no character the database cannot store.
    """

    start_date: dt.date | None = None
    end_date: dt.date | None = None
    categories: Sequence[str] = ()
    tags: Sequence[str] = ()


def _sorted_tag_names():
    """For each entry in the outer query: its tag names, sorted as in `_tag_names`.

    Only the entry owner's tags count. An entry without tags gets NULL.
    """
    return (
        select(
            func.array_agg(
                aggregate_order_by(models.Tag.name, func.lower(models.Tag.name), models.Tag.name)
            )
        )
        .select_from(models.EntryTag)
        .join(models.Tag, models.Tag.id == models.EntryTag.tag_id)
        .where(
            models.EntryTag.entry_id == models.Entry.id,
            models.Tag.user_id == models.Entry.user_id,
        )
        .scalar_subquery()
    )


def filter_entries(session: Session, user: models.User, entry_filter: EntryFilter) -> list[Entry]:
    """The user's entries that match the filter, newest first (FR-R1, FR-A3).

    The one shared filter: the list endpoint and summary generation (#17) both use it. Only
    the user's own entries are returned, and a tag filter only uses the user's own tags, so
    another user's tag name matches nothing. An entry that has several of the tags appears
    once. Sorted by date, newest first, then by creation time, newest first (the id only
    makes the order stable if both are equal).
    """
    query = select(models.Entry, _sorted_tag_names()).where(models.Entry.user_id == user.id)
    if entry_filter.start_date is not None:
        query = query.where(models.Entry.date >= entry_filter.start_date)
    if entry_filter.end_date is not None:
        query = query.where(models.Entry.date <= entry_filter.end_date)
    if entry_filter.categories:
        query = query.where(models.Entry.category.in_(list(entry_filter.categories)))
    if entry_filter.tags:
        # #8's rules: normalised, matched ignoring case with PostgreSQL's lower(), and only
        # among the user's own tags. Names the user has no tag for are left out.
        tag_ids = [tag.id for tag in lookup_tags(session, user, entry_filter.tags)]
        if not tag_ids:
            return []
        has_a_tag = (
            select(models.EntryTag.entry_id)
            .where(
                models.EntryTag.entry_id == models.Entry.id,
                models.EntryTag.tag_id.in_(tag_ids),
            )
            .exists()
        )
        query = query.where(has_a_tag)
    query = query.order_by(
        models.Entry.date.desc(), models.Entry.created_at.desc(), models.Entry.id.desc()
    )
    return [_to_api(entry, tag_names or []) for entry, tag_names in session.execute(query)]


def _period_out_of_order() -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "date_order",
                "loc": ("query", "end_date"),
                "msg": "End date must not be before the start date.",
                "input": None,
            }
        ]
    )


@router.get(
    "/entries",
    operation_id="listEntries",
    summary="List the user's entries, optionally filtered.",
    response_model=EntryList,
)
def list_entries(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
    start_date: Annotated[EntryDate | None, Query()] = None,
    end_date: Annotated[EntryDate | None, Query()] = None,
    # Repeated parameters (`?tag=a&tag=b`), because tag names can contain commas.
    category: Annotated[list[Category] | None, Query()] = None,
    tag: Annotated[list[FilterTagName] | None, Query()] = None,
) -> EntryList:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise _period_out_of_order()
    entry_filter = EntryFilter(
        start_date=start_date,
        end_date=end_date,
        categories=category or (),
        tags=tag or (),
    )
    return EntryList(entries=filter_entries(session, user, entry_filter))


@router.post(
    "/entries",
    operation_id="createEntry",
    summary="Create an entry.",
    status_code=201,
    response_model=Entry,
)
def create_entry(
    entry_input: EntryInput,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Entry:
    entry = models.Entry(
        user_id=user.id,
        date=entry_input.date,
        text=entry_input.text,
        category=entry_input.category,
        result_impact=entry_input.result_impact,
    )
    session.add(entry)
    session.flush()
    # Same transaction as the entry: if anything below fails, the session rolls back and
    # neither the entry nor the new tags are stored.
    tags = resolve_tags(session, user, entry_input.tags)
    _link_tags(session, entry, tags)
    tag_names = [tag.name for tag in tags]
    session.commit()
    return _to_api(entry, tag_names)


@router.get(
    "/entries/{entryId}",
    operation_id="getEntry",
    summary="Get one of the user's entries.",
    response_model=Entry,
)
def get_entry(
    entry_id: EntryId,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Entry:
    entry = _own_entry(session, user, entry_id)
    return _to_api(entry, _tag_names(session, entry))


@router.put(
    "/entries/{entryId}",
    operation_id="updateEntry",
    summary="Replace one of the user's entries.",
    response_model=Entry,
)
def update_entry(
    entry_id: EntryId,
    entry_input: EntryInput,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Entry:
    # The input is already valid here: an invalid request never reaches this point, so it
    # changes nothing. A missing or other user's entry is rejected before any tag is resolved.
    entry = _own_entry(session, user, entry_id, for_update=True)
    entry.date = entry_input.date
    entry.text = entry_input.text
    entry.category = entry_input.category
    entry.result_impact = entry_input.result_impact
    # Write the row even if every value is the same, so the trigger sets `updated_at`.
    flag_modified(entry, "text")
    session.flush()
    # Full replacement of the tags, in the same transaction as the entry: if anything below
    # fails, the session rolls back, the entry keeps its old values and no new tag is stored.
    session.execute(delete(models.EntryTag).where(models.EntryTag.entry_id == entry.id))
    tags = resolve_tags(session, user, entry_input.tags)
    _link_tags(session, entry, tags)
    tag_names = [tag.name for tag in tags]
    session.commit()
    return _to_api(entry, tag_names)


@router.delete(
    "/entries/{entryId}",
    operation_id="deleteEntry",
    summary="Delete one of the user's entries.",
    status_code=204,
    response_class=Response,
)
def delete_entry(
    entry_id: EntryId,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    # The entry's tag links go with it (ON DELETE CASCADE); the tags themselves stay.
    deleted = session.scalar(
        delete(models.Entry)
        .where(models.Entry.id == entry_id, models.Entry.user_id == user.id)
        .returning(models.Entry.id)
    )
    if deleted is None:
        raise not_found()
    session.commit()
    return Response(status_code=204)
