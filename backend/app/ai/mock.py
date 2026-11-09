"""The mock AI provider (issue #12): for automated tests and local development.

It needs no API key and makes no network call (product-spec.md §8 and §9).

- Deterministic: the same input always gives the same output. The suggested category comes
  from a SHA-256 hash of the text, not from Python's `hash()`, which changes between runs.
- Obviously fake: the default summary starts with "Mock summary" and the default tag is
  "Mock tag", so the output is never mistaken for real AI output.
- Configurable in tests: `return_suggestion`, `return_summary`, `raise_timeout` and
  `raise_provider_error` change what it does until `reset` is called. Configured output goes
  through the adapter's checks like any provider's, so invalid output raises
  `AIProviderError`.
- `suggest_calls` and `summarise_calls` record what each call received, so tests can check
  what would have been sent to a provider. They are kept in memory only and never logged.
"""

import hashlib

from app.ai.adapter import (
    CATEGORIES,
    AIError,
    AIProvider,
    AIProviderError,
    AITimeoutError,
    Suggestion,
    SummaryEntry,
)

MOCK_TAG = "Mock tag"
MOCK_SUMMARY_PREFIX = "Mock summary"

# "No output configured". Not None, so tests can configure None as invalid output.
_DEFAULT = object()


class MockProvider(AIProvider):
    name = "mock"

    def __init__(self) -> None:
        self.suggest_calls: list[str] = []
        self.summarise_calls: list[tuple[SummaryEntry, ...]] = []
        self.reset()

    def reset(self) -> None:
        """Go back to the default output. The recorded calls are kept."""
        self._suggestion: object = _DEFAULT
        self._summary: object = _DEFAULT
        self._error: type[AIError] | None = None

    def return_suggestion(self, suggestion: Suggestion) -> None:
        """Make suggest return this suggestion."""
        self._suggestion = suggestion

    def return_summary(self, summary: str) -> None:
        """Make summarise return this summary text."""
        self._summary = summary

    def raise_timeout(self) -> None:
        """Make both operations raise `AITimeoutError`."""
        self._error = AITimeoutError

    def raise_provider_error(self) -> None:
        """Make both operations raise `AIProviderError`."""
        self._error = AIProviderError

    def _suggest(self, text: str) -> Suggestion:
        self.suggest_calls.append(text)
        self._raise_if_configured()
        if self._suggestion is not _DEFAULT:
            return self._suggestion  # type: ignore[return-value]  (the adapter checks it)
        digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()
        return Suggestion(category=CATEGORIES[digest[0] % len(CATEGORIES)], tags=[MOCK_TAG])

    def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
        self.summarise_calls.append(entries)
        self._raise_if_configured()
        if self._summary is not _DEFAULT:
            return self._summary  # type: ignore[return-value]  (the adapter checks it)
        dates = sorted(entry.date for entry in entries)
        count = "1 entry" if len(entries) == 1 else f"{len(entries)} entries"
        return f"{MOCK_SUMMARY_PREFIX} of {count} from {dates[0]} to {dates[-1]}."

    def _raise_if_configured(self) -> None:
        if self._error is AITimeoutError:
            raise AITimeoutError("The mock AI provider was set to time out.")
        if self._error is AIProviderError:
            raise AIProviderError("The mock AI provider was set to fail.")
