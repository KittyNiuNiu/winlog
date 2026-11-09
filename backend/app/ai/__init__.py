"""The AI adapter: the only way the backend calls an AI provider (`AGENTS.md`, issue #12).

Features call the AI only through `LimitedAI` (`LimitedAIDependency`), which checks the
daily usage limits before every AI call (issue #15).
"""

from app.ai.adapter import (
    AIError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
    Suggestion,
    SummaryEntry,
)
from app.ai.factory import AI, create_ai_provider, get_ai_provider
from app.ai.limits import (
    AILimitReachedError,
    AILimits,
    LimitedAI,
    LimitedAIDependency,
    get_limited_ai,
)
from app.ai.mock import MockProvider
from app.ai.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "AI",
    "AIError",
    "AILimitReachedError",
    "AILimits",
    "AIProvider",
    "AIProviderError",
    "AITimeoutError",
    "LimitedAI",
    "LimitedAIDependency",
    "MockProvider",
    "OpenAICompatibleProvider",
    "Suggestion",
    "SummaryEntry",
    "create_ai_provider",
    "get_ai_provider",
    "get_limited_ai",
]
