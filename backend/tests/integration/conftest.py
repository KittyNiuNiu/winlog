"""Fixtures for integration tests, which run against real PostgreSQL (never SQLite).

Start the database first: `docker compose up -d db` in the repository root.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, inspect, text

# app.main builds the app from the environment when it is imported. These defaults let the
# import work without a .env file; tests build their own apps from explicit settings.
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost:5432/unused")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

from app.db import sqlalchemy_url  # noqa: E402
from app.main import create_app  # noqa: E402
from app.settings import ENV_FILE, Settings  # noqa: E402

ALLOWED_ORIGIN = "http://localhost:5173"
BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_TABLES = {"users", "entries", "tags", "entry_tags", "summaries", "ai_usage"}


class _IntegrationSettings(BaseSettings):
    """Reads only TEST_DATABASE_URL. There is deliberately no fallback to DATABASE_URL."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    test_database_url: str | None = None


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = _IntegrationSettings().test_database_url
    if not url:
        pytest.exit(
            "TEST_DATABASE_URL is not set. Integration tests use their own database and never "
            "fall back to DATABASE_URL. Set it in .env (see .env.example) and start PostgreSQL "
            "with `docker compose up -d db`.",
            returncode=4,
        )
    return url


@pytest.fixture
def client(test_database_url: str, migrated_db: Engine) -> TestClient:
    """The app, connected to the migrated test database. Data is removed after the test."""
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        cors_allowed_origins=[ALLOWED_ORIGIN],
    )
    return TestClient(create_app(settings))


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    engine = create_engine(sqlalchemy_url(test_database_url))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    """Alembic pointed at the test database (never at DATABASE_URL)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    # configparser treats % as special, so escape it in the URL.
    config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def reset_schema(engine: Engine) -> None:
    """Make the test database empty: no tables, no Alembic version."""
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


@pytest.fixture
def migrated_db(engine: Engine, alembic_config: Config) -> Iterator[Engine]:
    """The test database at the latest migration. All data is removed after the test."""
    command.upgrade(alembic_config, "head")
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users CASCADE"))
