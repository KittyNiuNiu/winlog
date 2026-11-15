"""How many values a filter holds, without a database (issue #88, product-spec.md §7.4).

Covers FR-R1 (`GET /entries`), FR-R3 (`POST /summaries`) and FR-R4 (saved filters). A filter
holds at most 20 tag names and 4 categories, counted as sent. Matching, saving and summaries
saved before the limits are tested against PostgreSQL in tests/integration/test_filter_limits.py.
"""

import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ai import get_limited_ai
from app.auth import get_current_user
from app.entries import MAX_FILTER_CATEGORIES
from app.main import create_app
from app.models import CATEGORIES, User
from app.summaries import SavedSummaryFilter, SummaryFilter
from app.tags import MAX_FILTER_TAG_NAMES, MAX_TAG_NAME_CHARACTERS
from tests.conftest import OPENAPI_PATH

OPENAPI = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
SCHEMAS = OPENAPI["components"]["schemas"]
JANUARY = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
EMOJI = "🎉"
# 21 values that the backend would clean into fewer, or into none: each one still counts.
TWENTY_ONE = {
    "one_name_repeated": ["Go"] * 21,
    "names_that_differ_only_in_case": ["go", "Go", "GO", "gO"] * 5 + ["go"],
    "empty_or_only_spaces": ["", " ", "   "] * 7,
    "names_nobody_has": [f"nobody-{number}" for number in range(21)],
}


def _list_parameter(name: str) -> dict:
    [parameter] = [
        p for p in OPENAPI["paths"]["/entries"]["get"]["parameters"] if p["name"] == name
    ]
    return parameter


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


def _validation_errors(response) -> list[tuple[str, str]]:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "validation_failed"
    return [(item["field"], item["reason"]) for item in body["fields"]]


def _model_errors(payload: dict) -> list[tuple[str, str]]:
    with pytest.raises(ValidationError) as error:
        SummaryFilter.model_validate(payload)
    return [
        (".".join(str(part) for part in item["loc"]), item["type"]) for item in error.value.errors()
    ]


# --- The limits match the contract --------------------------------------------------------


def test_fr_r1_filter_counts_match_the_contract():
    assert _list_parameter("tag")["schema"]["maxItems"] == MAX_FILTER_TAG_NAMES == 20
    assert _list_parameter("category")["schema"]["maxItems"] == MAX_FILTER_CATEGORIES == 4
    # 4 is the number of categories (product-spec.md §6).
    assert len(CATEGORIES) == MAX_FILTER_CATEGORIES
    # Each name keeps its 40 characters (#43).
    assert _list_parameter("tag")["schema"]["items"]["maxLength"] == MAX_TAG_NAME_CHARACTERS


def test_fr_r3_summary_filter_counts_match_the_contract():
    properties = SCHEMAS["SummaryFilter"]["properties"]
    assert properties["tags"]["maxItems"] == MAX_FILTER_TAG_NAMES
    assert properties["categories"]["maxItems"] == MAX_FILTER_CATEGORIES
    assert properties["tags"]["items"]["maxLength"] == MAX_TAG_NAME_CHARACTERS


def test_fr_r1_filter_count_descriptions_state_the_maximum():
    assert "At most 20 names" in _list_parameter("tag")["description"]
    assert "At most 4 values" in _list_parameter("category")["description"]
    properties = SCHEMAS["SummaryFilter"]["properties"]
    assert "At most 20 names" in properties["tags"]["description"]
    assert "At most 4 values" in properties["categories"]["description"]
    limits = " ".join(OPENAPI["info"]["description"].split())
    assert "at most 20 tag names and at most 4 categories" in limits
    assert (
        "counted as sent, so duplicates, names that differ only in case and names that are "
        "empty after trimming all count" in limits
    )


def test_fr_r4_saved_summary_filter_is_summary_filter_without_the_limits():
    saved = SCHEMAS["SavedSummaryFilter"]
    request = SCHEMAS["SummaryFilter"]

    assert saved["required"] == request["required"] == ["period_start", "period_end"]
    assert set(saved["properties"]) == set(request["properties"])
    for name, schema in saved["properties"].items():
        assert schema["description"] == request["properties"][name]["description"]
    text = yaml.safe_dump(saved)
    assert "maxLength" not in text and "maxItems" not in text
    description = " ".join(saved["description"].split())
    assert "saved before these limits existed can have longer tag names or more tag names" in (
        description
    )


def test_fr_r4_summaries_return_the_saved_filter_and_generation_takes_the_request_filter():
    assert SCHEMAS["Summary"]["properties"]["filter"] == {
        "$ref": "#/components/schemas/SavedSummaryFilter"
    }
    request = OPENAPI["paths"]["/summaries"]["post"]["requestBody"]["content"]["application/json"]
    assert request["schema"] == {"$ref": "#/components/schemas/SummaryFilter"}
    limits = " ".join(OPENAPI["info"]["description"].split())
    assert "`SavedSummaryFilter`" in limits
    assert "more tag names than a filter may hold now" in limits


# --- The request model of POST /summaries (FR-R3) ----------------------------------------


def test_fr_r3_summary_filter_with_20_tags_and_4_categories_is_valid():
    tags = [f"tag-{number}" for number in range(20)]

    summary_filter = SummaryFilter.model_validate(
        {**JANUARY, "tags": tags, "categories": list(CATEGORIES)}
    )

    assert summary_filter.tags == tags
    assert summary_filter.categories == list(CATEGORIES)


@pytest.mark.parametrize("tags", TWENTY_ONE.values(), ids=TWENTY_ONE.keys())
def test_fr_r3_summary_filter_with_21_tags_is_invalid_however_they_are_written(tags):
    assert _model_errors({**JANUARY, "tags": tags}) == [("tags", "too_many_tags")]


@pytest.mark.parametrize("tags", TWENTY_ONE.values(), ids=TWENTY_ONE.keys())
def test_fr_r3_summary_filter_with_20_such_tags_is_valid(tags):
    assert SummaryFilter.model_validate({**JANUARY, "tags": tags[:20]}).tags == tags[:20]


def test_fr_r3_summary_filter_with_5_categories_is_invalid_even_when_one_repeats():
    categories = [*CATEGORIES, "Learning"]

    assert _model_errors({**JANUARY, "categories": categories}) == [
        ("categories", "too_many_categories")
    ]
    # Repeated values within the count are still accepted, as before.
    assert SummaryFilter.model_validate({**JANUARY, "categories": ["Learning"] * 4})


def test_fr_r3_summary_filter_tags_of_40_characters_are_valid_and_41_names_the_value():
    tags = [EMOJI * 40] * 19 + ["t" * 40]
    assert SummaryFilter.model_validate({**JANUARY, "tags": tags}).tags == tags

    assert _model_errors({**JANUARY, "tags": ["Go", "t" * 41]}) == [("tags.1", "too_long")]


# --- Through the endpoints ---------------------------------------------------------------


def test_fr_r1_list_with_21_tags_is_a_validation_error_naming_tag(logged_in_client, contract):
    tags = [f"tag-{number}" for number in range(21)]

    response = logged_in_client.get("/entries", params={"tag": tags})

    contract("Error").validate(response.json())
    assert _validation_errors(response) == [("tag", "A filter can have at most 20 tag names.")]


@pytest.mark.parametrize("tags", TWENTY_ONE.values(), ids=TWENTY_ONE.keys())
def test_fr_r1_list_counts_tags_as_sent(logged_in_client, tags):
    response = logged_in_client.get("/entries", params={"tag": tags})

    assert [field for field, _ in _validation_errors(response)] == ["tag"]


def test_fr_r1_list_with_5_categories_is_a_validation_error_naming_category(
    logged_in_client, contract
):
    response = logged_in_client.get("/entries", params={"category": [*CATEGORIES, "Feedback"]})

    contract("Error").validate(response.json())
    assert _validation_errors(response) == [("category", "A filter can have at most 4 categories.")]


def test_fr_r1_list_names_both_fields_when_both_have_too_many(logged_in_client):
    response = logged_in_client.get(
        "/entries", params={"category": ["Learning"] * 5, "tag": ["Go"] * 21}
    )

    assert [field for field, _ in _validation_errors(response)] == ["category", "tag"]


def test_fr_r1_list_tag_over_40_characters_still_names_the_value(logged_in_client):
    response = logged_in_client.get("/entries", params={"tag": ["t" * 40] * 19 + ["t" * 41]})

    assert [field for field, _ in _validation_errors(response)] == ["tag.19"]


def test_fr_r3_summary_with_21_tags_is_rejected_without_an_ai_call(logged_in_client, contract):
    # NoAI fails the test if the AI is called.
    response = logged_in_client.post(
        "/summaries", json={**JANUARY, "tags": [f"t{number}" for number in range(21)]}
    )

    contract("Error").validate(response.json())
    assert _validation_errors(response) == [("tags", "A filter can have at most 20 tag names.")]


def test_fr_r3_summary_with_5_categories_is_rejected_without_an_ai_call(logged_in_client):
    response = logged_in_client.post(
        "/summaries", json={**JANUARY, "categories": [*CATEGORIES, "Achievement"]}
    )

    assert _validation_errors(response) == [
        ("categories", "A filter can have at most 4 categories.")
    ]


def test_fr_r3_summary_tag_over_40_characters_still_names_the_value(logged_in_client):
    response = logged_in_client.post(
        "/summaries", json={**JANUARY, "tags": ["t" * 40] * 19 + ["t" * 41]}
    )

    assert [field for field, _ in _validation_errors(response)] == ["tags.19"]


# --- Saved filters (FR-R4) ---------------------------------------------------------------


def test_fr_r4_saved_filter_model_has_no_limits():
    tags = [f"tag-{number}" for number in range(24)] + ["L" * 50]

    saved = SavedSummaryFilter.model_validate({**JANUARY, "tags": tags})

    assert saved.tags == tags
