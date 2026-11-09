"""Generating a summary of the entries matching a filter, and saving it (issue #17).

Operation `generateSummary` in openapi.yaml. Covers FR-R3, FR-R4 and FR-A3, and the
acceptance criteria in product-spec.md §7.4 and §8.

- The request needs a valid token. Without one, the request gets `not_authenticated` and no
  AI call is made: authentication runs before the endpoint.
- The filter has a period start and end (both required, real dates in the format
  YYYY-MM-DD), and optional categories and tag names. A start after the end, a missing or
  invalid date, an invalid category, or a tag name with a character the database cannot store
  is the shared validation error, which counts against no limit.
- Entries are selected with #11's shared `filter_entries`, so a summary is based on exactly
  the entries the list endpoint returns for the same filter. Only the user's own entries and
  tags count, so another user's tag name matches nothing (FR-A3).
- No matching entries is the 422 `no_matching_entries` error: no AI call, nothing counted,
  nothing saved (§7.4).
- The AI is called only through the limited entry point (`LimitedAIDependency`, issue #15),
  so the daily limits are checked before the call. A reached limit is the 429
  `limit_reached` error naming the limit.
- The AI receives the matching entries as `SummaryEntry` objects: date, category, text,
  Result/Impact and tag names, and nothing else (§8).
- An AI timeout or provider failure is the 503 `ai_unavailable` error, and nothing is saved.
- The summary is saved together with its filter (FR-R4): the period, the categories (each
  once, in the order given) and the tag names cleaned with #8's rules. A name that matches one
  of the user's tags, ignoring case, gets that tag's stored spelling; names that match each
  other are kept once, first one first; names that are empty after cleaning match nothing and
  are left out. The response is the saved summary, with status 201.
- Generating changes no entry and no tag. Only the summary and #15's usage counts are written.

Privacy: nothing here is logged. Entry text and summary text never appear in a log or an
error message, and the AI error is not chained to the `ai_unavailable` error, so the
provider's exception (which may repeat entry text) cannot reach a traceback (`AGENTS.md`).
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app import models
from app.ai import AIError, LimitedAIDependency, SummaryEntry
from app.auth import AuthenticateFirstRoute, CurrentUser
from app.db import get_session
from app.entries import Category, EntryDate, EntryFilter, filter_entries
from app.errors import ApiError
from app.suggestions import ai_unavailable
from app.tags import FilterTagName, lookup_tags, match_keys, normalise_tag_name

router = APIRouter(tags=["Summaries"], route_class=AuthenticateFirstRoute)


class SummaryFilter(BaseModel):
    """The filter a summary is generated from and saved with (components.schemas.SummaryFilter).

    `categories` and `tags` may be missing or empty, which means no restriction. Tag names
    only have to be storable here: like the list filter (#11), a name the user has no tag
    for, including one that is empty after trimming, matches nothing and is not an error.
    """

    # Fields the contract does not define, such as a user id, are ignored.
    model_config = ConfigDict(extra="ignore")

    period_start: EntryDate
    period_end: EntryDate
    categories: list[Category] = []
    tags: list[FilterTagName] = []


class Summary(BaseModel):
    """A saved summary as the API returns it (components.schemas.Summary)."""

    id: uuid.UUID
    text: str
    filter: SummaryFilter
    created_at: dt.datetime
    updated_at: dt.datetime


def no_matching_entries() -> ApiError:
    """openapi.yaml's 422 `no_matching_entries` error (§7.4: the user is told why)."""
    return ApiError(
        422,
        "no_matching_entries",
        "No entries match this filter, so no summary was generated.",
    )


def _period_out_of_order() -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "date_order",
                "loc": ("body", "period_end"),
                "msg": "Period end must not be before the period start.",
                "input": None,
            }
        ]
    )


def _unique[T](values: Sequence[T]) -> list[T]:
    """The values, each once, first one first."""
    return list(dict.fromkeys(values))


def filter_tag_names(session: Session, user: models.User, names: Sequence[str]) -> list[str]:
    """The tag names to save with a summary's filter, cleaned with #8's rules.

    Each name is cleaned (trimmed, inner whitespace collapsed), and names that are empty after
    cleaning are left out: they match nothing. A name that matches one of the user's tags,
    ignoring case as #8 does, gets the tag's stored spelling; other names keep their cleaned
    spelling. Names that match each other are kept once, first one first. Reads only the
    user's own tags and creates nothing.
    """
    cleaned = [name for name in map(normalise_tag_name, names) if name]
    if not cleaned:
        return []
    existing = lookup_tags(session, user, cleaned)
    # The match key of a stored tag is the key the lookup matched it on.
    keys = match_keys(session, [*cleaned, *(tag.name for tag in existing)])
    stored = {keys[tag.name]: tag.name for tag in existing}
    result: dict[str, str] = {}
    for name in cleaned:
        result.setdefault(keys[name], stored.get(keys[name], name))
    return list(result.values())


def _to_api(summary: models.Summary) -> Summary:
    return Summary(
        id=summary.id,
        text=summary.text,
        # Stored values were validated before they were saved. The request rules, such as
        # dates given as YYYY-MM-DD text, do not apply to them.
        filter=SummaryFilter.model_construct(
            period_start=summary.period_start,
            period_end=summary.period_end,
            categories=list(summary.filter_categories),
            tags=list(summary.filter_tags),
        ),
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


@router.post(
    "/summaries",
    operation_id="generateSummary",
    summary="Generate a summary of the entries matching a filter and save it.",
    status_code=201,
    response_model=Summary,
)
def generate_summary(
    body: SummaryFilter,
    user: CurrentUser,
    ai: LimitedAIDependency,
    session: Annotated[Session, Depends(get_session)],
) -> Summary:
    # `filter_entries` expects a valid filter: it does not check the period order (#11).
    if body.period_start > body.period_end:
        raise _period_out_of_order()
    entries = filter_entries(
        session,
        user,
        EntryFilter(
            start_date=body.period_start,
            end_date=body.period_end,
            categories=body.categories,
            tags=body.tags,
        ),
    )
    if not entries:
        # Before the limited entry point: no AI call, nothing counted, nothing saved (§7.4).
        raise no_matching_entries()
    categories = _unique(body.categories)
    tag_names = filter_tag_names(session, user, body.tags)
    # The AI call can take many seconds. Close the session first, so no database connection
    # or transaction is held during it. The user stays loaded, and the session opens a new
    # connection to save the summary.
    session.close()
    try:
        text = ai.summarise(user.id, [SummaryEntry.from_entry(entry) for entry in entries])
    except AIError:
        # `from None`: the provider's exception may repeat entry text, so it must not appear
        # as the cause or context of this error in any traceback. Nothing is saved.
        raise ai_unavailable() from None
    summary = models.Summary(
        user_id=user.id,
        period_start=body.period_start,
        period_end=body.period_end,
        filter_categories=categories,
        filter_tags=tag_names,
        text=text,
    )
    session.add(summary)
    session.commit()
    # Committing expires the row, so this reads back the id and the timestamps the database set.
    return _to_api(summary)
