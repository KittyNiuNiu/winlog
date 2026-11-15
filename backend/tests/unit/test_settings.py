import pytest

from app.main import create_app
from app.settings import Settings, SettingsError, load_settings
from tests.whole_number_settings import (
    accepted_values,
    assert_range_applies_in_code,
    assert_stops_at_startup,
    refused_values,
    value_id,
)

SECRET = "super-secret-password"
DATABASE_URL = f"postgresql://winlog:{SECRET}@localhost:5432/winlog"


def test_settings_variables():
    assert set(Settings.model_fields) == {
        "database_url",
        "cors_allowed_origins",
        "database_connect_timeout_seconds",
        "database_query_timeout_seconds",
        "request_body_max_bytes",
        "hsts_max_age_seconds",
        "token_lifetime_days",
        "ai_provider",
        "ai_base_url",
        "ai_api_key",
        "ai_model",
        "ai_suggestion_timeout_seconds",
        "ai_summary_timeout_seconds",
        "ai_summary_max_tokens",
        "ai_summary_max_input_characters",
        "ai_daily_suggestions_per_user",
        "ai_daily_summaries_per_user",
        "ai_daily_requests_global",
        "demo_email",
        "login_max_failed_attempts",
        "login_attempt_window_minutes",
        "demo_login_max_attempts",
        "demo_login_window_minutes",
        "otel_exporter_otlp_endpoint",
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


def _set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")


# --- Strict whole numbers (issue #108) ---

# Every field of Settings whose type is int, read from the model, so a whole-number setting
# added later is covered too.
INT_FIELDS = [name for name, field in Settings.model_fields.items() if field.annotation is int]

# The five settings that used pydantic's lax integer parsing before issue #108, with their
# ranges and defaults.
FIVE_SETTINGS = {
    "database_connect_timeout_seconds": (2, 60, 3),
    "token_lifetime_days": (1, 365, 7),
    "ai_suggestion_timeout_seconds": (1, 600, 15),
    "ai_summary_timeout_seconds": (1, 600, 60),
    "ai_summary_max_tokens": (1, 100_000, 16_000),
}


@pytest.mark.parametrize(("value", "expected"), accepted_values(2, 60))
def test_database_timeout_takes_a_whole_number_from_2_to_60(
    no_env_file, monkeypatch, value, expected
):
    _set_required(monkeypatch)
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", value)

    assert load_settings().database_connect_timeout_seconds == expected


@pytest.mark.parametrize("value", refused_values(2, 60), ids=value_id)
def test_database_timeout_stops_the_backend_when_invalid(no_env_file, monkeypatch, value):
    _set_required(monkeypatch)

    assert_stops_at_startup(monkeypatch, "DATABASE_CONNECT_TIMEOUT_SECONDS", value, 2, 60)


def test_database_timeout_range_applies_in_code(no_env_file):
    assert_range_applies_in_code(
        "database_connect_timeout_seconds",
        2,
        60,
        database_url=DATABASE_URL,
        cors_allowed_origins=["http://localhost:5173"],
        ai_provider="mock",
    )


def test_every_whole_number_setting_is_found():
    assert set(FIVE_SETTINGS) <= set(INT_FIELDS)
    assert len(INT_FIELDS) >= 16


@pytest.mark.parametrize("field", INT_FIELDS)
@pytest.mark.parametrize("spelling", ["+{}", "{}.0", "0_{}"])
def test_every_whole_number_setting_refuses_lax_spellings(
    no_env_file, monkeypatch, field, spelling
):
    _set_required(monkeypatch)
    variable = field.upper()
    monkeypatch.setenv(variable, spelling.format(Settings.model_fields[field].default))

    with pytest.raises(SettingsError) as error:
        load_settings()

    message = str(error.value)
    assert f"{variable} is invalid: " in message
    assert "must be a whole number" in message


@pytest.mark.parametrize(("field", "expected"), [(f, r[2]) for f, r in FIVE_SETTINGS.items()])
def test_whole_number_setting_defaults_stay_plain_ints(no_env_file, monkeypatch, field, expected):
    _set_required(monkeypatch)

    default = Settings.model_fields[field].default
    assert type(default) is int
    assert default == expected
    assert getattr(load_settings(), field) == expected


def test_no_whole_number_setting_keeps_a_pydantic_range_check():
    # Each range is stated once, in the setting's _whole_number validator.
    for name in INT_FIELDS:
        assert Settings.model_fields[name].metadata == [], name


def test_db_time_limit_setting_defaults_to_ten_seconds(no_env_file, monkeypatch):
    _set_required(monkeypatch)

    assert load_settings().database_query_timeout_seconds == 10


@pytest.mark.parametrize(("value", "expected"), [("1", 1), ("600", 600), (" 30 ", 30)])
def test_db_time_limit_setting_takes_a_whole_number_from_1_to_600(
    no_env_file, monkeypatch, value, expected
):
    _set_required(monkeypatch)
    monkeypatch.setenv("DATABASE_QUERY_TIMEOUT_SECONDS", value)

    assert load_settings().database_query_timeout_seconds == expected


@pytest.mark.parametrize("value", ["", " ", "0", "601", "2.5", "abc", "-1", "+5", "1_0", "1e1"])
def test_db_time_limit_setting_stops_the_backend_when_invalid(no_env_file, monkeypatch, value):
    _set_required(monkeypatch)
    monkeypatch.setenv("DATABASE_QUERY_TIMEOUT_SECONDS", value)

    with pytest.raises(SettingsError) as error:
        create_app()

    message = str(error.value)
    assert message.startswith("Invalid configuration: ")
    assert "DATABASE_QUERY_TIMEOUT_SECONDS is invalid: " in message
    assert "whole number from 1 to 600" in message


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
