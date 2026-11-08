"""Shared fixtures for unit tests."""

import os

import pytest
from fastapi.testclient import TestClient

# app.main builds the app from the environment when it is imported. These defaults let the
# import work without a .env file; tests build their own apps from explicit settings.
os.environ.setdefault("DATABASE_URL", "postgresql://unit:unit@localhost:5432/unit")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

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
