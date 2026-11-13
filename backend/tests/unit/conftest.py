"""Shared fixtures for unit tests."""

import os

import pytest
from fastapi.testclient import TestClient

# app.main builds the app from the environment when it is imported. These defaults let the
# import work without a .env file; tests build their own apps from explicit settings.
os.environ.setdefault("DATABASE_URL", "postgresql://unit:unit@localhost:5432/unit")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
os.environ.setdefault("AI_PROVIDER", "mock")

from app.attempt_limits import AttemptLimiter, TooManyAttemptsError  # noqa: E402
from app.health import check_database  # noqa: E402
from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402

ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://winlog:unit-test-secret@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
        ai_provider="mock",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    """A client whose database check always succeeds, so unit tests need no PostgreSQL."""
    app = create_app(settings)
    app.dependency_overrides[check_database] = lambda: True
    return TestClient(app)


@pytest.fixture
def no_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore any local .env file and remove the app's variables from the environment."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("DATABASE_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("TOKEN_LIFETIME_DAYS", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.delenv("AI_SUGGESTION_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AI_SUMMARY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AI_SUMMARY_MAX_TOKENS", raising=False)
    monkeypatch.delenv("AI_SUMMARY_MAX_INPUT_CHARACTERS", raising=False)
    monkeypatch.delenv("AI_DAILY_SUGGESTIONS_PER_USER", raising=False)
    monkeypatch.delenv("AI_DAILY_SUMMARIES_PER_USER", raising=False)
    monkeypatch.delenv("AI_DAILY_REQUESTS_GLOBAL", raising=False)
    monkeypatch.delenv("DEMO_EMAIL", raising=False)
    monkeypatch.delenv("LOGIN_MAX_FAILED_ATTEMPTS", raising=False)
    monkeypatch.delenv("LOGIN_ATTEMPT_WINDOW_MINUTES", raising=False)
    monkeypatch.delenv("DEMO_LOGIN_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("DEMO_LOGIN_WINDOW_MINUTES", raising=False)


class FakeAttempts:
    """Stands in for the attempt limits (FR-A4), which need PostgreSQL.

    Records each call as (method, key) in `calls`. While `retry_after` is set, every attempt
    is refused with that many seconds left. The real limits are tested in
    tests/integration/test_attempt_limits.py.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.retry_after: int | None = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = self

        def take(method: str):
            def record(_limiter: AttemptLimiter, key: str) -> None:
                fake.calls.append((method, key))
                if fake.retry_after is not None:
                    raise TooManyAttemptsError(fake.retry_after)

            return record

        def clear(_limiter: AttemptLimiter, email: str) -> None:
            fake.calls.append(("clear_login_attempts", email))

        monkeypatch.setattr(AttemptLimiter, "take_login_attempt", take("take_login_attempt"))
        monkeypatch.setattr(AttemptLimiter, "take_demo_login", take("take_demo_login"))
        monkeypatch.setattr(AttemptLimiter, "clear_login_attempts", clear)


@pytest.fixture(autouse=True)
def attempts(monkeypatch: pytest.MonkeyPatch) -> FakeAttempts:
    """Unit tests have no database, so the attempt limits are replaced by a fake."""
    fake = FakeAttempts()
    fake.install(monkeypatch)
    return fake
