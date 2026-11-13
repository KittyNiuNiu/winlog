"""Saved summaries: generating and saving one (issue #17), and listing, reading, editing and
deleting them (issue #18).

Operations `generateSummary`, `listSummaries`, `getSummary`, `updateSummary` and
`deleteSummary` in openapi.yaml. Covers FR-R3, FR-R4, FR-R5 and FR-A3, and the acceptance
criteria in product-spec.md §7.4 and §8.

Generate (#17):

- The request needs a valid token. Without one, the request gets `not_authenticated` and no
  AI call is made: authentication runs before the endpoint.
- The filter has a period start and end (both required, real dates in the format
  YYYY-MM-DD), and optional categories and tag names. A start after the end, a missing or
  invalid date, an invalid category, or a tag name with a character the database cannot store
  or with more than 40 characters (#43) is the shared validation error, which counts against
  no limit.
- Entries are selected with #11's shared `filter_entries`, so a summary is based on exactly
  the entries the list endpoint returns for the same filter. Only the user's own entries and
  tags count, so another user's tag name matches nothing (FR-A3).
- No matching entries is the 422 `no_matching_entries` error: no AI call, nothing counted,
  nothing saved (§7.4).
- Too much text is the 422 `summary_input_too_large` error (issue #43): the matching entries'
  text, Result/Impact and tag names, added up in Unicode characters, are more than the
  `AI_SUMMARY_MAX_INPUT_CHARACTERS` setting. No AI call, nothing counted, nothing saved.
  Exactly at the limit, the summary is generated. The checks run in this order: request
  validation, `no_matching_entries`, `summary_input_too_large`, then the daily limits.
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

List, get, edit and delete (#18, FR-R5, FR-A3):

- Every query is scoped to the authenticated user. Another user's summary gets the same
  `not_found` error as an id that does not exist, and stays unchanged. The list shows only
  the user's own summaries, newest first by creation time, and is not paginated.
- The summary id must be a UUID in the hyphenated form of `format: uuid`, as for entries;
  anything else is the shared validation error naming `summaryId`.
- Editing changes only the text, which is stored exactly as typed. Missing text, text that
  is empty or only whitespace, or text over `MAX_SUMMARY_CHARACTERS` (10,000 Unicode
  characters, #43) is the validation error and changes nothing. Other fields in
  the request, such as the filter, are ignored, so the stored filter never changes. The row is
  always written, so the database trigger sets `updated_at` even if the text is the same, and
  concurrent edits of one summary wait for each other: the last one wins.
- Summaries have no link to entries, so editing or deleting a summary never changes an entry
  (§7.4). Deleting answers 204; deleting the same summary again is `not_found`.
- A summary saved before #43 can be longer than 10,000 characters. It is still listed and read
  as it is; only a new edit is checked.

Telemetry (issue #74): generating a summary is the instrumented key user journey. The request's
SERVER span gets the child spans `summary.select_entries`, `ai.limits.reserve`, `ai.summarise`
and `summary.save` (as far as the request gets), and each of the five outcomes (`created`,
`no_matching_entries`, `summary_input_too_large`, `limit_reached`, `ai_unavailable`) is counted,
set on the SERVER span and logged (`app.telemetry.summary_generation_finished`). Only the
outcome and the number of entries are recorded.

Privacy: nothing here is logged except that outcome and number. Entry text and summary text
never appear in a log or an error message, and the AI error is not chained to the
`ai_unavailable` error, so the provider's exception (which may repeat entry text) cannot reach a
traceback (`AGENTS.md`).
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app import models, telemetry
from app.ai import AIError, AILimitReachedError, LimitedAIDependency, SummaryEntry
from app.ai.adapter import MAX_SUMMARY_CHARACTERS
from app.auth import AuthenticateFirstRoute, CurrentUser
from app.db import get_session
from app.entries import (
    Category,
    EntryDate,
    EntryFilter,
    _require_text,
    _require_uuid,
    filter_entries,
    not_found,
)
from app.errors import ApiError
from app.settings import Settings
from app.suggestions import ai_unavailable
from app.tags import FilterTagName, lookup_tags, match_keys, normalise_tag_name
from app.text_rules import at_most, reject_unstorable_characters

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


class SummaryList(BaseModel):
    """The list response (components.schemas.SummaryList)."""

    summaries: list[Summary]


SummaryText = Annotated[
    str,
    AfterValidator(reject_unstorable_characters),
    AfterValidator(_require_text),
    AfterValidator(at_most(MAX_SUMMARY_CHARACTERS, "Summary text")),
]
"""Edited summary text: the entry text rules, with the summary's own maximum length (#43)."""


class SummaryUpdate(BaseModel):
    """The request body for editing a summary (components.schemas.SummaryUpdate).

    The text follows the same rules as an entry's text: required, kept exactly as typed, not
    empty or only whitespace (`pattern: '\\S'`), and without characters the database cannot
    store. Its maximum length is the summary's, `MAX_SUMMARY_CHARACTERS` (#43). Every other
    field, such as the filter, is ignored: only the text can change.
    """

    model_config = ConfigDict(extra="ignore")

    text: SummaryText


SummaryId = Annotated[uuid.UUID, BeforeValidator(_require_uuid), Path(alias="summaryId")]
"""The `summaryId` path parameter (components.parameters.SummaryId)."""


def no_matching_entries() -> ApiError:
    """openapi.yaml's 422 `no_matching_entries` error (§7.4: the user is told why)."""
    return ApiError(
        422,
        "no_matching_entries",
        "No entries match this filter, so no summary was generated.",
    )


def summary_input_too_large() -> ApiError:
    """openapi.yaml's 422 `summary_input_too_large` error: the user should narrow the filter."""
    return ApiError(
        422,
        "summary_input_too_large",
        "The matching entries are too large to summarise in one request. Narrow the filter.",
    )


def summary_input_characters(entries: Sequence[SummaryEntry]) -> int:
    """The size of a summary request: each entry's text, Result/Impact and tag names, added up.

    Counted in Unicode characters, as every limit of #43. The date and category are left out:
    they are short and the same for every entry.
    """
    return sum(
        len(entry.text) + len(entry.result_impact or "") + sum(map(len, entry.tags))
        for entry in entries
    )


def summary_input_limit(request: Request) -> int:
    """FastAPI dependency: the `AI_SUMMARY_MAX_INPUT_CHARACTERS` setting of the app."""
    settings: Settings = request.app.state.settings
    return settings.ai_summary_max_input_characters


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
    max_input_characters: Annotated[int, Depends(summary_input_limit)],
) -> Summary:
    # `filter_entries` expects a valid filter: it does not check the period order (#11).
    # Request validation, like this check, comes before the journey's outcomes are counted.
    if body.period_start > body.period_end:
        raise _period_out_of_order()
    with telemetry.span("summary.select_entries") as span:
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
        span.set("winlog.entry_count", len(entries))
    if not entries:
        # Before the limited entry point: no AI call, nothing counted, nothing saved (§7.4).
        telemetry.summary_generation_finished("no_matching_entries", 0)
        raise no_matching_entries()
    summary_entries = [SummaryEntry.from_entry(entry) for entry in entries]
    if summary_input_characters(summary_entries) > max_input_characters:
        # Also before the limited entry point, so it never counts against a daily limit (#43).
        telemetry.summary_generation_finished("summary_input_too_large", len(entries))
        raise summary_input_too_large()
    categories = _unique(body.categories)
    tag_names = filter_tag_names(session, user, body.tags)
    # The AI call can take many seconds. Close the session first, so no database connection
    # or transaction is held during it. The user stays loaded, and the session opens a new
    # connection to save the summary.
    session.close()
    try:
        text = ai.summarise(user.id, summary_entries)
    except AILimitReachedError:
        telemetry.summary_generation_finished("limit_reached", len(entries))
        raise
    except AIError:
        telemetry.summary_generation_finished("ai_unavailable", len(entries))
        # `from None`: the provider's exception may repeat entry text, so it must not appear
        # as the cause or context of this error in any traceback. Nothing is saved.
        raise ai_unavailable() from None
    with telemetry.span("summary.save"):
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
    telemetry.summary_generation_finished("created", len(entries))
    # Committing expires the row, so this reads back the id and the timestamps the database set.
    return _to_api(summary)


def _own_summary(
    session: Session, user: models.User, summary_id: uuid.UUID, *, for_update: bool = False
) -> models.Summary:
    """The user's summary with this id, or `not_found`. Never returns another user's summary."""
    query = select(models.Summary).where(
        models.Summary.id == summary_id, models.Summary.user_id == user.id
    )
    if for_update:
        # Concurrent edits of one summary wait for each other, so the last one wins whole.
        query = query.with_for_update()
    summary = session.scalars(query).one_or_none()
    if summary is None:
        raise not_found()
    return summary


def user_summaries(session: Session, user: models.User) -> list[Summary]:
    """All of the user's summaries, newest first by creation time (FR-R5, FR-A3).

    The list endpoint and the data export (#19) both use it. The id only makes the order
    stable for summaries created at the same moment.
    """
    rows = session.scalars(
        select(models.Summary)
        .where(models.Summary.user_id == user.id)
        .order_by(models.Summary.created_at.desc(), models.Summary.id.desc())
    )
    return [_to_api(summary) for summary in rows]


@router.get(
    "/summaries",
    operation_id="listSummaries",
    summary="List the user's saved summaries.",
    response_model=SummaryList,
)
def list_summaries(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> SummaryList:
    return SummaryList(summaries=user_summaries(session, user))


@router.get(
    "/summaries/{summaryId}",
    operation_id="getSummary",
    summary="Get one of the user's summaries.",
    response_model=Summary,
)
def get_summary(
    summary_id: SummaryId,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Summary:
    return _to_api(_own_summary(session, user, summary_id))


@router.patch(
    "/summaries/{summaryId}",
    operation_id="updateSummary",
    summary="Change the text of one of the user's summaries.",
    response_model=Summary,
)
def update_summary(
    summary_id: SummaryId,
    body: SummaryUpdate,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Summary:
    # The input is already valid here: an invalid request never reaches this point, so it
    # changes nothing. Only the text is written; the filter and every entry stay as they are.
    summary = _own_summary(session, user, summary_id, for_update=True)
    summary.text = body.text
    # Write the row even if the text is the same, so the trigger sets `updated_at`.
    flag_modified(summary, "text")
    session.commit()
    # Committing expires the row, so this reads back the `updated_at` the trigger set.
    return _to_api(summary)


@router.delete(
    "/summaries/{summaryId}",
    operation_id="deleteSummary",
    summary="Delete one of the user's summaries.",
    status_code=204,
    response_class=Response,
)
def delete_summary(
    summary_id: SummaryId,
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    deleted = session.scalar(
        delete(models.Summary)
        .where(models.Summary.id == summary_id, models.Summary.user_id == user.id)
        .returning(models.Summary.id)
    )
    if deleted is None:
        raise not_found()
    session.commit()
    return Response(status_code=204)
