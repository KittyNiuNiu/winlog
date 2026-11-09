"""Daily AI usage limits: the one limited entry point for AI calls (issue #15, §8).

Features never call the AI adapter directly. They depend on `LimitedAIDependency` and call
`LimitedAI.suggest` or `LimitedAI.summarise`, which checks the limits before every AI call:

1. The input is checked as the adapter checks it. A request stopped here counts nothing.
2. In one database transaction, the user's count for the day and request type goes up by
   one, but only while it is below the user's limit. Then the global count for the day goes
   up by one, but only while it is below the global cap. If either limit is reached, the
   transaction is rolled back, so neither count changes, and `AILimitReachedError` names the
   limit. The transaction commits before the AI call, so the AI call never holds a lock.
3. The adapter is called. A call that fails or times out has already been counted.

Atomic: each count goes up in one `INSERT ... ON CONFLICT DO UPDATE ... WHERE count < limit`
statement. PostgreSQL locks the row and checks the condition against its latest version, so
when two requests arrive together and only one slot is left, exactly one gets it. Every
transaction locks the user's row first and the global row second, so they cannot deadlock.

A day runs from 00:00 to 24:00 UTC; each day has its own rows, so all counts start again at
00:00 UTC. The per-user counts live in `ai_usage` (#5), the global count in
`ai_usage_global`, which has no user id, so deleting an account does not lower it. The demo
account is a user like any other.
"""

import datetime as dt
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy import BigInteger, Connection, Engine, literal
from sqlalchemy.dialects.postgresql import insert

from app.ai.adapter import (
    AIProvider,
    Suggestion,
    SummaryEntry,
    check_suggest_input,
    check_summarise_input,
)
from app.ai.factory import AI
from app.errors import ApiError
from app.models import AiUsage, AiUsageGlobal
from app.settings import Settings

# The `limit` values of openapi.yaml's Error schema.
LimitName = Literal["user_suggestions", "user_summaries", "global"]
# The request types counted in ai_usage (app.models.AI_REQUEST_TYPES).
RequestType = Literal["suggestion", "summary"]

LIMIT_MESSAGES: dict[LimitName, str] = {
    "user_suggestions": (
        "You've used today's suggestions. They're available again after midnight UTC."
    ),
    "user_summaries": "You've used today's summaries. They're available again after midnight UTC.",
    "global": "Winlog has reached today's AI limit for everyone. Try again after midnight UTC.",
}

_USER_LIMIT_NAMES: dict[RequestType, LimitName] = {
    "suggestion": "user_suggestions",
    "summary": "user_summaries",
}


class AILimitReachedError(ApiError):
    """A daily AI limit is reached: openapi.yaml's 429 `limit_reached` error naming it."""

    def __init__(self, limit: LimitName) -> None:
        super().__init__(429, "limit_reached", LIMIT_MESSAGES[limit], limit=limit)
        self.limit = limit


@dataclass(frozen=True, slots=True)
class AILimits:
    """The daily limits. 0 blocks that kind of request."""

    suggestions_per_user: int
    summaries_per_user: int
    global_requests: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "AILimits":
        return cls(
            suggestions_per_user=settings.ai_daily_suggestions_per_user,
            summaries_per_user=settings.ai_daily_summaries_per_user,
            global_requests=settings.ai_daily_requests_global,
        )

    def per_user(self, request_type: RequestType) -> int:
        if request_type == "suggestion":
            return self.suggestions_per_user
        return self.summaries_per_user


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def utc_day(moment: dt.datetime) -> dt.date:
    """The UTC day a moment falls on. A day runs from 00:00 to 24:00 UTC."""
    if moment.tzinfo is None:
        raise ValueError("the moment needs a time zone")
    return moment.astimezone(dt.UTC).date()


class LimitedAI:
    """The only entry point features use for AI calls. Checks the daily limits first."""

    def __init__(
        self,
        provider: AIProvider,
        engine: Engine,
        limits: AILimits,
        clock: Callable[[], dt.datetime] = utc_now,
    ) -> None:
        self._provider = provider
        self._engine = engine
        self._limits = limits
        self._clock = clock

    def suggest(self, user_id: uuid.UUID, text: str) -> Suggestion:
        """Count a suggestion for the user and ask the AI for it.

        Raises `AILimitReachedError` before any AI call when a limit is reached, and the
        adapter's `AITimeoutError` or `AIProviderError` when the AI call fails (it counts).
        """
        text = check_suggest_input(text)
        self._count_request(user_id, "suggestion")
        return self._provider.suggest(text)

    def summarise(self, user_id: uuid.UUID, entries: Iterable[SummaryEntry]) -> str:
        """Count a summary for the user and ask the AI for it.

        No entries raises ValueError and counts nothing. Otherwise as `suggest`.
        """
        entries = check_summarise_input(entries)
        self._count_request(user_id, "summary")
        return self._provider.summarise(entries)

    def _count_request(self, user_id: uuid.UUID, request_type: RequestType) -> None:
        """Take one of the day's slots for the user and globally, or raise naming the limit."""
        day = utc_day(self._clock())
        with self._engine.begin() as connection:
            # Raising inside the block rolls back, so a reached global cap leaves the user's
            # count as it was.
            if not _count_for_user(
                connection, user_id, day, request_type, self._limits.per_user(request_type)
            ):
                raise AILimitReachedError(_USER_LIMIT_NAMES[request_type])
            if not _count_globally(connection, day, self._limits.global_requests):
                raise AILimitReachedError("global")


def _count_for_user(
    connection: Connection, user_id: uuid.UUID, day: dt.date, request_type: str, limit: int
) -> bool:
    """Add one to the user's count if it is below the limit. False if the limit is reached."""
    if limit <= 0:
        return False
    statement = (
        insert(AiUsage)
        .values(user_id=user_id, day=day, request_type=request_type, request_count=1)
        .on_conflict_do_update(
            index_elements=[AiUsage.user_id, AiUsage.day, AiUsage.request_type],
            set_={"request_count": AiUsage.request_count + 1},
            where=AiUsage.request_count < literal(limit, BigInteger),
        )
        .returning(AiUsage.request_count)
    )
    return connection.execute(statement).one_or_none() is not None


def _count_globally(connection: Connection, day: dt.date, limit: int) -> bool:
    """Add one to the day's global count if it is below the cap. False if it is reached."""
    if limit <= 0:
        return False
    statement = (
        insert(AiUsageGlobal)
        .values(day=day, request_count=1)
        .on_conflict_do_update(
            index_elements=[AiUsageGlobal.day],
            set_={"request_count": AiUsageGlobal.request_count + 1},
            where=AiUsageGlobal.request_count < literal(limit, BigInteger),
        )
        .returning(AiUsageGlobal.request_count)
    )
    return connection.execute(statement).one_or_none() is not None


def get_limited_ai(request: Request, provider: AI) -> LimitedAI:
    """FastAPI dependency: the limited entry point around the app's AI provider."""
    return LimitedAI(provider, request.app.state.engine, request.app.state.ai_limits)


LimitedAIDependency = Annotated[LimitedAI, Depends(get_limited_ai)]
