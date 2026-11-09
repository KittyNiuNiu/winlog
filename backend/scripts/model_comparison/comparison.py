"""The default-model comparison (issue #14, product-spec.md §13).

Run by hand from `backend/`, never in the automated tests or CI. Three commands:

- `check MODEL...`: free. Reads OpenRouter's public model list and zero-data-retention (ZDR)
  endpoint list and shows, for each candidate, whether it exists, its ZDR endpoints, their
  prices and an estimate of what one comparison run costs. Makes no AI call.
- `run MODEL... --confirm-paid-calls`: makes real, paid AI calls. Each candidate with a ZDR
  endpoint gets every entry of the fixed test set as a suggestion and every summary case as
  a summary, through the #13 provider (`OpenAICompatibleProvider`), so the prompts, the
  `zdr` setting, the JSON parsing and the timeouts are the ones production uses. One call per
  item, no retries. Results go to one JSON file per candidate.
- `report RESULTS_DIR`: after a person has filled in the review fields of the result files
  (language of tags and summaries, summary quality 1-5), prints the results table for the
  decision note (`docs/decisions/default-model.md`).

The API key comes only from the environment (`AI_API_KEY`), for example with
`uv run --env-file ../.env python -m scripts.model_comparison ...`. It is never printed,
logged or written to a result file.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO, get_args

import httpx2
import openai

from app.ai import AIError, OpenAICompatibleProvider, SummaryEntry

# _entries_json builds the summary request exactly as production does; the size estimates
# use it so that they match.
from app.ai.openai_compatible import SUGGEST_PROMPT, SUMMARISE_PROMPT, _entries_json
from app.entries import Category
from app.settings import Settings

HERE = Path(__file__).resolve().parent
TEST_SET_PATH = HERE / "test_set.json"
RESULTS_PATH = HERE / "results"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_VARIABLE = "AI_API_KEY"
BASE_URL_VARIABLE = "AI_BASE_URL"

CATEGORIES: tuple[str, ...] = get_args(Category)

# Production's timeouts: the settings' defaults (AI_SUGGESTION_TIMEOUT_SECONDS and
# AI_SUMMARY_TIMEOUT_SECONDS, `.env.example`).
SUGGESTION_TIMEOUT_SECONDS: int = Settings.model_fields["ai_suggestion_timeout_seconds"].default
SUMMARY_TIMEOUT_SECONDS: int = Settings.model_fields["ai_summary_timeout_seconds"].default
# Production's summary output bound: the default of AI_SUMMARY_MAX_TOKENS (issue #17).
SUMMARY_MAX_TOKENS: int = Settings.model_fields["ai_summary_max_tokens"].default

# Limits from product-spec.md §7.2, §7.4 and §8, used to check the test set and to estimate
# the maximum daily cost.
MAX_TEXT_CHARACTERS = 2_000
MAX_RESULT_IMPACT_CHARACTERS = 500
MAX_TAGS = 10
MAX_TAG_CHARACTERS = 40
MAX_SUMMARY_INPUT_CHARACTERS = 50_000
MAX_SUMMARY_CHARACTERS = 10_000
GLOBAL_DAILY_AI_REQUESTS = 100

# Estimates, used only where no measured number exists. Deliberately pessimistic: fewer
# characters per token than typical English text (about 4) means more tokens and a higher
# cost. The output allowances leave room for reasoning tokens.
CHARACTERS_PER_TOKEN_ESTIMATE = 3
SUGGESTION_OUTPUT_TOKENS_ESTIMATE = 500
SUMMARY_OUTPUT_TOKENS_ESTIMATE = 4_000


class ComparisonError(Exception):
    """The comparison cannot go on. The message says why and never contains the API key."""


# --- The test set ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SampleEntry:
    id: str
    language: str
    expected_category: str
    date: dt.date
    text: str
    result_impact: str | None
    tags: tuple[str, ...]

    def summary_entry(self) -> SummaryEntry:
        """The entry as the summary endpoint would send it: the fields §8 allows."""
        return SummaryEntry(
            date=self.date,
            category=self.expected_category,  # type: ignore[arg-type]  (checked on load)
            text=self.text,
            result_impact=self.result_impact,
            tags=self.tags,
        )


@dataclass(frozen=True, slots=True)
class SummaryCase:
    id: str
    expected_language: str
    entry_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SampleSet:
    languages: dict[str, str]
    entries: tuple[SampleEntry, ...]
    summary_cases: tuple[SummaryCase, ...]
    sha256: str

    def entry(self, entry_id: str) -> SampleEntry:
        return next(entry for entry in self.entries if entry.id == entry_id)

    def summary_entries(self, case: SummaryCase) -> tuple[SummaryEntry, ...]:
        return tuple(self.entry(entry_id).summary_entry() for entry_id in case.entry_ids)


def load_test_set(path: Path = TEST_SET_PATH) -> SampleSet:
    """Read and check the test set. Raises ComparisonError naming the first problem."""
    raw = path.read_bytes()
    data = json.loads(raw)
    languages = data["languages"]
    entries = []
    for item in data["entries"]:
        entry = SampleEntry(
            id=item["id"],
            language=item["language"],
            expected_category=item["expected_category"],
            date=dt.date.fromisoformat(item["date"]),
            text=item["text"],
            result_impact=item["result_impact"],
            tags=tuple(item["tags"]),
        )
        _check_entry(entry, languages)
        entries.append(entry)
    ids = [entry.id for entry in entries]
    if len(set(ids)) != len(ids):
        raise ComparisonError("Test set: entry ids are not unique.")
    cases = []
    for item in data["summary_cases"]:
        case = SummaryCase(
            id=item["id"],
            expected_language=item["expected_language"],
            entry_ids=tuple(item["entry_ids"]),
        )
        unknown = [entry_id for entry_id in case.entry_ids if entry_id not in ids]
        if unknown or not case.entry_ids:
            raise ComparisonError(f"Test set: summary case {case.id} has unknown or no entries.")
        if case.expected_language not in languages:
            raise ComparisonError(f"Test set: summary case {case.id} has an unknown language.")
        cases.append(case)
    if len({case.id for case in cases}) != len(cases):
        raise ComparisonError("Test set: summary case ids are not unique.")
    test_set = SampleSet(
        languages=dict(languages),
        entries=tuple(entries),
        summary_cases=tuple(cases),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    for case in cases:
        size = len(_entries_json(test_set.summary_entries(case)))
        if size > MAX_SUMMARY_INPUT_CHARACTERS:
            raise ComparisonError(f"Test set: summary case {case.id} is too large to summarise.")
    return test_set


def _check_entry(entry: SampleEntry, languages: dict[str, str]) -> None:
    problem = None
    if entry.language not in languages:
        problem = "an unknown language"
    elif entry.expected_category not in CATEGORIES:
        problem = "a category that does not exist"
    elif not entry.text.strip() or len(entry.text) > MAX_TEXT_CHARACTERS:
        problem = "an empty or too long text"
    elif entry.result_impact is not None and (
        not entry.result_impact.strip() or len(entry.result_impact) > MAX_RESULT_IMPACT_CHARACTERS
    ):
        problem = "an empty or too long Result/Impact"
    elif len(entry.tags) > MAX_TAGS or any(
        not tag.strip() or len(tag) > MAX_TAG_CHARACTERS for tag in entry.tags
    ):
        problem = "too many tags or an invalid tag"
    if problem:
        raise ComparisonError(f"Test set: entry {entry.id} has {problem}.")


# --- OpenRouter's public model and ZDR lists -----------------------------------------------


@dataclass(frozen=True, slots=True)
class ZdrEndpoint:
    provider_name: str
    prompt_price: float
    completion_price: float
    supports_response_format: bool


@dataclass(frozen=True, slots=True)
class Availability:
    """What OpenRouter lists for one candidate model."""

    model: str
    exists: bool
    # ZDR endpoints that do not retain prompts at all. Endpoints with "safety retention" (they
    # may keep prompts that a safety classifier flags) are not counted (product-spec.md §8).
    zdr_endpoints: tuple[ZdrEndpoint, ...]
    safety_retention_endpoints: int
    list_prompt_price: float | None
    list_completion_price: float | None

    @property
    def excluded_reason(self) -> str | None:
        if not self.exists:
            return "not listed by OpenRouter"
        if not self.zdr_endpoints:
            if self.safety_retention_endpoints:
                return "its only ZDR endpoints may keep prompts flagged by safety checks"
            return "no zero-data-retention endpoint"
        return None

    @property
    def max_prices(self) -> tuple[float, float]:
        """The highest prompt and completion price per token among its ZDR endpoints."""
        return (
            max(endpoint.prompt_price for endpoint in self.zdr_endpoints),
            max(endpoint.completion_price for endpoint in self.zdr_endpoints),
        )


def fetch_catalogue(client: httpx2.Client, base_url: str) -> tuple[list[dict], list[dict]]:
    """OpenRouter's model list and ZDR endpoint list. Both are public and free."""
    lists = []
    for path in ("/models", "/endpoints/zdr"):
        try:
            response = client.get(base_url.rstrip("/") + path, timeout=30)
            response.raise_for_status()
            lists.append(response.json()["data"])
        except (httpx2.HTTPError, ValueError, KeyError) as error:
            raise ComparisonError(
                f"Could not read OpenRouter's list {path}: {type(error).__name__}."
            ) from None
    return lists[0], lists[1]


def availability(model: str, models: list[dict], zdr_endpoints: list[dict]) -> Availability:
    listed = next((item for item in models if item.get("id") == model), None)
    if listed is None:
        return Availability(model, False, (), 0, None, None)
    # The ZDR list names models by their permanent slug, which /models calls canonical_slug.
    slugs = {model, listed.get("canonical_slug")}
    endpoints = [item for item in zdr_endpoints if item.get("model_id") in slugs]
    usable = tuple(
        ZdrEndpoint(
            provider_name=str(item.get("provider_name")),
            prompt_price=_price(item["pricing"], "prompt"),
            completion_price=_price(item["pricing"], "completion"),
            supports_response_format="response_format" in item.get("supported_parameters", []),
        )
        for item in endpoints
        if not item.get("safety_retention", False)
    )
    return Availability(
        model=model,
        exists=True,
        zdr_endpoints=usable,
        safety_retention_endpoints=len(endpoints) - len(usable),
        list_prompt_price=_price(listed["pricing"], "prompt"),
        list_completion_price=_price(listed["pricing"], "completion"),
    )


def _price(pricing: dict, key: str) -> float:
    """A price per token in USD, after any discount OpenRouter lists."""
    return float(pricing[key]) * (1 - float(pricing.get("discount", 0) or 0))


def estimated_run_tokens(test_set: SampleSet) -> tuple[int, int]:
    """Estimated input and output tokens of one candidate's run (pessimistic)."""
    input_characters = sum(len(SUGGEST_PROMPT) + len(entry.text) for entry in test_set.entries)
    input_characters += sum(
        len(SUMMARISE_PROMPT) + len(_entries_json(test_set.summary_entries(case)))
        for case in test_set.summary_cases
    )
    output_tokens = (
        len(test_set.entries) * SUGGESTION_OUTPUT_TOKENS_ESTIMATE
        + len(test_set.summary_cases) * SUMMARY_OUTPUT_TOKENS_ESTIMATE
    )
    return _tokens(input_characters), output_tokens


def _tokens(characters: int) -> int:
    return -(-characters // CHARACTERS_PER_TOKEN_ESTIMATE)


def check(
    models: Sequence[str], client: httpx2.Client, base_url: str, test_set: SampleSet, out: TextIO
) -> list[Availability]:
    """Print what OpenRouter lists for each candidate, and what one run would cost."""
    catalogue, zdr = fetch_catalogue(client, base_url)
    input_tokens, output_tokens = estimated_run_tokens(test_set)
    today = dt.datetime.now(dt.UTC).date().isoformat()
    out.write(
        f"OpenRouter lists on {today} (UTC). Prices in USD per million tokens; the run cost "
        f"assumes {input_tokens:,} input and {output_tokens:,} output tokens per candidate "
        "at the highest ZDR price.\n\n"
        "| Model | ZDR endpoints (providers) | response_format | Input price | Output price "
        "| Est. run cost | Excluded because |\n|---|---|---|---|---|---|---|\n"
    )
    results = []
    total = 0.0
    for model in models:
        found = availability(model, catalogue, zdr)
        results.append(found)
        if found.excluded_reason:
            out.write(f"| {model} | - | - | - | - | - | {found.excluded_reason} |\n")
            continue
        prompt, completion = found.max_prices
        cost = input_tokens * prompt + output_tokens * completion
        total += cost
        providers = ", ".join(sorted({e.provider_name for e in found.zdr_endpoints}))
        formats = sum(e.supports_response_format for e in found.zdr_endpoints)
        out.write(
            f"| {model} | {len(found.zdr_endpoints)} ({providers}) "
            f"| {formats} of {len(found.zdr_endpoints)} | {_per_million(prompt)} "
            f"| {_per_million(completion)} | ${cost:.4f} | |\n"
        )
    out.write(f"\nEstimated cost of one run for all usable candidates: ${total:.4f}\n")
    return results


def _per_million(price: float) -> str:
    return f"${price * 1_000_000:.3f}"


# --- Running the comparison ---------------------------------------------------------------


class AnswerRecorder:
    """An httpx event hook that keeps the last raw answer of the AI provider.

    It gives the script what the provider does not return: the answer's text before parsing
    (to count valid JSON), the token usage and OpenRouter's cost.
    """

    def __init__(self) -> None:
        self.answer: dict[str, Any] | None = None

    def __call__(self, response: httpx2.Response) -> None:
        if not response.request.url.path.endswith("/chat/completions"):
            return
        response.read()
        try:
            body = response.json()
        except ValueError:
            body = None
        self.answer = {"status": response.status_code, "body": body}

    def take(self) -> dict[str, Any]:
        """The last answer's text, usage, model and provider, then forget it."""
        answer, self.answer = self.answer, None
        body = answer["body"] if answer and isinstance(answer["body"], dict) else {}
        content = None
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        return {
            "status": answer["status"] if answer else None,
            "content": content if isinstance(content, str) else None,
            "usage": body.get("usage") if isinstance(body.get("usage"), dict) else None,
            "served_model": body.get("model"),
            "served_provider": body.get("provider"),
        }


def is_plain_json_object(content: str | None) -> bool:
    """Whether the provider can read the answer as JSON: a plain JSON object, nothing else.

    The same first check as `app.ai.openai_compatible._parse_suggestion`, so a Markdown-fenced
    answer counts as invalid, as it does in production (issue #13).
    """
    if content is None:
        return False
    try:
        return isinstance(json.loads(content), dict)
    except ValueError:
        return False


def call_cost(usage: dict | None, prices: tuple[float, float]) -> tuple[float | None, str]:
    """The cost of one call in USD, and where the number comes from."""
    if not usage:
        return None, "unknown"
    if isinstance(usage.get("cost"), int | float):
        return float(usage["cost"]), "OpenRouter usage.cost"
    prompt_tokens, completion_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        return prompt_tokens * prices[0] + completion_tokens * prices[1], "tokens x ZDR price"
    return None, "unknown"


def make_provider(
    model: str,
    base_url: str,
    api_key: str,
    recorder: AnswerRecorder,
    transport: httpx2.BaseTransport | None = None,
) -> OpenAICompatibleProvider:
    """The production provider for this model, with the SDK's default HTTP client plus the
    recorder. Tests pass a mock transport."""
    options: dict[str, Any] = {"event_hooks": {"response": [recorder]}}
    if transport is not None:
        options["transport"] = transport
    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        model=model,
        suggestion_timeout_seconds=SUGGESTION_TIMEOUT_SECONDS,
        summary_timeout_seconds=SUMMARY_TIMEOUT_SECONDS,
        summary_max_tokens=SUMMARY_MAX_TOKENS,
        http_client=openai.DefaultHttpxClient(**options),
    )


def run_candidate(
    found: Availability,
    test_set: SampleSet,
    provider: OpenAICompatibleProvider,
    recorder: AnswerRecorder,
    *,
    clock: Callable[[], float] = time.perf_counter,
    today: dt.date,
) -> dict[str, Any]:
    """Run the test set on one candidate. Every item gets exactly one call."""
    prices = found.max_prices
    suggestions = []
    for entry in test_set.entries:
        started = clock()
        error = suggestion = None
        try:
            suggestion = provider.suggest(entry.text)
        except AIError as failure:
            error = f"{type(failure).__name__}: {failure}"
        seconds = clock() - started
        answer = recorder.take()
        cost, cost_source = call_cost(answer["usage"], prices)
        suggestions.append(
            {
                "entry_id": entry.id,
                "language": entry.language,
                "expected_category": entry.expected_category,
                "category": suggestion.category if suggestion else None,
                "category_matches": bool(suggestion)
                and suggestion.category == entry.expected_category,
                "tags": suggestion.tags if suggestion else None,
                "valid_json_first_try": is_plain_json_object(answer["content"]),
                "error": error,
                "seconds": round(seconds, 3),
                "cost_usd": cost,
                "cost_source": cost_source,
                **answer,
                "review": {"tags_in_input_language": None if suggestion else False},
            }
        )
    summaries = []
    for case in test_set.summary_cases:
        entries = test_set.summary_entries(case)
        started = clock()
        error = summary = None
        try:
            summary = provider.summarise(entries)
        except AIError as failure:
            error = f"{type(failure).__name__}: {failure}"
        seconds = clock() - started
        answer = recorder.take()
        cost, cost_source = call_cost(answer["usage"], prices)
        summaries.append(
            {
                "case_id": case.id,
                "expected_language": case.expected_language,
                "entry_count": len(entries),
                "summary": summary,
                "summary_characters": len(summary) if summary else 0,
                "error": error,
                "seconds": round(seconds, 3),
                "cost_usd": cost,
                "cost_source": cost_source,
                **{key: value for key, value in answer.items() if key != "content"},
                "review": (
                    {"in_input_language": None, "quality": None, "notes": ""}
                    if summary
                    else {"in_input_language": False, "quality": 1, "notes": "No summary."}
                ),
            }
        )
    return {
        "date": today.isoformat(),
        "model": found.model,
        "zdr_endpoints": [
            {
                "provider_name": endpoint.provider_name,
                "prompt_price_per_million_usd": endpoint.prompt_price * 1_000_000,
                "completion_price_per_million_usd": endpoint.completion_price * 1_000_000,
                "supports_response_format": endpoint.supports_response_format,
            }
            for endpoint in found.zdr_endpoints
        ],
        "max_zdr_prompt_price_per_token_usd": prices[0],
        "max_zdr_completion_price_per_token_usd": prices[1],
        "suggestions": suggestions,
        "summaries": summaries,
    }


def run(
    models: Sequence[str],
    *,
    api_key: str,
    base_url: str,
    out_dir: Path,
    test_set: SampleSet,
    catalogue_client: httpx2.Client,
    transport: httpx2.BaseTransport | None = None,
    today: dt.date,
    out: TextIO,
) -> None:
    """Run the comparison and write one result file per candidate plus `run.json`."""
    catalogue, zdr = fetch_catalogue(catalogue_client, base_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    excluded = []
    for model in models:
        found = availability(model, catalogue, zdr)
        if found.excluded_reason:
            excluded.append({"model": model, "reason": found.excluded_reason})
            out.write(f"{model}: excluded, {found.excluded_reason}.\n")
            continue
        out.write(f"{model}: running {len(test_set.entries)} suggestions and ")
        out.write(f"{len(test_set.summary_cases)} summaries...\n")
        recorder = AnswerRecorder()
        provider = make_provider(model, base_url, api_key, recorder, transport)
        result = run_candidate(found, test_set, provider, recorder, today=today)
        _write_json(out_dir / f"{_file_name(model)}.json", result)
    _write_json(
        out_dir / "run.json",
        {
            "date": today.isoformat(),
            "base_url": base_url,
            "candidates": list(models),
            "excluded": excluded,
            "test_set": str(TEST_SET_PATH.relative_to(HERE.parents[1])),
            "test_set_sha256": test_set.sha256,
            "suggest_prompt_sha256": _sha256(SUGGEST_PROMPT),
            "summarise_prompt_sha256": _sha256(SUMMARISE_PROMPT),
            "suggestion_timeout_seconds": SUGGESTION_TIMEOUT_SECONDS,
            "summary_timeout_seconds": SUMMARY_TIMEOUT_SECONDS,
        },
    )
    out.write(f"Results written to {out_dir}. Fill in every review field, then run report.\n")


def _file_name(model: str) -> str:
    return model.replace("/", "__").replace(":", "_")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --- The report ---------------------------------------------------------------------------


def missing_reviews(result: dict) -> list[str]:
    """The review fields a person still has to fill in."""
    missing = [
        f"{result['model']} {item['entry_id']}: tags_in_input_language"
        for item in result["suggestions"]
        if not isinstance(item["review"].get("tags_in_input_language"), bool)
    ]
    for item in result["summaries"]:
        review = item["review"]
        if not isinstance(review.get("in_input_language"), bool):
            missing.append(f"{result['model']} {item['case_id']}: in_input_language")
        quality = review.get("quality")
        if not isinstance(quality, int) or isinstance(quality, bool) or not 1 <= quality <= 5:
            missing.append(f"{result['model']} {item['case_id']}: quality (1-5)")
    return missing


def max_daily_cost(result: dict) -> float:
    """The cost of the global daily cap if every request were the largest possible summary.

    Input: the largest summary input (§7.4) plus the prompt. Output: the longest summary (§7.4)
    plus the most reasoning tokens seen in this run. Both at the highest ZDR price.
    """
    input_tokens = _tokens(MAX_SUMMARY_INPUT_CHARACTERS + len(SUMMARISE_PROMPT))
    reasoning = max(
        (_reasoning_tokens(item.get("usage")) for item in result["summaries"]), default=0
    )
    output_tokens = _tokens(MAX_SUMMARY_CHARACTERS) + reasoning
    per_request = (
        input_tokens * result["max_zdr_prompt_price_per_token_usd"]
        + output_tokens * result["max_zdr_completion_price_per_token_usd"]
    )
    return GLOBAL_DAILY_AI_REQUESTS * per_request


def _reasoning_tokens(usage: dict | None) -> int:
    details = (usage or {}).get("completion_tokens_details") or {}
    value = details.get("reasoning_tokens")
    return value if isinstance(value, int) else 0


def report(results_dir: Path, out: TextIO) -> None:
    """Print the results table. Raises ComparisonError while reviews are missing."""
    files = sorted(path for path in results_dir.glob("*.json") if path.name != "run.json")
    if not files:
        raise ComparisonError(f"No result files in {results_dir}.")
    results = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    missing = [field for result in results for field in missing_reviews(result)]
    if missing:
        raise ComparisonError(
            "Reviews missing, fill these in first:\n" + "\n".join(f"- {m}" for m in missing)
        )
    out.write(
        "| Model | Category matches | Tags in input language | Summary in input language "
        "| Valid JSON first try | Summary quality (1-5) | Median suggestion time "
        "| Median summary time | Cost per suggestion | Cost per summary | Max daily cost "
        "|\n|---|---|---|---|---|---|---|---|---|---|---|\n"
    )
    for result in results:
        suggestions, summaries = result["suggestions"], result["summaries"]
        n, m = len(suggestions), len(summaries)
        matches = sum(item["category_matches"] for item in suggestions)
        tags_ok = sum(item["review"]["tags_in_input_language"] for item in suggestions)
        summary_ok = sum(item["review"]["in_input_language"] for item in summaries)
        valid_json = sum(item["valid_json_first_try"] for item in suggestions)
        quality = statistics.mean(item["review"]["quality"] for item in summaries)
        out.write(
            f"| {result['model']} | {matches}/{n} | {tags_ok}/{n} | {summary_ok}/{m} "
            f"| {valid_json}/{n} | {quality:.1f} "
            f"| {_median_seconds(suggestions)} | {_median_seconds(summaries)} "
            f"| {_mean_cost(suggestions)} | {_mean_cost(summaries)} "
            f"| ${max_daily_cost(result):.2f} |\n"
        )
    out.write(
        f"\nDate of the run: {results[0]['date']}. Times are medians over all calls of the "
        "operation; costs are means over the calls that reported usage.\n"
    )


def _median_seconds(items: list[dict]) -> str:
    return f"{statistics.median(item['seconds'] for item in items):.1f} s"


def _mean_cost(items: list[dict]) -> str:
    costs = [item["cost_usd"] for item in items if item["cost_usd"] is not None]
    return f"${statistics.mean(costs):.5f}" if costs else "unknown"


# --- Command line -------------------------------------------------------------------------


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: dict[str, str] | None = None,
    transport: httpx2.BaseTransport | None = None,
    out: TextIO = sys.stdout,
) -> int:
    """The command line. `transport` lets the offline tests answer every HTTP request."""
    environ = dict(os.environ) if environ is None else environ
    parser = argparse.ArgumentParser(
        prog="python -m scripts.model_comparison",
        description="Compare candidate LLMs for Winlog's default model (issue #14).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check_command = commands.add_parser("check", help="free: list ZDR endpoints and prices")
    check_command.add_argument("models", nargs="+", metavar="MODEL")
    run_command = commands.add_parser("run", help="paid: run the comparison")
    run_command.add_argument("models", nargs="+", metavar="MODEL")
    run_command.add_argument(
        "--confirm-paid-calls",
        action="store_true",
        help="required: confirms that this run makes real, paid AI calls",
    )
    run_command.add_argument("--out", type=Path, help="results folder (default: results/DATE)")
    report_command = commands.add_parser("report", help="print the results table")
    report_command.add_argument("results_dir", type=Path)
    args = parser.parse_args(argv)

    base_url = environ.get(BASE_URL_VARIABLE) or DEFAULT_BASE_URL
    try:
        if args.command == "report":
            report(args.results_dir, out)
            return 0
        test_set = load_test_set()
        if args.command == "check":
            with httpx2.Client(transport=transport) as client:
                check(args.models, client, base_url, test_set, out)
            return 0
        if not args.confirm_paid_calls:
            raise ComparisonError("run makes real, paid AI calls: add --confirm-paid-calls.")
        api_key = (environ.get(API_KEY_VARIABLE) or "").strip()
        if not api_key:
            raise ComparisonError(f"{API_KEY_VARIABLE} is not set in the environment.")
        today = dt.datetime.now(dt.UTC).date()
        with httpx2.Client(transport=transport) as client:
            run(
                args.models,
                api_key=api_key,
                base_url=base_url,
                out_dir=args.out or RESULTS_PATH / today.isoformat(),
                test_set=test_set,
                catalogue_client=client,
                transport=transport,
                today=today,
                out=out,
            )
        return 0
    except ComparisonError as error:
        out.write(f"Error: {error}\n")
        return 1
