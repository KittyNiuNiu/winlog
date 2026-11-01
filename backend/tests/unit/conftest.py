"""Shared fixtures for unit tests."""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

# app.main builds the app from the environment when it is imported. These defaults let the
# import work without a .env file; tests build their own apps from explicit settings.
os.environ.setdefault("DATABASE_URL", "postgresql://unit:unit@localhost:5432/unit")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

from app.main import create_app  # noqa: E402
from app.settings import Settings  # noqa: E402

ALLOWED_ORIGIN = "http://localhost:5173"
OPENAPI_PATH = Path(__file__).resolve().parents[3] / "openapi.yaml"
CONTRACT_URI = "urn:winlog:openapi"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://winlog:unit-test-secret@localhost:5432/winlog",
        cors_allowed_origins=[ALLOWED_ORIGIN],
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def no_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore any local .env file and remove both variables from the environment."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)


@pytest.fixture(scope="session")
def contract() -> Callable[[str], Draft202012Validator]:
    """Return a validator for a schema in openapi.yaml, for example contract("Error")."""
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(
        CONTRACT_URI, Resource(contents=spec, specification=DRAFT202012)
    )

    def validator(schema_name: str) -> Draft202012Validator:
        ref = {"$ref": f"{CONTRACT_URI}#/components/schemas/{schema_name}"}
        return Draft202012Validator(ref, registry=registry)

    return validator
