"""The provider-agnostic AI adapter (issue #12, product-spec.md §8).

All AI calls go through an `AIProvider` (`AGENTS.md`). It has two operations:

- `suggest(text)`: a category and tag names for an entry text (FR-S1).
- `summarise(entries)`: a summary text for a list of entries (FR-G1).

The interface is sync, like the rest of the backend (issue #4): FastAPI runs sync endpoints
in a thread pool.

Every provider subclasses `AIProvider` and implements `_suggest` and `_summarise`. The public
methods check the provider's output, so every provider shares the same rules:

- A suggestion has one of the four categories and a list of valid tag names. Tag names are
  normalised as `app.tags.normalise_tag_name` does.
- A summary is a text that is not blank and has at most `MAX_SUMMARY_CHARACTERS` characters
  (product-spec.md §7.4). A longer summary is an unusable answer, not one to shorten
  (product owner decision on issue #17).
- Output that breaks these rules raises `AIProviderError`.
- A provider failure that is not an `AIError` also becomes an `AIProviderError`.

Data minimisation: `summarise` takes only `SummaryEntry` objects, which hold an entry's date,
category, text, Result/Impact and tag names, and nothing else. User ids, emails and entry ids
cannot reach a provider through it.

Telemetry (issue #74): every call gets an `ai.{operation}` span and a
`winlog.ai.request.duration` measurement (app/telemetry.py).

Privacy: the adapter logs only the operation, the provider, the number of entries, the time
taken and the error type, in the message and as allowlisted fields. It never logs entry text,
tag names or summary text, and its error messages never contain them (`AGENTS.md`).
"""

import datetime as dt
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import ClassVar, get_args

from app import telemetry
from app.entries import Category, Entry
from app.tags import normalise_tag_name
from app.telemetry import AIOutcome
from app.text_rules import has_unstorable_characters, is_blank

logger = logging.getLogger(__name__)

CATEGORIES: tuple[str, ...] = get_args(Category)

# product-spec.md §7.4: "A summary's text is at most 10,000 characters." Counted as characters
# (Unicode code points), not bytes. A fixed rule of the spec, not a setting.
MAX_SUMMARY_CHARACTERS = 10_000


class AIError(Exception):
    """An AI call did not give a usable answer. The message never contains user content."""


class AITimeoutError(AIError):
    """The AI provider did not answer in time."""


class AIProviderError(AIError):
    """Any other provider failure, including output that breaks the adapter's rules."""


@dataclass(frozen=True, slots=True)
class Suggestion:
    """Suggest's answer: one of the four categories and a list of tag names."""

    category: Category
    tags: list[str]


@dataclass(frozen=True, slots=True)
class SummaryEntry:
    """The only data of an entry that summarise receives (product-spec.md §8)."""

    date: dt.date
    category: Category
    text: str
    result_impact: str | None
    tags: tuple[str, ...]

    @classmethod
    def from_entry(cls, entry: Entry) -> "SummaryEntry":
        """Copy only the fields summarise may receive; the entry's id stays behind."""
        return cls(
            date=entry.date,
            category=entry.category,
            text=entry.text,
            result_impact=entry.result_impact,
            tags=tuple(entry.tags),
        )


class AIProvider(ABC):
    """An AI provider. Subclasses implement `_suggest` and `_summarise`."""

    name: ClassVar[str]

    def suggest(self, text: str) -> Suggestion:
        """Suggest a category and tag names for an entry text.

        Raises `AITimeoutError` or `AIProviderError` when the provider gives no usable answer.
        """
        text = check_suggest_input(text)
        return self._call("suggest", None, lambda: _checked_suggestion(self._suggest(text)))

    def summarise(self, entries: Sequence[SummaryEntry]) -> str:
        """Write a summary text for the entries.

        Raises `AITimeoutError` or `AIProviderError` when the provider gives no usable answer.
        """
        entries = check_summarise_input(entries)
        return self._call(
            "summarise", len(entries), lambda: _checked_summary(self._summarise(entries))
        )

    @abstractmethod
    def _suggest(self, text: str) -> Suggestion:
        """Ask the provider for a suggestion. The adapter checks the output."""

    @abstractmethod
    def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
        """Ask the provider for a summary. The adapter checks the output."""

    def _call[T](self, operation: str, entry_count: int | None, call: Callable[[], T]) -> T:
        # The span, the duration metric and the log fields hold only allowlisted values
        # (app/telemetry.py): the operation, the provider, the outcome and the entry count.
        attributes: dict[str, object] = {
            "winlog.ai.operation": operation,
            "winlog.ai.provider": self.name,
        }
        if entry_count is not None:
            attributes["winlog.entry_count"] = entry_count
        started = time.monotonic()
        with telemetry.span(f"ai.{operation}", attributes) as span:
            try:
                try:
                    result = call()
                except AIError:
                    raise
                except Exception as error:
                    raise AIProviderError("The AI provider failed.") from error
            except AIError as error:
                outcome: AIOutcome = (
                    "timeout" if isinstance(error, AITimeoutError) else "provider_error"
                )
                span.set("winlog.ai.outcome", outcome)
                telemetry.record_ai_call(operation, self.name, outcome, time.monotonic() - started)
                logger.warning(
                    "AI %s with provider %s failed after %d ms%s: %s",
                    operation,
                    self.name,
                    _elapsed_ms(started),
                    _entry_count(entry_count),
                    type(error).__name__,
                    extra={
                        **attributes,
                        "winlog.ai.outcome": outcome,
                        "duration_ms": _elapsed_ms(started),
                        "error.type": type(error).__name__,
                    },
                )
                raise
            span.set("winlog.ai.outcome", "success")
            telemetry.record_ai_call(operation, self.name, "success", time.monotonic() - started)
            logger.info(
                "AI %s with provider %s succeeded in %d ms%s",
                operation,
                self.name,
                _elapsed_ms(started),
                _entry_count(entry_count),
                extra={
                    **attributes,
                    "winlog.ai.outcome": "success",
                    "duration_ms": _elapsed_ms(started),
                },
            )
            return result


def check_suggest_input(text: object) -> str:
    """Raise TypeError unless suggest can send this text. Used before any AI call is counted."""
    if not isinstance(text, str):
        raise TypeError("suggest takes the entry text as a string")
    return text


def check_summarise_input(entries: Iterable[SummaryEntry]) -> tuple[SummaryEntry, ...]:
    """Raise unless summarise can send these entries. Used before any AI call is counted."""
    entries = tuple(entries)
    if not entries:
        # product-spec.md §8 and openapi.yaml: no entries means no AI call (issue #17).
        raise ValueError("summarise needs at least one entry")
    if not all(type(entry) is SummaryEntry for entry in entries):
        raise TypeError("summarise takes only SummaryEntry objects (data minimisation, §8)")
    return entries


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _entry_count(entry_count: int | None) -> str:
    return "" if entry_count is None else f" for {entry_count} entries"


def _checked_suggestion(output: object) -> Suggestion:
    if not isinstance(output, Suggestion):
        raise AIProviderError("The AI provider returned no suggestion.")
    if output.category not in CATEGORIES:
        raise AIProviderError("The AI provider suggested a category that does not exist.")
    if not isinstance(output.tags, list | tuple):
        raise AIProviderError("The AI provider returned tags that are not a list.")
    tags = []
    for tag in output.tags:
        if not isinstance(tag, str) or has_unstorable_characters(tag):
            raise AIProviderError("The AI provider suggested an invalid tag name.")
        name = normalise_tag_name(tag)
        if not name:
            raise AIProviderError("The AI provider suggested an empty tag name.")
        tags.append(name)
    return Suggestion(category=output.category, tags=tags)


def _checked_summary(output: object) -> str:
    if not isinstance(output, str):
        raise AIProviderError("The AI provider returned a summary that is not text.")
    if has_unstorable_characters(output):
        raise AIProviderError("The AI provider returned a summary that cannot be stored.")
    if is_blank(output):
        raise AIProviderError("The AI provider returned an empty summary.")
    if len(output) > MAX_SUMMARY_CHARACTERS:
        raise AIProviderError(
            f"The AI provider returned a summary longer than {MAX_SUMMARY_CHARACTERS:,} characters."
        )
    return output
