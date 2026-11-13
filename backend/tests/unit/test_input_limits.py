"""Maximum input sizes without a database (issue #43, product-spec.md §6, §7.2 and §7.4).

Covers FR-E2 (entry limits), FR-S1 (suggestion text), FR-R1 (filter tag names), FR-R3 (the
summary input limit) and FR-R5 (edited summary text). Each limit is checked just at and one
over its value, with emoji-only values, because lengths are Unicode characters (code points).
Saving, legacy data and the summary input limit end to end are tested against PostgreSQL in
tests/integration/test_input_limits.py.
"""

import datetime as dt
import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from app.ai import SummaryEntry, get_limited_ai
from app.ai.adapter import MAX_SUMMARY_CHARACTERS
from app.auth import get_current_user
from app.demo_seed import SAMPLE_ENTRIES, SAMPLE_SUMMARIES
from app.entries import (
    MAX_ENTRY_TEXT_CHARACTERS,
    MAX_RESULT_IMPACT_CHARACTERS,
    MAX_TAGS_PER_ENTRY,
    EntryInput,
)
from app.main import create_app
from app.models import User
from app.settings import Settings, SettingsError, load_settings
from app.suggestions import SuggestionRequest
from app.summaries import SummaryFilter, SummaryUpdate, summary_input_characters
from app.tags import MAX_TAG_NAME_CHARACTERS, FilterTagName, TagName
from tests.conftest import OPENAPI_PATH

OPENAPI = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
SCHEMAS = OPENAPI["components"]["schemas"]
ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"
VARIABLE = "AI_SUMMARY_MAX_INPUT_CHARACTERS"
VALID = {"text": "Shipped it.", "date": "2026-11-08", "category": "Achievement"}
JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
ENTRY_ID = "123e4567-e89b-12d3-a456-426614174000"
# One character (one code point) that is two UTF-16 units and four UTF-8 bytes.
EMOJI = "🎉"
# A marker that must never appear in an error response.
SECRET = "Secretword"


def _fields(model: type, payload: dict) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        model.model_validate(payload)
    return [
        (".".join(str(part) for part in item["loc"]), item["type"]) for item in error.value.errors()
    ]


class NoAI:
    """Stands in for the limited AI entry point and fails the test if it is ever called."""

    def suggest(self, *args: object) -> None:
        raise AssertionError("no AI call may be made")

    def summarise(self, *args: object) -> None:
        raise AssertionError("no AI call may be made")


@pytest.fixture
def logged_in_client(settings) -> TestClient:
    """The real routes with a stand-in user. Validation fails before any database use."""
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: User(id=uuid.uuid4(), email="a@b.c")
    app.dependency_overrides[get_limited_ai] = NoAI
    return TestClient(app)


def _validation_fields(response) -> list[str]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "validation_failed"
    assert SECRET not in response.text
    return [item["field"] for item in body["fields"]]


# --- The limits match the contract --------------------------------------------------------


def test_fr_e2_limits_match_the_contract():
    entry = SCHEMAS["EntryInput"]["properties"]
    assert entry["text"]["maxLength"] == MAX_ENTRY_TEXT_CHARACTERS == 2_000
    assert entry["result_impact"]["maxLength"] == MAX_RESULT_IMPACT_CHARACTERS == 500
    assert entry["tags"]["maxItems"] == MAX_TAGS_PER_ENTRY == 10
    assert entry["tags"]["items"]["maxLength"] == MAX_TAG_NAME_CHARACTERS == 40
    assert entry["tags"]["items"]["minLength"] == 1


def test_fr_s1_suggestion_limits_match_the_contract():
    assert SCHEMAS["SuggestionRequest"]["properties"]["text"]["maxLength"] == 2_000
    assert SCHEMAS["Suggestion"]["properties"]["tags"]["items"]["maxLength"] == 40


def test_fr_r5_summary_text_limit_matches_the_contract():
    assert SCHEMAS["SummaryUpdate"]["properties"]["text"]["maxLength"] == MAX_SUMMARY_CHARACTERS
    assert MAX_SUMMARY_CHARACTERS == 10_000


def test_fr_r1_filter_tag_limits_match_the_contract():
    [tag] = [p for p in OPENAPI["paths"]["/entries"]["get"]["parameters"] if p["name"] == "tag"]
    assert tag["schema"]["items"]["maxLength"] == 40
    assert SCHEMAS["SummaryFilter"]["properties"]["tags"]["items"]["maxLength"] == 40


def test_fr_r3_summary_input_too_large_is_a_contract_error_code():
    assert "summary_input_too_large" in SCHEMAS["Error"]["properties"]["code"]["enum"]
    examples = OPENAPI["paths"]["/summaries"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["examples"]
    assert examples["summaryInputTooLarge"]["$ref"].endswith("/SummaryInputTooLarge")


def test_fr_e2_response_schemas_set_no_maximum_length():
    """Data saved before the limits existed can be longer (#43)."""
    for name in ("Entry", "Summary"):
        assert "maxLength" not in yaml.safe_dump(SCHEMAS[name])


def test_fr_e2_contract_counts_characters_as_the_backend_does(contract):
    """jsonschema counts code points, as Python's len does: an emoji is one character."""
    at_limit = {**VALID, "text": EMOJI * 2_000, "tags": [EMOJI * 40] * 10}
    contract("EntryInput").validate(at_limit)
    assert EntryInput.model_validate(at_limit).text == EMOJI * 2_000
    over = {**VALID, "text": EMOJI * 2_001}
    assert not contract("EntryInput").is_valid(over)
    assert _fields(EntryInput, over) == [("text", "too_long")]


# --- Entry text, Result/Impact and tags ---------------------------------------------------


@pytest.mark.parametrize("char", ["a", EMOJI, "\n"])
def test_fr_e2_entry_text_of_2000_characters_is_accepted(char: str):
    text = "x" + char * 1_999
    assert EntryInput.model_validate({**VALID, "text": text}).text == text


@pytest.mark.parametrize("char", ["a", EMOJI])
def test_fr_e2_entry_text_over_2000_characters_is_rejected(char: str):
    assert _fields(EntryInput, {**VALID, "text": char * 2_001}) == [("text", "too_long")]


def test_fr_e2_emoji_only_entry_text_at_the_limit_is_accepted():
    """2,000 emoji are 4,000 UTF-16 units and 8,000 bytes, but 2,000 characters."""
    assert EntryInput.model_validate({**VALID, "text": EMOJI * 2_000}).text == EMOJI * 2_000


def test_fr_e2_result_impact_of_500_characters_is_accepted():
    value = EMOJI * 500
    assert EntryInput.model_validate({**VALID, "result_impact": value}).result_impact == value


@pytest.mark.parametrize("value", ["r" * 501, EMOJI * 501])
def test_fr_e2_result_impact_over_500_characters_is_rejected(value: str):
    assert _fields(EntryInput, {**VALID, "result_impact": value}) == [("result_impact", "too_long")]


def test_fr_e2_result_impact_over_500_characters_is_rejected_even_when_only_whitespace():
    assert _fields(EntryInput, {**VALID, "result_impact": " " * 501}) == [
        ("result_impact", "too_long")
    ]
    # Exactly at the limit, whitespace is still stored as no result (#9).
    assert EntryInput.model_validate({**VALID, "result_impact": " " * 500}).result_impact is None


def test_fr_e2_ten_tags_are_accepted():
    tags = [f"Tag {number}" for number in range(10)]
    assert EntryInput.model_validate({**VALID, "tags": tags}).tags == tags


def test_fr_e2_more_than_10_tags_are_rejected():
    tags = [f"Tag {number}" for number in range(11)]
    assert _fields(EntryInput, {**VALID, "tags": tags}) == [("tags", "too_many_tags")]


def test_fr_e2_tags_are_counted_as_sent_even_when_they_match_each_other():
    """`maxItems: 10` counts the names as sent, before names that match become one tag."""
    assert _fields(EntryInput, {**VALID, "tags": ["Go"] * 11}) == [("tags", "too_many_tags")]


@pytest.mark.parametrize("name", ["t" * 40, EMOJI * 40, "a" + " " * 38 + "b"])
def test_fr_e2_tag_name_of_40_characters_is_accepted(name: str):
    assert TypeAdapter(TagName).validate_python(name) == " ".join(name.split())


@pytest.mark.parametrize("name", ["t" * 41, EMOJI * 41, "t" * 9_000])
def test_fr_e2_tag_name_over_40_characters_is_rejected(name: str):
    assert _fields(EntryInput, {**VALID, "tags": ["Go", name]}) == [("tags.1", "too_long")]


def test_fr_e2_tag_name_length_is_measured_as_sent_not_after_cleaning():
    """Cleaning would make it 39 characters, but 43 were sent (the contract is exact)."""
    name = "  " + "t" * 39 + "  "
    assert _fields(EntryInput, {**VALID, "tags": [name]}) == [("tags.0", "too_long")]


def test_fr_e2_every_field_over_its_limit_is_named(logged_in_client: TestClient, contract):
    response = logged_in_client.post(
        "/entries",
        json={
            **VALID,
            "text": SECRET * 201,
            "result_impact": SECRET * 51,
            "tags": ["Go", SECRET * 5],
        },
    )

    contract("Error").validate(response.json())
    assert _validation_fields(response) == ["text", "tags.1", "result_impact"]


def test_fr_e2_too_many_tags_names_the_tags_field(logged_in_client: TestClient):
    response = logged_in_client.post("/entries", json={**VALID, "tags": list("abcdefghijk")})

    assert _validation_fields(response) == ["tags"]


def test_fr_e2_9000_character_tag_is_a_validation_error_not_a_500(logged_in_client: TestClient):
    """#9's QA got a 500 from the database index; the API boundary now stops it."""
    response = logged_in_client.post("/entries", json={**VALID, "tags": [SECRET * 900]})

    assert _validation_fields(response) == ["tags.0"]


def test_fr_e4_update_checks_the_same_limits(logged_in_client: TestClient, contract):
    response = logged_in_client.put(
        f"/entries/{ENTRY_ID}",
        json={
            **VALID,
            "text": SECRET * 201,
            "result_impact": " " * 501,
            "tags": [f"t{number}" for number in range(11)],
        },
    )

    contract("Error").validate(response.json())
    assert _validation_fields(response) == ["text", "tags", "result_impact"]


# --- Suggestions (FR-S1) ------------------------------------------------------------------


def test_fr_s1_suggestion_text_of_2000_characters_is_accepted():
    assert SuggestionRequest(text=EMOJI * 2_000).text == EMOJI * 2_000


def test_fr_s1_suggestion_text_over_2000_characters_is_rejected_without_an_ai_call(
    logged_in_client: TestClient, contract
):
    # NoAI fails the test if the AI is called.
    response = logged_in_client.post("/suggestions", json={"text": SECRET * 201})

    contract("Error").validate(response.json())
    assert _validation_fields(response) == ["text"]


# --- Summaries (FR-R1, FR-R3, FR-R5) ------------------------------------------------------


def test_fr_r5_summary_text_of_10000_characters_is_accepted():
    """Edited summary text has the summary's own limit, not the entry text's."""
    assert SummaryUpdate(text=EMOJI * 10_000).text == EMOJI * 10_000


@pytest.mark.parametrize("char", ["s", EMOJI])
def test_fr_r5_summary_text_over_10000_characters_is_rejected(char: str):
    assert _fields(SummaryUpdate, {"text": char * 10_001}) == [("text", "too_long")]


def test_fr_r5_summary_update_over_10000_characters_is_a_validation_error(
    logged_in_client: TestClient, contract
):
    response = logged_in_client.patch(f"/summaries/{ENTRY_ID}", json={"text": SECRET * 1_001})

    contract("Error").validate(response.json())
    assert _validation_fields(response) == ["text"]


@pytest.mark.parametrize("name", ["t" * 40, EMOJI * 40, "", "  "])
def test_fr_r1_filter_tag_name_of_up_to_40_characters_is_accepted(name: str):
    assert TypeAdapter(FilterTagName).validate_python(name) == name


@pytest.mark.parametrize("name", ["t" * 41, EMOJI * 41, " " * 41])
def test_fr_r1_filter_tag_name_over_40_characters_is_rejected(name: str):
    with pytest.raises(ValidationError) as error:
        TypeAdapter(FilterTagName).validate_python(name)

    assert [item["type"] for item in error.value.errors()] == ["too_long"]


def test_fr_r1_list_filter_tag_over_40_characters_names_the_parameter(
    logged_in_client: TestClient, contract
):
    response = logged_in_client.get("/entries", params={"tag": ["Go", SECRET * 5]})

    contract("Error").validate(response.json())
    assert _validation_fields(response) == ["tag.1"]


def test_fr_r3_summary_filter_tag_over_40_characters_is_rejected_without_an_ai_call(
    logged_in_client: TestClient, contract
):
    response = logged_in_client.post("/summaries", json={**JANUARY, "tags": [SECRET * 5]})

    contract("Error").validate(response.json())
    assert _validation_fields(response) == ["tags.0"]
    assert SummaryFilter.model_validate({**JANUARY, "tags": ["t" * 40]}).tags == ["t" * 40]


def _summary_entry(text: str, result_impact: str | None, tags: tuple[str, ...]) -> SummaryEntry:
    return SummaryEntry(
        date=dt.date(2026, 1, 5),
        category="Achievement",
        text=text,
        result_impact=result_impact,
        tags=tags,
    )


def test_fr_r3_summary_input_adds_up_text_result_and_tag_names():
    entries = [
        _summary_entry("a" * 100, "b" * 20, ("Go", "Python")),
        _summary_entry(EMOJI * 7, None, ()),
    ]

    # 100 + 20 + 2 + 6, then 7 emoji: each counts as one character.
    assert summary_input_characters(entries) == 135


# --- AI_SUMMARY_MAX_INPUT_CHARACTERS ------------------------------------------------------


@pytest.fixture
def required_env(no_env_file, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://winlog:secret@localhost:5432/winlog")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("AI_PROVIDER", "mock")


def test_fr_r3_summary_input_limit_defaults_to_50000(required_env):
    assert load_settings().ai_summary_max_input_characters == 50_000


@pytest.mark.parametrize("value", ["1", "50000", " 70000 ", "1000000"])
def test_fr_r3_summary_input_limit_comes_from_the_environment(required_env, monkeypatch, value):
    monkeypatch.setenv(VARIABLE, value)

    assert load_settings().ai_summary_max_input_characters == int(value)


@pytest.mark.parametrize(
    "value", ["0", "-1", "1.5", "1.0", "abc", "", " ", "+5", "1_000", "1e2", "٣"]
)
def test_fr_r3_invalid_summary_input_limit_stops_the_backend_naming_the_variable(
    required_env, monkeypatch, value
):
    monkeypatch.setenv(VARIABLE, value)

    with pytest.raises(SettingsError, match=f"{VARIABLE} is invalid: .*whole number of 1"):
        load_settings()
    with pytest.raises(SettingsError, match=f"{VARIABLE} is invalid"):
        create_app()


@pytest.mark.parametrize("value", [0, -1, True, 1.5, None])
def test_fr_r3_summary_input_limit_given_in_code_must_be_a_whole_number_of_1_or_more(value):
    with pytest.raises(ValueError, match="whole number of 1 or more"):
        Settings(
            _env_file=None,
            database_url="postgresql://winlog:secret@localhost:5432/winlog",
            cors_allowed_origins=["http://localhost:5173"],
            ai_provider="mock",
            ai_summary_max_input_characters=value,
        )


def test_fr_r3_summary_input_limit_is_documented_in_env_example():
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    assert f"{VARIABLE}=50000" in lines


# --- Demo data (#21) ----------------------------------------------------------------------


def test_fr_e2_demo_sample_data_fits_every_limit():
    for sample in SAMPLE_ENTRIES:
        assert 1 <= len(sample.text) <= MAX_ENTRY_TEXT_CHARACTERS
        assert len(sample.result_impact or "") <= MAX_RESULT_IMPACT_CHARACTERS
        assert len(sample.tags) <= MAX_TAGS_PER_ENTRY
        assert all(1 <= len(name) <= MAX_TAG_NAME_CHARACTERS for name in sample.tags)
    for summary in SAMPLE_SUMMARIES:
        assert 1 <= len(summary.text) <= MAX_SUMMARY_CHARACTERS
        assert all(len(name) <= MAX_TAG_NAME_CHARACTERS for name in summary.tags)
    # All sample entries together fit one summary request at the default limit.
    together = summary_input_characters(
        [_summary_entry(s.text, s.result_impact, s.tags) for s in SAMPLE_ENTRIES]
    )
    assert together <= 50_000
