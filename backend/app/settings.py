"""Application settings, read from environment variables.

Locally, values can also come from the repository-root `.env` file (see `.env.example`).
Real environment variables take precedence over the file, and a missing file is ignored.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class SettingsError(RuntimeError):
    """The configuration is missing or invalid. The message names the variables."""


# The AI providers AI_PROVIDER can select (issue #12). app/ai/factory.py has one provider for
# each name, and a unit test checks that the two lists match.
AIProviderName = Literal["mock"]


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

    @field_validator("database_url")
    @classmethod
    def _database_url_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

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
            else:
                problems.append(f"{name} is invalid: {item['msg']}")
        message = "Invalid configuration: " + "; ".join(problems) + ". See .env.example."
        raise SettingsError(message) from None
