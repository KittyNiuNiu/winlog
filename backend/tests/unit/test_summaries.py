"""The generate-summary route without a database (issue #17, `generateSummary`).

Covers FR-R3, FR-R4 and the §7.4 error handling. The limited entry point is replaced by a
stand-in, and the shared filter by a fixed list of entries, so these tests make no AI call
and need no PostgreSQL. Matching, saving, the limits and other users are tested against
PostgreSQL in tests/integration/test_summaries.py.
"""

import datetime as dt
import uuid
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models, summaries
from app.ai import (
    AIError,
    AILimitReachedError,
    AIProviderError,
    AITimeoutError,
    SummaryEntry,
    get_limited_ai,
)
from app.ai.limits import LIMIT_MESSAGES
from app.auth import get_current_user
from app.db import get_session
from app.entries import Entry, EntryFilter
from app.errors import ApiError
from app.main import create_app
from app.models import User
from app.summaries import SummaryFilter

JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
ENTRY_TEXT = "Negotiated the confidential vendor contract."
AI_UNAVAILABLE = {"code": "ai_unavailable", "message": "The AI is not available right now."}


class FakeLimitedAI:
    """Stands in for `LimitedAI`: records the calls and answers or raises as configured."""

    def __init__(self, answer: str | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[uuid.UUID, list[SummaryEntry]]] = []

    def summarise(self, user_id: uuid.UUID, entries: Sequence[SummaryEntry]) -> str:
        self.calls.append((user_id, list(entries)))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _entry() -> Entry:
    now = dt.datetime(2026, 1, 10, 12, tzinfo=dt.UTC)
    return Entry(
        id=uuid.uuid4(),
        date=dt.date(2026, 1, 10),
        text=ENTRY_TEXT,
        category="Achievement",
        tags=["Python"],
        result_impact=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def user() -> User:
    return User(id=uuid.uuid4(), email="a@b.c")


class FakeFilter:
    """Stands in for #11's `filter_entries`: returns `entries` and records each filter."""

    def __init__(self) -> None:
        self.entries = [_entry()]
        self.filters: list[EntryFilter] = []

    def __call__(self, session: Session, user: User, entry_filter: EntryFilter) -> list[Entry]:
        self.filters.append(entry_filter)
        return list(self.entries)


@pytest.fixture
def matching(monkeypatch: pytest.MonkeyPatch) -> FakeFilter:
    fake = FakeFilter()
    monkeypatch.setattr(summaries, "filter_entries", fake)
    monkeypatch.setattr(summaries, "filter_tag_names", lambda session, user, names: list(names))
    return fake


class FakeSession:
    """Stands in for the database session: keeps added rows and sets what PostgreSQL sets."""

    def __init__(self) -> None:
        self.added: list[models.Summary] = []
        self.committed = False

    def close(self) -> None:
        pass

    def add(self, row: models.Summary) -> None:
        self.added.append(row)

    def commit(self) -> None:
        now = dt.datetime.now(dt.UTC)
        for row in self.added:
            row.id, row.created_at, row.updated_at = uuid.uuid4(), now, now
        self.committed = True


def _client(
    settings, user: User, ai: FakeLimitedAI, session: FakeSession | None = None
) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_limited_ai] = lambda: ai
    app.dependency_overrides[get_session] = lambda: session or FakeSession()
    return TestClient(app)


# --- Contract -----------------------------------------------------------------------------


def test_fr_r3_generate_summary_operation_matches_the_contract(settings):
    generated = create_app(settings).openapi()
    operation = generated["paths"]["/summaries"]["post"]

    assert operation["operationId"] == "generateSummary"
    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["requestBody"]["required"] is True
    request = operation["requestBody"]["content"]["application/json"]["schema"]
    assert request == {"$ref": "#/components/schemas/SummaryFilter"}
    response = operation["responses"]["201"]["content"]["application/json"]["schema"]
    assert response == {"$ref": "#/components/schemas/Summary"}
    schemas = generated["components"]["schemas"]
    assert schemas["SummaryFilter"]["required"] == ["period_start", "period_end"]
    assert set(schemas["SummaryFilter"]["properties"]) == {
        "period_start",
        "period_end",
        "categories",
        "tags",
    }
    assert schemas["Summary"]["required"] == ["id", "text", "filter", "created_at", "updated_at"]


# --- Request model ------------------------------------------------------------------------


def test_fr_r3_filter_needs_only_the_period():
    summary_filter = SummaryFilter.model_validate(JANUARY)

    assert summary_filter.period_start == dt.date(2026, 1, 1)
    assert summary_filter.period_end == dt.date(2026, 1, 31)
    assert summary_filter.categories == []
    assert summary_filter.tags == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"period_start": "2026-01-01"},
        {"period_end": "2026-01-31"},
        {"period_start": "2026-02-30", "period_end": "2026-03-01"},
        {"period_start": "2026-01-01T00:00:00", "period_end": "2026-01-31"},
        {"period_start": 1767225600, "period_end": "2026-01-31"},
        {**JANUARY, "categories": ["Hobby"]},
        {**JANUARY, "categories": None},
        {**JANUARY, "tags": ["a\x00b"]},
        {**JANUARY, "tags": None},
    ],
)
def test_fr_r3_filter_rejects_missing_or_invalid_fields(body):
    with pytest.raises(ValueError):
        SummaryFilter.model_validate(body)


def test_fr_r3_filter_tag_names_are_only_checked_for_storable_characters():
    """Like the list filter (#11): a name that is empty after cleaning matches nothing."""
    assert SummaryFilter.model_validate({**JANUARY, "tags": ["", "  x  "]}).tags == ["", "  x  "]


# --- Route --------------------------------------------------------------------------------


def test_fr_r3_route_sends_the_users_matching_entries_to_the_limited_entry_point(
    settings, user, matching, contract
):
    ai = FakeLimitedAI("A summary.")
    session = FakeSession()
    body = {**JANUARY, "categories": ["Achievement"], "tags": ["Python"]}

    response = _client(settings, user, ai, session).post("/summaries", json=body)

    assert response.status_code == 201
    contract("Summary").validate(response.json())
    assert response.json()["text"] == "A summary."
    assert response.json()["filter"] == body
    [saved] = session.added
    assert session.committed
    assert str(saved.id) == response.json()["id"]
    assert saved.user_id == user.id
    assert saved.text == "A summary."
    assert matching.filters == [
        EntryFilter(
            start_date=dt.date(2026, 1, 1),
            end_date=dt.date(2026, 1, 31),
            categories=["Achievement"],
            tags=["Python"],
        )
    ]
    assert ai.calls == [(user.id, [SummaryEntry.from_entry(entry) for entry in matching.entries])]


def test_fr_r3_no_matching_entries_makes_no_ai_call(settings, user, matching, contract):
    matching.entries.clear()
    ai = FakeLimitedAI("A summary.")

    response = _client(settings, user, ai).post("/summaries", json=JANUARY)

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "no_matching_entries",
        "message": "No entries match this filter, so no summary was generated.",
    }
    assert ai.calls == []


def test_fr_r3_period_out_of_order_is_checked_before_filtering(settings, user, matching, contract):
    """#11's shared filter does not check the period order, so the endpoint must."""
    ai = FakeLimitedAI("A summary.")

    response = _client(settings, user, ai).post(
        "/summaries", json={"period_start": "2026-01-02", "period_end": "2026-01-01"}
    )

    assert response.status_code == 422
    contract("Error").validate(response.json())
    assert response.json()["code"] == "validation_failed"
    assert [field["field"] for field in response.json()["fields"]] == ["period_end"]
    assert matching.filters == []
    assert ai.calls == []


@pytest.mark.parametrize(
    "error", [AITimeoutError("timed out"), AIProviderError("failed"), AIError("other")]
)
def test_fr_r3_ai_failure_returns_ai_unavailable(settings, user, matching, contract, error):
    session = FakeSession()

    response = _client(settings, user, FakeLimitedAI(error), session).post(
        "/summaries", json=JANUARY
    )

    assert response.status_code == 503
    contract("Error").validate(response.json())
    assert response.json() == AI_UNAVAILABLE
    assert session.added == []


@pytest.mark.parametrize("limit", ["user_summaries", "global"])
def test_fr_r3_reached_limit_returns_limit_reached(settings, user, matching, contract, limit):
    response = _client(settings, user, FakeLimitedAI(AILimitReachedError(limit))).post(
        "/summaries", json=JANUARY
    )

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json() == {
        "code": "limit_reached",
        "message": LIMIT_MESSAGES[limit],
        "limit": limit,
    }


def test_privacy_ai_unavailable_error_does_not_carry_the_provider_error(user, matching):
    """The provider's exception may repeat the entry text, so no traceback may include it."""
    try:
        raise AIProviderError("The AI provider failed.") from RuntimeError(f"bad: {ENTRY_TEXT}")
    except AIProviderError as provider_error:
        ai = FakeLimitedAI(provider_error)

    with Session() as session, pytest.raises(ApiError) as raised:
        summaries.generate_summary(
            SummaryFilter.model_validate(JANUARY),
            user,
            ai,  # type: ignore[arg-type]
            session,
        )

    assert raised.value.code == "ai_unavailable"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert ENTRY_TEXT not in str(raised.value)


def test_fr_r4_no_filter_tag_names_needs_no_lookup(user):
    """Without names, nothing is looked up, so no database is needed."""
    with Session() as session:
        assert summaries.filter_tag_names(session, user, []) == []
        assert summaries.filter_tag_names(session, user, ["", "   "]) == []
