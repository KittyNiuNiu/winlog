import pytest

from app.main import create_app
from app.settings import Settings, SettingsError, load_settings

SECRET = "super-secret-password"
DATABASE_URL = f"postgresql://winlog:{SECRET}@localhost:5432/winlog"


def test_settings_variables():
    assert set(Settings.model_fields) == {
        "database_url",
        "cors_allowed_origins",
        "database_connect_timeout_seconds",
        "token_lifetime_days",
        "ai_provider",
        "ai_base_url",
        "ai_api_key",
        "ai_model",
        "ai_suggestion_timeout_seconds",
        "ai_summary_timeout_seconds",
        "ai_summary_max_tokens",
        "ai_daily_suggestions_per_user",
        "ai_daily_summaries_per_user",
        "ai_daily_requests_global",
    }


def test_database_timeout_defaults_to_three_seconds(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    assert load_settings().database_connect_timeout_seconds == 3


@pytest.mark.parametrize("value", ["1", "61", "soon"])
def test_invalid_database_timeout_is_rejected(no_env_file, monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", value)

    with pytest.raises(SettingsError, match="DATABASE_CONNECT_TIMEOUT_SECONDS is invalid"):
        load_settings()


def test_settings_come_from_environment_variables(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " http://localhost:5173 , https://app.example.com ")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    settings = load_settings()

    assert settings.database_url.get_secret_value() == DATABASE_URL
    assert settings.cors_allowed_origins == ["http://localhost:5173", "https://app.example.com"]


def test_missing_database_url_is_named(no_env_file, monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    with pytest.raises(SettingsError, match="DATABASE_URL is required"):
        load_settings()


def test_missing_cors_origins_is_named(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AI_PROVIDER", "mock")

    with pytest.raises(SettingsError, match="CORS_ALLOWED_ORIGINS is required"):
        load_settings()


def test_app_does_not_start_without_required_variables(no_env_file):
    with pytest.raises(SettingsError) as error:
        create_app()

    assert "DATABASE_URL" in str(error.value)
    assert "CORS_ALLOWED_ORIGINS" in str(error.value)
    assert "AI_PROVIDER" in str(error.value)


def test_empty_database_url_is_invalid(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "  ")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    with pytest.raises(SettingsError, match="DATABASE_URL is invalid"):
        load_settings()


@pytest.mark.parametrize("origins", ["", "http://localhost:5173/", "localhost:5173"])
def test_invalid_cors_origins_are_rejected(no_env_file, monkeypatch, origins):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)
    monkeypatch.setenv("AI_PROVIDER", "mock")

    with pytest.raises(SettingsError, match="CORS_ALLOWED_ORIGINS is invalid"):
        load_settings()


def test_error_message_never_contains_values(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "not-an-origin")
    monkeypatch.setenv("AI_PROVIDER", "mock")

    with pytest.raises(SettingsError) as error:
        load_settings()

    assert SECRET not in str(error.value)


def test_database_url_is_masked_when_printed_or_logged(no_env_file, monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    settings = load_settings()

    import logging

    logging.getLogger("test").warning("settings: %s / %r", settings, settings)

    assert SECRET not in str(settings)
    assert SECRET not in repr(settings)
    assert SECRET not in caplog.text
