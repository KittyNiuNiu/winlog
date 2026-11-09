"""The AI adapter: the only way the backend calls an AI provider (`AGENTS.md`, issue #12)."""

from app.ai.adapter import (
    AIError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
    Suggestion,
    SummaryEntry,
)
from app.ai.factory import AI, create_ai_provider, get_ai_provider
from app.ai.mock import MockProvider

__all__ = [
    "AI",
    "AIError",
    "AIProvider",
    "AIProviderError",
    "AITimeoutError",
    "MockProvider",
    "Suggestion",
    "SummaryEntry",
    "create_ai_provider",
    "get_ai_provider",
]
