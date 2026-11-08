"""Entries: creating an entry (`createEntry` in openapi.yaml, issue #9).

Covers FR-E1, FR-E2 and FR-E3, and the acceptance criteria in product-spec.md §7.2 and §7.3.

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

The entry text and Result/Impact are never logged.
"""

import datetime as dt
import re
import uuid
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session

from app import models
from app.auth import CurrentUser
from app.db import get_session
from app.tags import TagName, resolve_tags
from app.text_rules import is_blank, reject_unstorable_characters

router = APIRouter(tags=["Entries"])

# The four categories of openapi.yaml (components.schemas.Category), as in models.CATEGORIES.
Category = Literal["Achievement", "Learning", "Feedback", "Side project"]

# `format: date` in openapi.yaml: an RFC 3339 full-date, YYYY-MM-DD with ASCII digits.
_FULL_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _require_full_date(value: Any) -> Any:
    """Accept only a YYYY-MM-DD string; pydantic then checks that it is a real date.

    Without this, pydantic would also accept a date-time such as `2026-11-08T00:00:00` or a
    Unix timestamp, which `format: date` does not allow.
    """
    if not isinstance(value, str) or not _FULL_DATE.fullmatch(value):
        raise PydanticCustomError("date_format", "Date must be a date in the format YYYY-MM-DD.")
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
    str, AfterValidator(reject_unstorable_characters), AfterValidator(_require_text)
]
EntryDate = Annotated[dt.date, BeforeValidator(_require_full_date)]


def _reject_unstorable_optional(value: str | None) -> str | None:
    return value if value is None else reject_unstorable_characters(value)


ResultImpact = Annotated[
    str | None, AfterValidator(_reject_unstorable_optional), AfterValidator(_blank_to_none)
]


class EntryInput(BaseModel):
    """The request body for create (and, in #10, update)."""

    # Fields the contract does not define, such as `user_id`, are ignored.
    model_config = ConfigDict(extra="ignore")

    text: EntryText
    date: EntryDate
    category: Category
    tags: list[TagName] = []
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
