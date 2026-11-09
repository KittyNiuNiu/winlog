"""Selecting the AI provider from AI_PROVIDER (issue #12).

`create_app` calls `create_ai_provider` once at startup and keeps the provider on
`app.state.ai_provider`. Endpoints get it through the `get_ai_provider` dependency, which
tests can override.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from app.ai.adapter import AIProvider
from app.ai.mock import MockProvider
from app.settings import Settings, SettingsError

# One provider for each name in app.settings.AIProviderName. #13 adds the OpenAI-compatible one.
PROVIDERS: dict[str, Callable[[Settings], AIProvider]] = {
    "mock": lambda settings: MockProvider(),
}


def create_ai_provider(settings: Settings) -> AIProvider:
    """Return the provider AI_PROVIDER selects, or raise SettingsError naming the allowed values."""
    create = PROVIDERS.get(settings.ai_provider)
    if create is None:
        allowed = ", ".join(f"'{name}'" for name in PROVIDERS)
        raise SettingsError(
            f"Invalid configuration: AI_PROVIDER is invalid: must be one of {allowed}. "
            "See .env.example."
        )
    return create(settings)


def get_ai_provider(request: Request) -> AIProvider:
    """FastAPI dependency: the app's AI provider."""
    return request.app.state.ai_provider


AI = Annotated[AIProvider, Depends(get_ai_provider)]
