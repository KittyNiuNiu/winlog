"""Daily AI usage limits without a database (issue #15, product-spec.md §8).

The counting itself needs PostgreSQL and is tested in tests/integration/test_ai_limits.py.
"""

import ast
import datetime as dt
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.ai import AILimitReachedError, AILimits, LimitedAIDependency
from app.ai.limits import LIMIT_MESSAGES, utc_day
from app.main import create_app
from app.settings import Settings, SettingsError, load_settings
from tests.conftest import OPENAPI_PATH

BACKEND_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BACKEND_DIR / "app"
ENV_EXAMPLE = BACKEND_DIR.parent / ".env.example"

LIMIT_VARIABLES = {
    "AI_DAILY_SUGGESTIONS_PER_USER": ("ai_daily_suggestions_per_user", 10),
    "AI_DAILY_SUMMARIES_PER_USER": ("ai_daily_summaries_per_user", 2),
    "AI_DAILY_REQUESTS_GLOBAL": ("ai_daily_requests_global", 100),
}


@pytest.fixture
def required_env(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")


# --- Settings -----------------------------------------------------------------------------


def test_limits_default_to_the_spec_values(required_env):
    settings = load_settings()

    assert settings.ai_daily_suggestions_per_user == 10
    assert settings.ai_daily_summaries_per_user == 2
    assert settings.ai_daily_requests_global == 100
    assert AILimits.from_settings(settings) == AILimits(
        suggestions_per_user=10, summaries_per_user=2, global_requests=100
    )


@pytest.mark.parametrize("variable", LIMIT_VARIABLES)
@pytest.mark.parametrize("value", ["0", "1", "7", " 25 ", "100000"])
def test_limits_come_from_the_environment(required_env, monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)

    field, _ = LIMIT_VARIABLES[variable]
    assert getattr(load_settings(), field) == int(value)


@pytest.mark.parametrize("variable", LIMIT_VARIABLES)
@pytest.mark.parametrize(
    "value", ["-1", "1.5", "1.0", "abc", "", " ", "+5", "1_000", "1e2", "0x10", "٣", "ten"]
)
def test_invalid_limit_stops_the_app_naming_the_variable(
    required_env, monkeypatch, variable, value
):
    monkeypatch.setenv(variable, value)

    with pytest.raises(SettingsError, match=f"{variable} is invalid"):
        load_settings()
    with pytest.raises(SettingsError, match=f"{variable} is invalid"):
        create_app()


def test_invalid_limit_error_names_only_the_invalid_variables(required_env, monkeypatch):
    monkeypatch.setenv("AI_DAILY_SUGGESTIONS_PER_USER", "-3")
    monkeypatch.setenv("AI_DAILY_REQUESTS_GLOBAL", "lots")

    with pytest.raises(SettingsError) as error:
        load_settings()

    message = str(error.value)
    assert "AI_DAILY_SUGGESTIONS_PER_USER is invalid" in message
    assert "AI_DAILY_REQUESTS_GLOBAL is invalid" in message
    assert "AI_DAILY_SUMMARIES_PER_USER" not in message
    assert "whole number of 0 or more" in message


@pytest.mark.parametrize("value", [-1, True, 1.5, None])
def test_limits_given_in_code_must_be_whole_numbers_too(value):
    with pytest.raises(ValueError, match="whole number of 0 or more"):
        Settings(
            _env_file=None,
            database_url="postgresql://winlog:secret@localhost:5432/winlog",
            cors_allowed_origins=["http://localhost:5173"],
            ai_provider="mock",
            ai_daily_summaries_per_user=value,
        )


def test_limits_are_documented_in_env_example_with_their_defaults():
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    for variable, (_, default) in LIMIT_VARIABLES.items():
        assert f"{variable}={default}" in lines
        # The comment block right above the variable states the default.
        index = lines.index(f"{variable}={default}")
        comment = []
        while lines[index - 1].startswith("#"):
            index -= 1
            comment.insert(0, lines[index])
        assert f"default {default}" in " ".join(comment)


def test_app_keeps_the_limits_from_its_settings(settings):
    settings = settings.model_copy(
        update={
            "ai_daily_suggestions_per_user": 3,
            "ai_daily_summaries_per_user": 0,
            "ai_daily_requests_global": 7,
        }
    )

    app = create_app(settings)

    assert app.state.ai_limits == AILimits(
        suggestions_per_user=3, summaries_per_user=0, global_requests=7
    )


# --- The limit reached error --------------------------------------------------------------


def test_limit_names_are_the_ones_in_the_contract():
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    names = spec["components"]["schemas"]["Error"]["properties"]["limit"]["enum"]
    assert set(LIMIT_MESSAGES) == set(names)


@pytest.mark.parametrize("limit", ["user_suggestions", "user_summaries", "global"])
def test_limit_reached_error_names_the_limit_as_in_the_contract(settings, contract, limit):
    app = create_app(settings)

    @app.get("/test-limit")
    def _raise() -> None:
        raise AILimitReachedError(limit)

    response = TestClient(app).get("/test-limit")

    assert response.status_code == 429
    body = response.json()
    assert body == {"code": "limit_reached", "message": LIMIT_MESSAGES[limit], "limit": limit}
    contract("Error").validate(body)


def test_limit_messages_say_which_limit_and_when_it_resets():
    assert "suggestions" in LIMIT_MESSAGES["user_suggestions"]
    assert "summaries" in LIMIT_MESSAGES["user_summaries"]
    assert "everyone" in LIMIT_MESSAGES["global"]
    for message in LIMIT_MESSAGES.values():
        assert "midnight UTC" in message


# --- Days ---------------------------------------------------------------------------------


def test_a_day_runs_from_midnight_to_midnight_utc():
    assert utc_day(dt.datetime(2026, 11, 9, 0, 0, 0, tzinfo=dt.UTC)) == dt.date(2026, 11, 9)
    assert utc_day(dt.datetime(2026, 11, 9, 23, 59, 59, 999999, tzinfo=dt.UTC)) == dt.date(
        2026, 11, 9
    )
    assert utc_day(dt.datetime(2026, 11, 10, 0, 0, 0, tzinfo=dt.UTC)) == dt.date(2026, 11, 10)


def test_the_day_is_the_utc_day_whatever_the_time_zone():
    berlin_morning = dt.datetime(2026, 11, 10, 0, 30, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    new_york_evening = dt.datetime(2026, 11, 9, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))

    assert utc_day(berlin_morning) == dt.date(2026, 11, 9)
    assert utc_day(new_york_evening) == dt.date(2026, 11, 10)


def test_a_time_without_a_time_zone_is_refused():
    with pytest.raises(ValueError):
        utc_day(dt.datetime(2026, 11, 9, 12, 0))


# --- One limited entry point --------------------------------------------------------------


def test_the_app_provides_the_limited_entry_point_around_its_provider(settings):
    app = create_app(settings)

    @app.get("/test-entry-point")
    def _entry_point(ai: LimitedAIDependency) -> dict:
        return {"provider": ai._provider is app.state.ai_provider}

    assert TestClient(app).get("/test-entry-point").json() == {"provider": True}


_RAW_AI_NAMES = {
    "AI",
    "AIProvider",
    "MockProvider",
    "OpenAICompatibleProvider",
    "create_ai_provider",
    "get_ai_provider",
}


def _feature_modules() -> list[Path]:
    """Every backend module outside the AI package itself."""
    return [path for path in APP_DIR.rglob("*.py") if APP_DIR / "ai" not in path.parents]


def test_features_never_use_the_ai_provider_directly():
    """Features call the AI only through LimitedAI, so no feature can skip the limits."""
    offenders = []
    for path in _feature_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.ai"):
                for alias in node.names:
                    if alias.name in _RAW_AI_NAMES and (
                        path.name != "main.py" or alias.name != "create_ai_provider"
                    ):
                        offenders.append(f"{path.name} imports {alias.name}")
            if isinstance(node, ast.Import):
                offenders += [
                    f"{path.name} imports {alias.name}"
                    for alias in node.names
                    if alias.name.startswith("app.ai")
                ]
            if isinstance(node, ast.Attribute) and node.attr == "ai_provider":
                if path.name != "main.py":
                    offenders.append(f"{path.name} reads ai_provider")
    assert offenders == []
