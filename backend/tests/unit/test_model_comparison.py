"""The default-model comparison script (issue #14).

No test here calls a real AI API or OpenRouter: every HTTP request goes to an httpx mock
transport that answers with stubbed lists and completions and records the requests.
"""

import datetime as dt
import io
import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest

from app.ai.openai_compatible import SUGGEST_PROMPT, SUMMARISE_PROMPT
from scripts.model_comparison import comparison
from scripts.model_comparison.comparison import (
    CATEGORIES,
    ComparisonError,
    availability,
    call_cost,
    is_plain_json_object,
    load_test_set,
    main,
    max_daily_cost,
    missing_reviews,
    report,
)

BASE_URL = "https://openrouter.example.test/api/v1"
API_KEY = "sk-or-v1-Kq9TestOnlyKeyThatMustNeverBeWritten"
GOOD = "vendor/good-model"
NO_ZDR = "vendor/no-zdr-model"
SAFETY_ONLY = "vendor/safety-retention-model"
UNKNOWN = "vendor/unknown-model"
PRICE_IN = 0.000001  # USD per token: $1 per million
PRICE_OUT = 0.000004

MODELS = [
    {
        "id": GOOD,
        "canonical_slug": "vendor/good-model-2026",
        "pricing": {"prompt": "0.0000005", "completion": "0.000002"},
    },
    {"id": NO_ZDR, "canonical_slug": NO_ZDR, "pricing": {"prompt": "0", "completion": "0"}},
    {
        "id": SAFETY_ONLY,
        "canonical_slug": SAFETY_ONLY,
        "pricing": {"prompt": "0", "completion": "0"},
    },
]
ZDR_ENDPOINTS = [
    {
        "model_id": "vendor/good-model-2026",
        "provider_name": "CheapCloud",
        "pricing": {"prompt": "0.0000005", "completion": "0.000002"},
        "supported_parameters": ["response_format"],
        "safety_retention": False,
    },
    {
        "model_id": "vendor/good-model-2026",
        "provider_name": "PricierCloud",
        "pricing": {"prompt": str(PRICE_IN), "completion": str(PRICE_OUT)},
        "supported_parameters": [],
        "safety_retention": False,
    },
    {
        "model_id": "vendor/good-model-2026",
        "provider_name": "FlaggingCloud",
        "pricing": {"prompt": "0.1", "completion": "0.1"},
        "supported_parameters": [],
        "safety_retention": True,
    },
    {
        "model_id": SAFETY_ONLY,
        "provider_name": "FlaggingCloud",
        "pricing": {"prompt": "0", "completion": "0"},
        "supported_parameters": [],
        "safety_retention": True,
    },
]

Answer = Callable[[dict], str]


def plain_suggestion(body: dict) -> str:
    """A suggestion that always picks the category of the first test entry (Achievement)."""
    return json.dumps({"category": "Achievement", "tags": ["Stub tag"]})


class StubOpenRouter:
    """Answers OpenRouter's list endpoints and chat completions; records every request."""

    def __init__(self, suggestion: Answer = plain_suggestion, usage: dict | None = None):
        self.suggestion = suggestion
        self.usage = (
            usage
            if usage is not None
            else {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cost": 0.0002,
            }
        )
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/models"):
            return httpx2.Response(200, json={"data": MODELS})
        if path.endswith("/endpoints/zdr"):
            return httpx2.Response(200, json={"data": ZDR_ENDPOINTS})
        assert path.endswith("/chat/completions"), path
        body = json.loads(request.content)
        is_suggestion = body["messages"][0]["content"] == SUGGEST_PROMPT
        content = self.suggestion(body) if is_suggestion else "Stub summary of the entries."
        return httpx2.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 1_700_000_000,
                "model": body["model"],
                "provider": "CheapCloud",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": self.usage,
            },
        )

    @property
    def completions(self) -> list[dict]:
        return [
            json.loads(request.content)
            for request in self.requests
            if request.url.path.endswith("/chat/completions")
        ]


def run_script(
    stub: StubOpenRouter, out_dir: Path, *args: str, environ: dict[str, str] | None = None
) -> tuple[int, str]:
    out = io.StringIO()
    environ = {"AI_API_KEY": API_KEY, "AI_BASE_URL": BASE_URL} if environ is None else environ
    code = main(
        ["run", *args, "--out", str(out_dir)],
        environ=environ,
        transport=httpx2.MockTransport(stub),
        out=out,
    )
    return code, out.getvalue()


def item_counts() -> tuple[int, int]:
    """The number of suggestion and summary items in the test set."""
    test_set = load_test_set()
    return len(test_set.entries), len(test_set.summary_cases)


# --- The fixed test set ---------------------------------------------------------------------


def test_issue14_test_set_has_ten_english_and_ten_other_language_entries() -> None:
    test_set = load_test_set()
    by_language: dict[str, int] = {}
    for entry in test_set.entries:
        by_language[entry.language] = by_language.get(entry.language, 0) + 1
    assert by_language.get("en", 0) >= 10
    other = [count for language, count in by_language.items() if language != "en"]
    assert other and max(other) >= 10


def test_issue14_test_set_covers_all_four_categories_in_each_language() -> None:
    test_set = load_test_set()
    for language in test_set.languages:
        categories = {e.expected_category for e in test_set.entries if e.language == language}
        assert categories == set(CATEGORIES), language


def test_issue14_test_set_has_summary_cases_for_each_language_and_mixed_input() -> None:
    test_set = load_test_set()
    for case in test_set.summary_cases:
        languages = [test_set.entry(entry_id).language for entry_id in case.entry_ids]
        # The expected language is the one most entries use (product-spec.md §8).
        assert max(set(languages), key=languages.count) == case.expected_language
        assert languages.count(case.expected_language) > len(languages) / 2
    mixed = [
        case
        for case in test_set.summary_cases
        if len({test_set.entry(entry_id).language for entry_id in case.entry_ids}) > 1
    ]
    assert {case.expected_language for case in mixed} == set(test_set.languages)


def test_issue14_test_set_contains_no_personal_data() -> None:
    raw = comparison.TEST_SET_PATH.read_text(encoding="utf-8")
    assert "made up" in json.loads(raw)["description"]
    for entry in load_test_set().entries:
        free_text = " ".join([entry.text, entry.result_impact or "", *entry.tags])
        assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", free_text), f"{entry.id}: email address"
        assert not re.search(r"\+?\d[\d ()/-]{6,}\d", free_text), f"{entry.id}: phone number"
        assert not re.search(r"https?://|www\.", free_text), f"{entry.id}: link"


def test_issue14_test_set_entries_respect_the_entry_limits() -> None:
    # load_test_set checks every limit and raises on the first problem.
    test_set = load_test_set()
    assert all(len(entry.text) <= 2_000 for entry in test_set.entries)


def test_issue14_test_set_check_rejects_an_invalid_category(tmp_path: Path) -> None:
    data = json.loads(comparison.TEST_SET_PATH.read_text(encoding="utf-8"))
    data["entries"][0]["expected_category"] = "Achievements"
    path = tmp_path / "test_set.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ComparisonError, match="category that does not exist"):
        load_test_set(path)


# --- Candidates and zero data retention -----------------------------------------------------


def test_issue14_candidate_without_zdr_endpoint_is_excluded() -> None:
    assert availability(NO_ZDR, MODELS, ZDR_ENDPOINTS).excluded_reason == (
        "no zero-data-retention endpoint"
    )
    assert "safety" in availability(SAFETY_ONLY, MODELS, ZDR_ENDPOINTS).excluded_reason
    assert availability(UNKNOWN, MODELS, ZDR_ENDPOINTS).excluded_reason == (
        "not listed by OpenRouter"
    )


def test_issue14_zdr_endpoints_are_matched_by_permanent_slug_without_safety_retention() -> None:
    found = availability(GOOD, MODELS, ZDR_ENDPOINTS)
    assert found.excluded_reason is None
    assert [e.provider_name for e in found.zdr_endpoints] == ["CheapCloud", "PricierCloud"]
    assert found.max_prices == (PRICE_IN, PRICE_OUT)


def test_issue14_check_lists_prices_and_makes_no_ai_call() -> None:
    stub = StubOpenRouter()
    out = io.StringIO()
    code = main(
        ["check", GOOD, NO_ZDR],
        environ={"AI_BASE_URL": BASE_URL},
        transport=httpx2.MockTransport(stub),
        out=out,
    )
    assert code == 0
    assert stub.completions == []
    text = out.getvalue()
    assert f"| {GOOD} | 2 (CheapCloud, PricierCloud) | 1 of 2 | $1.000 | $4.000 |" in text
    assert f"| {NO_ZDR} |" in text and "no zero-data-retention endpoint" in text
    assert "Estimated cost of one run" in text


# --- Running the comparison -----------------------------------------------------------------


def test_issue14_run_refuses_without_confirmation_or_key(tmp_path: Path) -> None:
    stub = StubOpenRouter()
    out = io.StringIO()
    code = main(
        ["run", GOOD, "--out", str(tmp_path)],
        environ={"AI_API_KEY": API_KEY, "AI_BASE_URL": BASE_URL},
        transport=httpx2.MockTransport(stub),
        out=out,
    )
    assert code == 1 and "--confirm-paid-calls" in out.getvalue()
    code, text = run_script(stub, tmp_path, GOOD, "--confirm-paid-calls", environ={})
    assert code == 1 and "AI_API_KEY is not set" in text
    assert stub.requests == []


def test_issue14_run_uses_the_production_provider_prompts_and_zdr(tmp_path: Path) -> None:
    stub = StubOpenRouter()
    code, _ = run_script(stub, tmp_path, GOOD, "--confirm-paid-calls")
    assert code == 0
    entries, cases = item_counts()
    bodies = stub.completions
    # One call per item, no retries.
    assert len(bodies) == entries + cases
    assert all(body["model"] == GOOD for body in bodies)
    assert all(body["provider"] == {"zdr": True} for body in bodies)
    suggest = [b for b in bodies if b["messages"][0]["content"] == SUGGEST_PROMPT]
    summarise = [b for b in bodies if b["messages"][0]["content"] == SUMMARISE_PROMPT]
    assert len(suggest) == entries and len(summarise) == cases
    assert all(body["response_format"] == {"type": "json_object"} for body in suggest)
    test_set = load_test_set()
    assert [b["messages"][1]["content"] for b in suggest] == [e.text for e in test_set.entries]
    chat_requests = [r for r in stub.requests if r.url.path.endswith("/chat/completions")]
    assert all(r.headers["authorization"] == f"Bearer {API_KEY}" for r in chat_requests)
    assert all(str(r.url).startswith(BASE_URL) for r in stub.requests)


def test_issue14_run_records_results_for_each_candidate(tmp_path: Path) -> None:
    stub = StubOpenRouter()
    code, text = run_script(stub, tmp_path, GOOD, NO_ZDR, "--confirm-paid-calls")
    assert code == 0
    assert "vendor/no-zdr-model: excluded, no zero-data-retention endpoint" in text
    run_info = json.loads((tmp_path / "run.json").read_text())
    assert run_info["excluded"] == [{"model": NO_ZDR, "reason": "no zero-data-retention endpoint"}]
    assert run_info["test_set"] == "scripts/model_comparison/test_set.json"
    assert not (tmp_path / "vendor__no-zdr-model.json").exists()
    result = json.loads((tmp_path / "vendor__good-model.json").read_text())
    assert result["date"] == dt.datetime.now(dt.UTC).date().isoformat()
    entries, cases = item_counts()
    assert len(result["suggestions"]) == entries and len(result["summaries"]) == cases
    first = result["suggestions"][0]
    assert first["category"] == "Achievement" and first["category_matches"] is True
    assert first["tags"] == ["Stub tag"] and first["valid_json_first_try"] is True
    assert first["cost_usd"] == 0.0002 and first["cost_source"] == "OpenRouter usage.cost"
    assert first["review"] == {"tags_in_input_language": None}
    matches = sum(item["category_matches"] for item in result["suggestions"])
    assert matches == sum(e.expected_category == "Achievement" for e in load_test_set().entries)
    summary = result["summaries"][0]
    assert summary["summary"] == "Stub summary of the entries." and summary["error"] is None
    assert summary["review"] == {"in_input_language": None, "quality": None, "notes": ""}
    assert API_KEY not in (tmp_path / "vendor__good-model.json").read_text()
    assert API_KEY not in (tmp_path / "run.json").read_text()


def test_issue14_markdown_fenced_json_does_not_count_as_valid_json(tmp_path: Path) -> None:
    def fenced(body: dict) -> str:
        return '```json\n{"category": "Learning", "tags": ["Stub"]}\n```'

    code, _ = run_script(StubOpenRouter(suggestion=fenced), tmp_path, GOOD, "--confirm-paid-calls")
    assert code == 0
    result = json.loads((tmp_path / "vendor__good-model.json").read_text())
    first = result["suggestions"][0]
    assert first["valid_json_first_try"] is False
    assert first["category"] is None and first["category_matches"] is False
    assert first["error"].startswith("AIProviderError")
    # A failed suggestion has no tags, so they cannot be in the input's language.
    assert first["review"] == {"tags_in_input_language": False}


def test_issue14_valid_json_with_a_wrong_category_still_counts_as_valid_json() -> None:
    assert is_plain_json_object('{"category": "Win", "tags": []}')
    assert not is_plain_json_object('["Achievement"]')
    assert not is_plain_json_object("Achievement")
    assert not is_plain_json_object(None)


def test_issue14_cost_falls_back_to_tokens_times_zdr_price() -> None:
    assert call_cost({"cost": 0.5, "prompt_tokens": 1}, (1.0, 1.0)) == (
        0.5,
        "OpenRouter usage.cost",
    )
    usage = {"prompt_tokens": 1_000, "completion_tokens": 100}
    cost, source = call_cost(usage, (PRICE_IN, PRICE_OUT))
    assert cost == pytest.approx(0.0014) and source == "tokens x ZDR price"
    assert call_cost(None, (PRICE_IN, PRICE_OUT)) == (None, "unknown")


# --- The report -----------------------------------------------------------------------------


def reviewed_result(tmp_path: Path) -> Path:
    run_script(StubOpenRouter(), tmp_path, GOOD, "--confirm-paid-calls")
    path = tmp_path / "vendor__good-model.json"
    result = json.loads(path.read_text())
    for item in result["suggestions"]:
        item["review"]["tags_in_input_language"] = item["language"] == "en"
    for item in result["summaries"]:
        item["review"].update(in_input_language=True, quality=4)
    path.write_text(json.dumps(result))
    return path


def test_issue14_report_refuses_while_reviews_are_missing(tmp_path: Path) -> None:
    run_script(StubOpenRouter(), tmp_path, GOOD, "--confirm-paid-calls")
    result = json.loads((tmp_path / "vendor__good-model.json").read_text())
    entries, cases = item_counts()
    assert len(missing_reviews(result)) == entries + 2 * cases
    with pytest.raises(ComparisonError, match="Reviews missing"):
        report(tmp_path, io.StringIO())


def test_issue14_report_prints_every_required_result(tmp_path: Path) -> None:
    reviewed_result(tmp_path)
    out = io.StringIO()
    assert main(["report", str(tmp_path)], environ={}, out=out) == 0
    text = out.getvalue()
    assert "| Category matches | Tags in input language | Summary in input language " in text
    assert "| Valid JSON first try | Summary quality (1-5) | Median suggestion time " in text
    assert "| Median summary time | Cost per suggestion | Cost per summary | Max daily cost" in text
    test_set = load_test_set()
    entries, cases = item_counts()
    english = sum(entry.language == "en" for entry in test_set.entries)
    achievements = sum(e.expected_category == "Achievement" for e in test_set.entries)
    row = next(line for line in text.splitlines() if line.startswith(f"| {GOOD} |"))
    assert row.startswith(
        f"| {GOOD} | {achievements}/{entries} | {english}/{entries} | {cases}/{cases} "
        f"| {entries}/{entries} | 4.0 |"
    )
    assert "| $0.00020 | $0.00020 |" in row
    assert "Date of the run:" in text


def test_issue14_max_daily_cost_assumes_the_largest_summary_for_every_request() -> None:
    result = {
        "max_zdr_prompt_price_per_token_usd": PRICE_IN,
        "max_zdr_completion_price_per_token_usd": PRICE_OUT,
        "summaries": [
            {"usage": {"completion_tokens_details": {"reasoning_tokens": 500}}},
            {"usage": None},
        ],
    }
    input_tokens = -(-(50_000 + len(SUMMARISE_PROMPT)) // 3)
    output_tokens = -(-10_000 // 3) + 500
    expected = 100 * (input_tokens * PRICE_IN + output_tokens * PRICE_OUT)
    assert max_daily_cost(result) == pytest.approx(expected)


# --- The decision -------------------------------------------------------------------------


def test_issue14_env_example_default_model_is_the_chosen_model() -> None:
    root = Path(__file__).resolve().parents[3]
    note = (root / "docs" / "decisions" / "default-model.md").read_text(encoding="utf-8")
    chosen = re.search(r"^\*\*Chosen model:\*\* `([^`]+)`$", note, re.MULTILINE)
    assert chosen, "the decision note names the chosen model"
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    defaults = re.findall(r"^AI_MODEL=(.*)$", env_example, re.MULTILINE)
    assert defaults == [chosen.group(1)]


def test_issue14_committed_results_cover_the_decision_and_hold_no_secrets() -> None:
    results = comparison.RESULTS_PATH / "2026-11-09"
    run_info = json.loads((results / "run.json").read_text(encoding="utf-8"))
    assert len(run_info["candidates"]) >= 3
    for path in results.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        for secret in ("bearer", "authorization", "sk-or-", "api_key", "placeholder"):
            assert secret not in text, f"{path.name} contains {secret!r}"
    for model in run_info["candidates"]:
        result = json.loads((results / f"{comparison._file_name(model)}.json").read_text())
        assert missing_reviews(result) == []
        assert "engineer agent" in result["review_by"].lower()
