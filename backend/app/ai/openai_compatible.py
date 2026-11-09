"""The OpenAI-compatible AI provider (issue #13, product-spec.md §8).

It calls a real LLM through an OpenAI-compatible Chat Completions API (OpenRouter is planned),
with the official `openai` SDK. AI_PROVIDER=openai-compatible selects it, and AI_BASE_URL,
AI_API_KEY, AI_MODEL and AI_SUMMARY_MAX_TOKENS configure it (`.env.example`).

- One user action makes at most one AI call: the SDK's automatic retries are off.
- Every request asks OpenRouter to route it only to zero-data-retention endpoints
  (`provider: {"zdr": true}`, sent through `extra_body`).
- Suggest sends only the entry text. Summarise sends only each entry's date, category, text,
  Result/Impact and tag names, which is all a `SummaryEntry` holds (data minimisation, §8).
- Summary requests send `max_tokens` (AI_SUMMARY_MAX_TOKENS), which bounds the cost of one
  summary and leaves room for a 10,000-character summary in any language (issue #17).
  Suggestion requests send none: their answer is a short JSON object.
- An answer the model cut off (`finish_reason` "length", for example at `max_tokens`) raises
  `AIProviderError`: a cut-off summary or suggestion is not a usable answer (issue #17).
- Suggestions are asked for as JSON, then parsed and checked here. The adapter
  (`app/ai/adapter.py`) checks the output again, as it does for every provider.
- A timeout raises `AITimeoutError`. Network errors, 4xx and 5xx answers and unreadable
  answers raise `AIProviderError`. The SDK's exception is not chained, because its message
  or the response it holds can contain provider output.

Privacy: this module logs only the model, the response status and the time taken. It never
logs the API key, entry text, tag names or summary text, and its error messages never contain
them (`AGENTS.md`).
"""

import json
import logging
import time
from typing import Any

import httpx2
import openai

from app.ai.adapter import (
    CATEGORIES,
    MAX_SUMMARY_CHARACTERS,
    AIProvider,
    AIProviderError,
    AITimeoutError,
    Suggestion,
    SummaryEntry,
)
from app.settings import OPENAI_COMPATIBLE, Settings, SettingsError

logger = logging.getLogger(__name__)

# OpenRouter's provider routing: only endpoints with a zero-data-retention policy (§8).
ZERO_DATA_RETENTION = {"provider": {"zdr": True}}

_CATEGORY_LIST = ", ".join(f'"{category}"' for category in CATEGORIES)

SUGGEST_PROMPT = f"""\
You help a professional keep a work success diary. The user message is the text of one \
diary entry. Suggest a category and tags for it.

- Category: choose exactly one of {_CATEGORY_LIST}. Write it exactly as shown here, in \
English, whatever language the entry is written in.
- Tags: suggest up to 5 short tag names, such as a project, skill or topic the entry is \
about. Write the tag names in the language of the entry text.

Answer only with a JSON object of this form, and nothing else:
{{"category": "<one of the categories>", "tags": ["<tag name>", "<tag name>"]}}"""

SUMMARISE_PROMPT = f"""\
You help a professional prepare for a performance review. The user message is a JSON list \
of entries from their work success diary. Each entry has a date, a category, a text, an \
optional result or impact, and tags.

Write a review-ready summary of these entries that the user can edit and use in a \
performance review or appraisal conversation. Use only facts from the entries and do not \
invent anything. Keep the summary shorter than {MAX_SUMMARY_CHARACTERS:,} characters.

Write the summary in the language that most of the entries use."""


class OpenAICompatibleProvider(AIProvider):
    name = OPENAI_COMPATIBLE

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        suggestion_timeout_seconds: float,
        summary_timeout_seconds: float,
        summary_max_tokens: int,
        http_client: httpx2.Client | None = None,
    ) -> None:
        """`http_client` lets tests stub the HTTP layer; by default the SDK makes its own."""
        self._client = openai.OpenAI(
            base_url=base_url,
            api_key=api_key,
            # The SDK retries twice by default; one user action makes at most one AI call.
            max_retries=0,
            http_client=http_client,
        )
        self._model = model
        self._suggestion_timeout = suggestion_timeout_seconds
        self._summary_timeout = summary_timeout_seconds
        self._summary_max_tokens = summary_max_tokens

    @classmethod
    def from_settings(
        cls, settings: Settings, http_client: httpx2.Client | None = None
    ) -> "OpenAICompatibleProvider":
        # The settings already require these when AI_PROVIDER selects this provider.
        missing = [
            name
            for name, value in (
                ("AI_BASE_URL", settings.ai_base_url),
                ("AI_API_KEY", settings.ai_api_key),
                ("AI_MODEL", settings.ai_model),
            )
            if value is None
        ]
        if missing:
            raise SettingsError(
                "Invalid configuration: "
                + "; ".join(
                    f"{name} is required when AI_PROVIDER is '{OPENAI_COMPATIBLE}' but not set"
                    for name in missing
                )
                + ". See .env.example."
            )
        assert settings.ai_base_url and settings.ai_api_key and settings.ai_model
        return cls(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key.get_secret_value(),
            model=settings.ai_model,
            suggestion_timeout_seconds=settings.ai_suggestion_timeout_seconds,
            summary_timeout_seconds=settings.ai_summary_timeout_seconds,
            summary_max_tokens=settings.ai_summary_max_tokens,
            http_client=http_client,
        )

    def _suggest(self, text: str) -> Suggestion:
        content = self._complete(
            [
                {"role": "system", "content": SUGGEST_PROMPT},
                {"role": "user", "content": text},
            ],
            timeout=self._suggestion_timeout,
            response_format={"type": "json_object"},
        )
        return _parse_suggestion(content)

    def _summarise(self, entries: tuple[SummaryEntry, ...]) -> str:
        return self._complete(
            [
                {"role": "system", "content": SUMMARISE_PROMPT},
                {"role": "user", "content": _entries_json(entries)},
            ],
            timeout=self._summary_timeout,
            max_tokens=self._summary_max_tokens,
        )

    def _complete(self, messages: list[dict[str, str]], *, timeout: float, **options: Any) -> str:
        """Make one Chat Completions call and return the answer's text."""
        started = time.monotonic()
        status: int | None = None
        try:
            response = self._client.chat.completions.with_raw_response.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                timeout=timeout,
                extra_body=ZERO_DATA_RETENTION,
                **options,
            )
            status = response.http_response.status_code
            completion = response.parse()
            choice = completion.choices[0]
            finish_reason = choice.finish_reason
            content = choice.message.content
        except openai.APITimeoutError:
            raise AITimeoutError("The AI provider did not answer in time.") from None
        except openai.APIStatusError as error:
            status = error.status_code
            raise AIProviderError(f"The AI provider answered with status {status}.") from None
        except openai.APIConnectionError:
            raise AIProviderError("The AI provider could not be reached.") from None
        except Exception:
            # An answer the SDK cannot read, or one without choices or a message.
            raise AIProviderError("The AI provider returned an unreadable answer.") from None
        finally:
            logger.info(
                "AI request to model %s answered with status %s in %d ms",
                self._model,
                status if status is not None else "none",
                round((time.monotonic() - started) * 1000),
            )
        if finish_reason == "length":
            raise AIProviderError("The AI provider cut off its answer at the output limit.")
        if not isinstance(content, str):
            raise AIProviderError("The AI provider returned an answer without text.")
        return content


def _parse_suggestion(content: str) -> Suggestion:
    """Read the JSON suggestion. Anything but one category and non-empty tag names fails."""
    try:
        answer = json.loads(content)
    except ValueError:
        raise AIProviderError("The AI provider returned a suggestion that is not JSON.") from None
    if not isinstance(answer, dict):
        raise AIProviderError("The AI provider returned a suggestion that is not an object.")
    category = answer.get("category")
    if not isinstance(category, str) or category not in CATEGORIES:
        raise AIProviderError("The AI provider suggested a category that does not exist.")
    tags = answer.get("tags")
    if not isinstance(tags, list):
        raise AIProviderError("The AI provider returned tags that are not a list.")
    if not all(isinstance(tag, str) and tag.strip() for tag in tags):
        raise AIProviderError("The AI provider suggested an empty or invalid tag name.")
    return Suggestion(category=category, tags=tags)  # type: ignore[arg-type]


def _entries_json(entries: tuple[SummaryEntry, ...]) -> str:
    """The entries as JSON, with only the fields summarise may send (§8)."""
    return json.dumps(
        [
            {
                "date": entry.date.isoformat(),
                "category": entry.category,
                "text": entry.text,
                "result_impact": entry.result_impact,
                "tags": list(entry.tags),
            }
            for entry in entries
        ],
        ensure_ascii=False,
    )
