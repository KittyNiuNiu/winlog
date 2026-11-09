"""Daily AI usage limits against real PostgreSQL (issue #15, product-spec.md §8).

Every AI call goes to the mock provider. The clock is fixed, so the tests can step over
midnight UTC.
"""

import datetime as dt
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Engine, delete, func, insert, inspect, select

from app.ai import (
    AILimitReachedError,
    AILimits,
    AIProviderError,
    AITimeoutError,
    LimitedAI,
    LimitedAIDependency,
    MockProvider,
    Suggestion,
    SummaryEntry,
)
from app.ai.limits import LIMIT_MESSAGES
from app.auth import CurrentUser, hash_token
from app.main import create_app
from app.models import AiUsage, AiUsageGlobal, Token, User
from app.settings import Settings
from tests.integration.conftest import ALLOWED_ORIGIN

TODAY = dt.date(2026, 11, 9)
NOON = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.UTC)
LAST_SECOND = dt.datetime(2026, 11, 9, 23, 59, 59, tzinfo=dt.UTC)
MIDNIGHT = dt.datetime(2026, 11, 10, 0, 0, 0, tzinfo=dt.UTC)
TEXT = "Shipped the release."
ENTRY = SummaryEntry(
    date=TODAY, category="Achievement", text=TEXT, result_impact=None, tags=("Release",)
)


# --- Helpers ------------------------------------------------------------------------------


class Clock:
    """A clock the tests can set."""

    def __init__(self, now: dt.datetime = NOON) -> None:
        self.now = now

    def __call__(self) -> dt.datetime:
        return self.now


def _user(engine: Engine, email: str | None = None) -> uuid.UUID:
    email = email or f"user-{uuid.uuid4()}@example.com"
    with engine.begin() as connection:
        return connection.execute(
            insert(User).values(email=email, password_hash="hash").returning(User.id)
        ).scalar_one()


def _token(engine: Engine, user_id: uuid.UUID) -> str:
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


def _limits(suggestions: int = 10, summaries: int = 2, global_requests: int = 100) -> AILimits:
    return AILimits(
        suggestions_per_user=suggestions,
        summaries_per_user=summaries,
        global_requests=global_requests,
    )


def _user_count(
    engine: Engine, user_id: uuid.UUID, request_type: str = "suggestion", day: dt.date = TODAY
) -> int:
    with engine.connect() as connection:
        count = connection.execute(
            select(AiUsage.request_count).where(
                AiUsage.user_id == user_id,
                AiUsage.day == day,
                AiUsage.request_type == request_type,
            )
        ).scalar_one_or_none()
    return count or 0


def _global_count(engine: Engine, day: dt.date = TODAY) -> int:
    with engine.connect() as connection:
        count = connection.execute(
            select(AiUsageGlobal.request_count).where(AiUsageGlobal.day == day)
        ).scalar_one_or_none()
    return count or 0


def _usage_rows(engine: Engine) -> int:
    with engine.connect() as connection:
        users = connection.execute(select(func.count()).select_from(AiUsage)).scalar_one()
        days = connection.execute(select(func.count()).select_from(AiUsageGlobal)).scalar_one()
    return users + days


@pytest.fixture
def mock() -> MockProvider:
    return MockProvider()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def limited(migrated_db: Engine, mock: MockProvider, clock: Clock) -> Callable[..., LimitedAI]:
    """Build the limited entry point with the given limits, the mock and the test clock."""

    def build(**limits: int) -> LimitedAI:
        return LimitedAI(mock, migrated_db, _limits(**limits), clock=clock)

    return build


def _ai_calls(mock: MockProvider) -> int:
    return len(mock.suggest_calls) + len(mock.summarise_calls)


# --- Each limit reached -------------------------------------------------------------------


def test_user_suggestion_limit_is_reached(migrated_db, limited, mock):
    ai = limited(suggestions=2)
    user = _user(migrated_db)

    assert ai.suggest(user, TEXT).category
    assert ai.suggest(user, TEXT).category
    with pytest.raises(AILimitReachedError) as error:
        ai.suggest(user, TEXT)

    assert error.value.limit == "user_suggestions"
    assert error.value.status_code == 429
    assert error.value.code == "limit_reached"
    assert len(mock.suggest_calls) == 2
    assert _user_count(migrated_db, user) == 2
    assert _global_count(migrated_db) == 2


def test_user_summary_limit_is_reached(migrated_db, limited, mock):
    ai = limited(summaries=1)
    user = _user(migrated_db)

    assert ai.summarise(user, [ENTRY])
    with pytest.raises(AILimitReachedError) as error:
        ai.summarise(user, [ENTRY])

    assert error.value.limit == "user_summaries"
    assert len(mock.summarise_calls) == 1
    assert _user_count(migrated_db, user, "summary") == 1
    assert _global_count(migrated_db) == 1


def test_suggestion_and_summary_limits_are_counted_separately(migrated_db, limited):
    ai = limited(suggestions=1, summaries=1)
    user = _user(migrated_db)

    ai.suggest(user, TEXT)
    ai.summarise(user, [ENTRY])  # the used suggestion does not block the summary

    with pytest.raises(AILimitReachedError, match="suggestions"):
        ai.suggest(user, TEXT)
    with pytest.raises(AILimitReachedError, match="summaries"):
        ai.summarise(user, [ENTRY])
    assert _user_count(migrated_db, user, "suggestion") == 1
    assert _user_count(migrated_db, user, "summary") == 1


def test_global_cap_counts_suggestions_and_summaries_of_all_users_together(
    migrated_db, limited, mock
):
    ai = limited(suggestions=10, summaries=10, global_requests=3)
    alice, bob = _user(migrated_db), _user(migrated_db)

    ai.suggest(alice, TEXT)
    ai.summarise(alice, [ENTRY])
    ai.suggest(bob, TEXT)
    assert _global_count(migrated_db) == 3

    for call in (lambda: ai.suggest(bob, TEXT), lambda: ai.summarise(bob, [ENTRY])):
        with pytest.raises(AILimitReachedError) as error:
            call()
        assert error.value.limit == "global"

    assert _ai_calls(mock) == 3
    assert _global_count(migrated_db) == 3


def test_reached_global_cap_does_not_raise_the_users_count(migrated_db, limited):
    ai = limited(suggestions=10, global_requests=1)
    alice, bob = _user(migrated_db), _user(migrated_db)
    ai.suggest(alice, TEXT)

    with pytest.raises(AILimitReachedError, match="everyone"):
        ai.suggest(bob, TEXT)

    assert _user_count(migrated_db, bob) == 0
    assert _user_count(migrated_db, alice) == 1
    assert _global_count(migrated_db) == 1


def test_users_limit_is_checked_before_the_global_cap(migrated_db, limited):
    ai = limited(suggestions=1, global_requests=1)
    user = _user(migrated_db)
    ai.suggest(user, TEXT)

    # Both are reached: the user's own limit is named.
    with pytest.raises(AILimitReachedError) as error:
        ai.suggest(user, TEXT)

    assert error.value.limit == "user_suggestions"


# --- A limit of 0 -------------------------------------------------------------------------


def test_suggestion_limit_of_zero_blocks_suggestions(migrated_db, limited, mock):
    ai = limited(suggestions=0)
    user = _user(migrated_db)

    with pytest.raises(AILimitReachedError) as error:
        ai.suggest(user, TEXT)

    assert error.value.limit == "user_suggestions"
    assert ai.summarise(user, [ENTRY])  # summaries still work
    assert mock.suggest_calls == []
    assert _user_count(migrated_db, user) == 0
    assert _global_count(migrated_db) == 1


def test_summary_limit_of_zero_blocks_summaries(migrated_db, limited, mock):
    ai = limited(summaries=0)
    user = _user(migrated_db)

    with pytest.raises(AILimitReachedError) as error:
        ai.summarise(user, [ENTRY])

    assert error.value.limit == "user_summaries"
    assert mock.summarise_calls == []
    assert _usage_rows(migrated_db) == 0


def test_global_cap_of_zero_blocks_every_request(migrated_db, limited, mock):
    ai = limited(global_requests=0)
    user = _user(migrated_db)

    for call in (lambda: ai.suggest(user, TEXT), lambda: ai.summarise(user, [ENTRY])):
        with pytest.raises(AILimitReachedError) as error:
            call()
        assert error.value.limit == "global"

    assert _ai_calls(mock) == 0
    assert _usage_rows(migrated_db) == 0


# --- Days ---------------------------------------------------------------------------------


def test_counts_start_again_at_midnight_utc(migrated_db, limited, clock, mock):
    ai = limited(suggestions=1, summaries=1, global_requests=2)
    user = _user(migrated_db)
    next_day = TODAY + dt.timedelta(days=1)

    clock.now = LAST_SECOND
    ai.suggest(user, TEXT)
    ai.summarise(user, [ENTRY])
    with pytest.raises(AILimitReachedError, match="suggestions"):
        ai.suggest(user, TEXT)

    clock.now = MIDNIGHT
    ai.suggest(user, TEXT)
    ai.summarise(user, [ENTRY])

    assert _ai_calls(mock) == 4
    assert _user_count(migrated_db, user, "suggestion", TODAY) == 1
    assert _user_count(migrated_db, user, "summary", TODAY) == 1
    assert _user_count(migrated_db, user, "suggestion", next_day) == 1
    assert _user_count(migrated_db, user, "summary", next_day) == 1
    assert _global_count(migrated_db, TODAY) == 2
    assert _global_count(migrated_db, next_day) == 2


def test_global_cap_starts_again_at_midnight_utc(migrated_db, limited, clock):
    ai = limited(global_requests=1)
    alice, bob = _user(migrated_db), _user(migrated_db)

    clock.now = LAST_SECOND
    ai.suggest(alice, TEXT)
    with pytest.raises(AILimitReachedError, match="everyone"):
        ai.suggest(bob, TEXT)

    clock.now = MIDNIGHT
    ai.suggest(bob, TEXT)

    assert _global_count(migrated_db, TODAY) == 1
    assert _global_count(migrated_db, TODAY + dt.timedelta(days=1)) == 1


def test_the_day_is_the_utc_day_not_the_servers_local_day(migrated_db, limited, clock):
    ai = limited(suggestions=1)
    user = _user(migrated_db)
    # 00:30 in UTC+01:00 is still 23:30 of the day before in UTC.
    clock.now = dt.datetime(2026, 11, 10, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=1)))

    ai.suggest(user, TEXT)

    assert _user_count(migrated_db, user, day=TODAY) == 1
    assert _global_count(migrated_db, TODAY) == 1


# --- What counts --------------------------------------------------------------------------


def test_timed_out_calls_count(migrated_db, limited, mock):
    ai = limited(suggestions=1, summaries=1)
    user = _user(migrated_db)
    mock.raise_timeout()

    with pytest.raises(AITimeoutError):
        ai.suggest(user, TEXT)
    with pytest.raises(AITimeoutError):
        ai.summarise(user, [ENTRY])

    assert _user_count(migrated_db, user, "suggestion") == 1
    assert _user_count(migrated_db, user, "summary") == 1
    assert _global_count(migrated_db) == 2
    mock.reset()
    with pytest.raises(AILimitReachedError, match="suggestions"):
        ai.suggest(user, TEXT)


def test_failed_calls_count(migrated_db, limited, mock):
    ai = limited(suggestions=2)
    user = _user(migrated_db)
    mock.raise_provider_error()

    with pytest.raises(AIProviderError):
        ai.suggest(user, TEXT)
    with pytest.raises(AIProviderError):
        ai.summarise(user, [ENTRY])

    assert _user_count(migrated_db, user, "suggestion") == 1
    assert _user_count(migrated_db, user, "summary") == 1
    assert _global_count(migrated_db) == 2


def test_calls_with_invalid_ai_output_count(migrated_db, limited, mock):
    ai = limited()
    user = _user(migrated_db)
    mock.return_suggestion(Suggestion(category="Not a category", tags=[]))  # type: ignore[arg-type]

    with pytest.raises(AIProviderError):
        ai.suggest(user, TEXT)

    assert _user_count(migrated_db, user) == 1
    assert _global_count(migrated_db) == 1


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda ai, user: ai.summarise(user, []), id="no matching entries"),
        pytest.param(lambda ai, user: ai.summarise(user, [object()]), id="not summary entries"),
        pytest.param(lambda ai, user: ai.suggest(user, None), id="text that is not a string"),
    ],
)
def test_requests_stopped_before_the_ai_call_do_not_count(migrated_db, limited, mock, call):
    ai = limited()
    user = _user(migrated_db)

    with pytest.raises((ValueError, TypeError)):
        call(ai, user)

    assert _ai_calls(mock) == 0
    assert _usage_rows(migrated_db) == 0


def test_requests_stopped_by_a_reached_limit_do_not_count(migrated_db, limited):
    ai = limited(suggestions=1, global_requests=5)
    user = _user(migrated_db)
    ai.suggest(user, TEXT)

    for _ in range(3):
        with pytest.raises(AILimitReachedError):
            ai.suggest(user, TEXT)

    assert _user_count(migrated_db, user) == 1
    assert _global_count(migrated_db) == 1


# --- Atomic check and increment -----------------------------------------------------------


def _race(calls: list[Callable[[], object]]) -> list[object]:
    """Run the calls in parallel threads that start together. Returns results or errors."""
    barrier = threading.Barrier(len(calls))

    def run(call: Callable[[], object]) -> object:
        barrier.wait()
        try:
            return call()
        except AILimitReachedError as error:
            return error

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


@pytest.mark.parametrize("attempt", range(5))
def test_parallel_requests_for_the_users_last_slot_let_exactly_one_through(
    migrated_db, limited, mock, attempt
):
    ai = limited(suggestions=3)
    user = _user(migrated_db)
    ai.suggest(user, TEXT)
    ai.suggest(user, TEXT)  # one slot left

    results = _race([lambda: ai.suggest(user, TEXT) for _ in range(10)])

    passed = [result for result in results if isinstance(result, Suggestion)]
    refused = [result for result in results if isinstance(result, AILimitReachedError)]
    assert len(passed) == 1
    assert len(refused) == 9
    assert {error.limit for error in refused} == {"user_suggestions"}
    assert len(mock.suggest_calls) == 3
    assert _user_count(migrated_db, user) == 3
    assert _global_count(migrated_db) == 3


@pytest.mark.parametrize("attempt", range(5))
def test_parallel_requests_for_the_last_global_slot_let_exactly_one_through(
    migrated_db, limited, mock, attempt
):
    ai = limited(global_requests=2)
    ai.suggest(_user(migrated_db), TEXT)  # one global slot left
    users = [_user(migrated_db) for _ in range(10)]

    results = _race(
        [lambda user=user: ai.summarise(user, [ENTRY]) for user in users]
        + [lambda user=user: ai.suggest(user, TEXT) for user in users]
    )

    passed = [result for result in results if not isinstance(result, AILimitReachedError)]
    refused = [result for result in results if isinstance(result, AILimitReachedError)]
    assert len(passed) == 1
    assert len(refused) == 19
    assert {error.limit for error in refused} == {"global"}
    assert _ai_calls(mock) == 2
    assert _global_count(migrated_db) == 2
    # Only the request that went through raised a user's count.
    counts = [
        _user_count(migrated_db, user, kind) for user in users for kind in ("suggestion", "summary")
    ]
    assert sorted(counts) == [0] * 19 + [1]


# --- Accounts -----------------------------------------------------------------------------


def test_fr_d2_deleting_a_user_who_used_ai_today_keeps_the_global_count(migrated_db, limited):
    ai = limited(global_requests=4)
    alice, bob = _user(migrated_db), _user(migrated_db)
    ai.suggest(alice, TEXT)
    ai.suggest(alice, TEXT)
    ai.summarise(alice, [ENTRY])
    ai.suggest(bob, TEXT)
    assert _global_count(migrated_db) == 4

    # Account deletion (#20) is not built yet, so the user is deleted in the database.
    with migrated_db.begin() as connection:
        connection.execute(delete(User).where(User.id == alice))

    assert _user_count(migrated_db, alice) == 0  # the per-user rows went with the account
    assert _global_count(migrated_db) == 4
    with pytest.raises(AILimitReachedError, match="everyone"):
        ai.suggest(bob, TEXT)


def test_global_counter_holds_no_personal_data(migrated_db):
    columns = {column["name"] for column in inspect(migrated_db).get_columns("ai_usage_global")}
    foreign_keys = inspect(migrated_db).get_foreign_keys("ai_usage_global")

    assert columns == {"day", "request_count"}
    assert foreign_keys == []


def test_fr_a3_one_user_at_the_limit_does_not_block_another(migrated_db, limited, mock):
    ai = limited(suggestions=1, summaries=1)
    alice, bob = _user(migrated_db), _user(migrated_db)
    ai.suggest(alice, TEXT)
    ai.summarise(alice, [ENTRY])
    with pytest.raises(AILimitReachedError):
        ai.suggest(alice, TEXT)

    assert ai.suggest(bob, TEXT)
    assert ai.summarise(bob, [ENTRY])
    assert _user_count(migrated_db, bob, "suggestion") == 1
    assert _user_count(migrated_db, bob, "summary") == 1


def test_demo_account_is_limited_like_any_other_user(migrated_db, mock, clock):
    """Everyone using the demo account shares its limits (§8): it is one user like any other."""
    demo = _user(migrated_db, "demo@winlog.example")
    first_visitor = LimitedAI(mock, migrated_db, _limits(suggestions=1), clock=clock)
    second_visitor = LimitedAI(mock, migrated_db, _limits(suggestions=1), clock=clock)

    first_visitor.suggest(demo, TEXT)
    with pytest.raises(AILimitReachedError) as error:
        second_visitor.suggest(demo, TEXT)

    assert error.value.limit == "user_suggestions"
    assert _user_count(migrated_db, demo) == 1


# --- Through the app ----------------------------------------------------------------------


class _SuggestionRequest(BaseModel):
    text: str


def _app_client(test_database_url: str, **limits: int) -> TestClient:
    """The app with the given limits and a route that uses the limited entry point.

    The suggestion and summary endpoints come with #16 and #17. This route stands in for
    them: authentication, then validation, then the limited entry point.
    """
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
        **limits,
    )
    app = create_app(settings)

    @app.post("/test-suggestion")
    def _suggest(body: _SuggestionRequest, user: CurrentUser, ai: LimitedAIDependency) -> dict:
        suggestion = ai.suggest(user.id, body.text)
        return {"category": suggestion.category}

    return TestClient(app)


def test_app_returns_the_limit_reached_error_from_the_contract(
    test_database_url, migrated_db, contract
):
    client = _app_client(test_database_url, ai_daily_suggestions_per_user=1)
    headers = {"Authorization": f"Bearer {_token(migrated_db, _user(migrated_db))}"}

    assert client.post("/test-suggestion", json={"text": TEXT}, headers=headers).status_code == 200
    response = client.post("/test-suggestion", json={"text": TEXT}, headers=headers)

    assert response.status_code == 429
    body = response.json()
    contract("Error").validate(body)
    assert body == {
        "code": "limit_reached",
        "message": LIMIT_MESSAGES["user_suggestions"],
        "limit": "user_suggestions",
    }


def test_app_names_the_global_cap_when_it_is_reached(test_database_url, migrated_db, contract):
    client = _app_client(test_database_url, ai_daily_requests_global=1)
    first = {"Authorization": f"Bearer {_token(migrated_db, _user(migrated_db))}"}
    second = {"Authorization": f"Bearer {_token(migrated_db, _user(migrated_db))}"}

    assert client.post("/test-suggestion", json={"text": TEXT}, headers=first).status_code == 200
    response = client.post("/test-suggestion", json={"text": TEXT}, headers=second)

    assert response.status_code == 429
    contract("Error").validate(response.json())
    assert response.json()["limit"] == "global"


def test_app_uses_the_default_limits(test_database_url, migrated_db):
    client = _app_client(test_database_url)
    headers = {"Authorization": f"Bearer {_token(migrated_db, _user(migrated_db))}"}

    codes = [
        client.post("/test-suggestion", json={"text": TEXT}, headers=headers).status_code
        for _ in range(11)
    ]

    assert codes == [200] * 10 + [429]


def test_unauthenticated_and_invalid_requests_do_not_count(test_database_url, migrated_db):
    client = _app_client(test_database_url)
    headers = {"Authorization": f"Bearer {_token(migrated_db, _user(migrated_db))}"}

    assert client.post("/test-suggestion", json={"text": TEXT}).status_code == 401
    assert (
        client.post(
            "/test-suggestion", json={"text": TEXT}, headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert client.post("/test-suggestion", json={}, headers=headers).status_code == 422

    assert _usage_rows(migrated_db) == 0
