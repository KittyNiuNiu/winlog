"""Application settings, read from environment variables.

Locally, values can also come from the repository-root `.env` file (see `.env.example`).
Real environment variables take precedence over the file, and a missing file is ignored.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    EmailStr,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class SettingsError(RuntimeError):
    """The configuration is missing or invalid. The message names the variables."""


# The AI providers AI_PROVIDER can select (issues #12 and #13). app/ai/factory.py has one
# provider for each name, and a unit test checks that the two lists match.
AIProviderName = Literal["mock", "openai-compatible"]

# The provider that calls a real LLM through an OpenAI-compatible chat API (issue #13).
OPENAI_COMPATIBLE = "openai-compatible"

# The error type for a variable that the selected AI provider needs but that is not set.
_MISSING_FOR_AI_PROVIDER = "missing_for_ai_provider"

_EMAIL = TypeAdapter(EmailStr)

# The longest attempt window (FR-A4): one year. A longer one would overflow date arithmetic
# while the app runs, so it stops the app at startup instead.
MAX_ATTEMPT_WINDOW_MINUTES = 525_600


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr
    cors_allowed_origins: Annotated[list[str], NoDecode]
    # Seconds the health check waits for the database to answer, on a new or a pooled
    # connection. Also libpq's connect_timeout for every new connection, which treats values
    # below 2 as 2, so 2 is the minimum.
    database_connect_timeout_seconds: int = Field(default=3, ge=2, le=60)
    # Days a login token works before it expires (FR-A2).
    token_lifetime_days: int = Field(default=7, ge=1, le=365)
    # The AI provider (product-spec.md §8). Required with no default, so the app never uses a
    # real or a fake AI by accident.
    ai_provider: AIProviderName
    # The OpenAI-compatible provider (issue #13). Required when AI_PROVIDER selects it, and
    # ignored otherwise. They come after ai_provider, so their validator can read it.
    ai_base_url: str | None = Field(default=None, validate_default=True)
    ai_api_key: SecretStr | None = Field(default=None, validate_default=True)
    ai_model: str | None = Field(default=None, validate_default=True)
    # Seconds the OpenAI-compatible provider waits for an answer before it gives up.
    ai_suggestion_timeout_seconds: int = Field(default=15, ge=1, le=600)
    ai_summary_timeout_seconds: int = Field(default=60, ge=1, le=600)
    # The most tokens the OpenAI-compatible provider lets the model write for one summary
    # (`max_tokens`, issue #17). A summary has at most 10,000 characters (§7.4). English needs
    # about 1 token per 4 characters, German about 1 per 3, Chinese, Japanese and Korean up to
    # about 1 per character: up to 10,000 tokens. Reasoning tokens count too (up to 3,400 per
    # summary in #14's comparison). 16,000 leaves room for all of that, so it never cuts a valid
    # summary. A larger value only raises the cost bound: the adapter rejects any summary over
    # 10,000 characters, and a model that hits this bound gives "AI unavailable".
    ai_summary_max_tokens: int = Field(default=16_000, ge=1, le=100_000)
    # The most characters the matching entries may have for one summary: each entry's text,
    # Result/Impact and tag names, added up (product-spec.md §7.4, issue #43). Above it, no
    # summary is generated and the user is asked to narrow the filter. A cost limit, so it is
    # a setting. A whole number of 1 or more.
    ai_summary_max_input_characters: int = 50_000
    # Daily AI limits (product-spec.md §8, issue #15). A day runs from 00:00 to 24:00 UTC.
    # Whole numbers of 0 or more; 0 blocks that kind of request.
    ai_daily_suggestions_per_user: int = 10
    ai_daily_summaries_per_user: int = 2
    # Suggestions and summaries of all users together.
    ai_daily_requests_global: int = 100
    # The shared demo account's email (FR-X1, issue #21). Empty or not set turns the demo off.
    # Stored in lower case, as registration stores emails, so it matches the users table.
    demo_email: str | None = None
    # Login and demo-login attempt limits (FR-A4, issue #46). Whole numbers of 1 or more.
    # Failed logins per email: after this many within the window, every login for that email
    # is refused until the window ends. Wrong passwords on account deletion count too.
    login_max_failed_attempts: int = 10
    login_attempt_window_minutes: int = 15
    # Demo-logins per visitor IP address within the window.
    demo_login_max_attempts: int = 20
    demo_login_window_minutes: int = 60

    @field_validator("database_url")
    @classmethod
    def _database_url_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("ai_base_url", "ai_api_key", "ai_model")
    @classmethod
    def _required_by_ai_provider(
        cls, value: str | SecretStr | None, info: ValidationInfo
    ) -> str | SecretStr | None:
        text = value.get_secret_value() if isinstance(value, SecretStr) else value
        if text is None or not text.strip():
            # An empty value, as in `AI_API_KEY=` in .env, counts as not set.
            if info.data.get("ai_provider") == OPENAI_COMPATIBLE:
                raise PydanticCustomError(
                    _MISSING_FOR_AI_PROVIDER, "required by the selected AI provider"
                )
            return None
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("ai_base_url")
    @classmethod
    def _check_ai_base_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return value

    @field_validator(
        "ai_daily_suggestions_per_user",
        "ai_daily_summaries_per_user",
        "ai_daily_requests_global",
        mode="before",
    )
    @classmethod
    def _check_daily_limit(cls, value: object) -> int:
        return _whole_number(value, minimum=0)

    @field_validator("ai_summary_max_input_characters", mode="before")
    @classmethod
    def _check_summary_input_limit(cls, value: object) -> int:
        return _whole_number(value, minimum=1)

    @field_validator("login_max_failed_attempts", "demo_login_max_attempts", mode="before")
    @classmethod
    def _check_attempt_limit(cls, value: object) -> int:
        return _whole_number(value, minimum=1)

    @field_validator("login_attempt_window_minutes", "demo_login_window_minutes", mode="before")
    @classmethod
    def _check_attempt_window(cls, value: object) -> int:
        return _whole_number(value, minimum=1, maximum=MAX_ATTEMPT_WINDOW_MINUTES)

    @field_validator("demo_email", mode="before")
    @classmethod
    def _check_demo_email(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("must be an email address")
        if not value.strip():
            # An empty value, as in `DEMO_EMAIL=` in .env, turns the demo off.
            return None
        try:
            email = _EMAIL.validate_python(value.strip())
        except ValidationError:
            raise ValueError(
                "must be a valid email address, or empty to turn the demo off"
            ) from None
        return email.lower()

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _check_origins(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must list at least one origin")
        for origin in value:
            if not origin.startswith(("http://", "https://")) or origin.endswith("/"):
                raise ValueError(
                    f"'{origin}' must look like https://example.com, without a trailing slash"
                )
        return value


def _whole_number(value: object, *, minimum: int, maximum: int | None = None) -> int:
    """A whole number of `minimum` or more (and at most `maximum`, if given).

    From code or from an environment variable. Stricter than pydantic's int parsing, which
    also accepts "1.0", "+5" and "1_000".
    """
    if maximum is None:
        message = f"must be a whole number of {minimum} or more"
    else:
        message = f"must be a whole number from {minimum} to {maximum}"
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    elif isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        number = int(value.strip())
    else:
        raise ValueError(message)
    if number < minimum or (maximum is not None and number > maximum):
        raise ValueError(message)
    return number


def load_settings() -> Settings:
    """Load the settings, or raise SettingsError naming every missing or invalid variable.

    The message never contains the values themselves, so secrets cannot leak into logs.
    """
    try:
        return Settings()
    except ValidationError as error:
        problems = []
        for item in error.errors(include_url=False, include_input=False):
            name = str(item["loc"][0]).upper() if item["loc"] else "UNKNOWN"
            if item["type"] == "missing":
                problems.append(f"{name} is required but not set")
            elif item["type"] == _MISSING_FOR_AI_PROVIDER:
                problems.append(
                    f"{name} is required when AI_PROVIDER is '{OPENAI_COMPATIBLE}' but not set"
                )
            else:
                problems.append(f"{name} is invalid: {item['msg']}")
        message = "Invalid configuration: " + "; ".join(problems) + ". See .env.example."
        raise SettingsError(message) from None
