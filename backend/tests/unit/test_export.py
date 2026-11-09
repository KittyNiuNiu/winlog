"""The data export without a database (issue #19).

Operations `exportJson` and `exportMarkdown` in openapi.yaml. Covers FR-D1 and FR-A3: the
contract, both file formats rendered from one set of data, file names, no AI dependency and
authentication. Collecting the data, other users and the HTTP downloads are tested against
PostgreSQL in tests/integration/test_export.py.
"""

import datetime as dt
import json
import uuid
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import export
from app.ai import get_ai_provider
from app.ai.limits import get_limited_ai
from app.entries import Entry
from app.export import ExportData, file_name, render_json, render_markdown
from app.main import create_app
from app.summaries import Summary, SummaryFilter

OPENAPI = yaml.safe_load(
    (Path(__file__).resolve().parents[3] / "openapi.yaml").read_text(encoding="utf-8")
)
EXPORTED_AT = dt.datetime(2026, 11, 1, 9, 30, tzinfo=dt.UTC)
CREATED = dt.datetime(2026, 10, 20, 8, 0, tzinfo=dt.UTC)
OPERATIONS = {"/export/json": "exportJson", "/export/markdown": "exportMarkdown"}

# Markdown and HTML syntax, which must reach the file exactly as written.
RAW_TEXT = "# Not a heading\n\n* star _under_ `code` <b>bold</b> \\ [link](x) | a | b |\n  indented"


def _entry(**changes) -> Entry:
    values = {
        "id": uuid.uuid4(),
        "date": dt.date(2026, 10, 15),
        "text": "Gave a talk on testing.",
        "category": "Learning",
        "tags": ["Public speaking", "Testing"],
        "result_impact": "Two teams adopted the approach.",
        "created_at": CREATED,
        "updated_at": CREATED,
    }
    return Entry(**(values | changes))


def _summary(**changes) -> Summary:
    filter_values = {
        "period_start": dt.date(2026, 10, 1),
        "period_end": dt.date(2026, 10, 31),
        "categories": ["Learning", "Achievement"],
        "tags": ["Testing"],
    }
    filter_values |= changes.pop("filter", {})
    values = {
        "id": uuid.uuid4(),
        "text": "October was about testing.",
        "filter": SummaryFilter.model_construct(**filter_values),
        "created_at": CREATED,
        "updated_at": CREATED,
    }
    return Summary(**(values | changes))


def _data(entries=(), summaries=(), exported_at=EXPORTED_AT) -> ExportData:
    return ExportData(exported_at=exported_at, entries=list(entries), summaries=list(summaries))


def _calls(dependant) -> set:
    found = {dependant.call}
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


# --- Contract -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", OPERATIONS)
def test_fr_d1_export_operations_match_the_contract(settings, path: str):
    generated = create_app(settings).openapi()["paths"][path]["get"]
    expected = OPENAPI["paths"][path]["get"]

    assert generated["operationId"] == expected["operationId"] == OPERATIONS[path]
    assert generated["security"] == [{"bearerAuth": []}]
    assert "parameters" not in generated
    response = generated["responses"]["200"]
    assert set(response["content"]) == set(expected["responses"]["200"]["content"])
    assert "Content-Disposition" in response["headers"]


def test_fr_d1_generated_export_file_schema_matches_the_contract(settings):
    generated = create_app(settings).openapi()["components"]["schemas"]["ExportFile"]
    expected = OPENAPI["components"]["schemas"]["ExportFile"]

    assert generated["required"] == expected["required"]
    assert set(generated["properties"]) == set(expected["properties"])
    assert generated["properties"]["format_version"]["const"] == 1


@pytest.mark.parametrize("path", OPERATIONS)
def test_fr_d1_export_never_depends_on_the_ai(path: str):
    """§8: the export works when the AI is unavailable, because it never reaches it."""
    [route] = [route for route in export.router.routes if route.path == path]

    calls = _calls(route.dependant)
    assert get_ai_provider not in calls
    assert get_limited_ai not in calls


# --- Shared data --------------------------------------------------------------------------


def test_fr_d1_both_formats_render_the_same_collected_data():
    entries = [_entry(text="Second entry."), _entry(text="First entry.", result_impact=None)]
    summaries = [_summary(text="Newer summary."), _summary(text="Older summary.")]
    data = _data(entries, summaries)

    exported = json.loads(render_json(data))
    markdown = render_markdown(data)

    assert [entry["text"] for entry in exported["entries"]] == ["Second entry.", "First entry."]
    assert [summary["text"] for summary in exported["summaries"]] == [
        "Newer summary.",
        "Older summary.",
    ]
    # The same order in the Markdown file.
    assert markdown.index("Second entry.") < markdown.index("First entry.")
    assert markdown.index("Newer summary.") < markdown.index("Older summary.")


# --- JSON ---------------------------------------------------------------------------------


def test_fr_d1_json_export_has_version_time_and_both_lists(contract):
    exported = json.loads(render_json(_data([_entry()], [_summary()])))

    contract("ExportFile").validate(exported)
    assert set(exported) == {"format_version", "exported_at", "entries", "summaries"}
    assert exported["format_version"] == 1
    assert dt.datetime.fromisoformat(exported["exported_at"]) == EXPORTED_AT


def test_fr_d1_json_export_contains_every_entry_with_the_entry_schema_fields(contract):
    entries = [
        _entry(),
        _entry(category="Side project", tags=[], result_impact=None, date=dt.date(2026, 9, 1)),
    ]

    exported = json.loads(render_json(_data(entries)))

    assert len(exported["entries"]) == 2
    entry_fields = set(OPENAPI["components"]["schemas"]["Entry"]["properties"])
    for item, entry in zip(exported["entries"], entries, strict=True):
        contract("Entry").validate(item)
        assert set(item) == entry_fields
        assert item == json.loads(entry.model_dump_json())
    assert exported["entries"][0]["tags"] == ["Public speaking", "Testing"]
    assert exported["entries"][0]["result_impact"] == "Two teams adopted the approach."
    assert exported["entries"][1]["result_impact"] is None


def test_fr_d1_json_export_contains_every_summary_with_its_filter(contract):
    summaries = [_summary(), _summary(filter={"categories": [], "tags": []})]

    exported = json.loads(render_json(_data(summaries=summaries)))

    summary_fields = set(OPENAPI["components"]["schemas"]["Summary"]["properties"])
    assert len(exported["summaries"]) == 2
    for item in exported["summaries"]:
        contract("Summary").validate(item)
        assert set(item) == summary_fields
    assert exported["summaries"][0]["filter"] == {
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "categories": ["Learning", "Achievement"],
        "tags": ["Testing"],
    }
    assert exported["summaries"][1]["filter"]["categories"] == []


def test_fr_d1_json_export_of_an_empty_account_has_empty_lists(contract):
    exported = json.loads(render_json(_data()))

    contract("ExportFile").validate(exported)
    assert exported["entries"] == []
    assert exported["summaries"] == []


def test_fr_d1_json_export_keeps_non_english_text_unchanged():
    text = "Ärger 日本語 🎉"
    raw = render_json(_data([_entry(text=text, tags=["Größe", "日本"])], [_summary(text=text)]))

    assert text in raw
    assert "Größe" in raw and "日本" in raw
    assert "\\u" not in raw
    assert json.loads(raw)["entries"][0]["text"] == text


def test_fr_d1_json_export_keeps_text_exactly_as_written():
    exported = json.loads(render_json(_data([_entry(text=RAW_TEXT)], [_summary(text=RAW_TEXT)])))

    assert exported["entries"][0]["text"] == RAW_TEXT
    assert exported["summaries"][0]["text"] == RAW_TEXT


# --- Markdown -----------------------------------------------------------------------------


def test_fr_d1_markdown_export_starts_with_title_date_and_both_sections():
    markdown = render_markdown(_data([_entry()], [_summary()]))

    assert markdown.startswith("# Winlog export\n\nExported on 2026-11-01\n\n## Entries\n\n")
    assert markdown.index("## Entries") < markdown.index("## Summaries")


def test_fr_d1_markdown_export_of_an_empty_account_shows_none_in_both_sections():
    markdown = render_markdown(_data())

    # The example of exportMarkdown in openapi.yaml.
    example = OPENAPI["paths"]["/export/markdown"]["get"]["responses"]["200"]["content"]
    assert markdown == example["text/markdown"]["example"]
    assert markdown == (
        "# Winlog export\n\nExported on 2026-11-01\n\n## Entries\n\nNone\n\n## Summaries\n\nNone\n"
    )


def test_fr_d1_markdown_export_contains_every_entry():
    entries = [
        _entry(),
        _entry(
            date=dt.date(2026, 9, 1),
            category="Side project",
            text="Built a bird feeder.",
            tags=[],
            result_impact=None,
        ),
    ]

    markdown = render_markdown(_data(entries))

    assert (
        "### 2026-10-15 · Learning\n\n"
        "Gave a talk on testing.\n\n"
        "Result/Impact: Two teams adopted the approach.\n\n"
        "Tags: Public speaking, Testing\n\n"
    ) in markdown
    # No Result/Impact line for an entry without one; no tags shows "None".
    assert "### 2026-09-01 · Side project\n\nBuilt a bird feeder.\n\nTags: None\n\n" in markdown
    assert markdown.count("Result/Impact:") == 1


def test_fr_d1_markdown_export_contains_every_summary():
    summaries = [
        _summary(),
        _summary(
            text="The first quarter.",
            created_at=dt.datetime(2026, 4, 2, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-5))),
            filter={
                "period_start": dt.date(2026, 1, 1),
                "period_end": dt.date(2026, 3, 31),
                "categories": [],
                "tags": [],
            },
        ),
    ]

    markdown = render_markdown(_data(summaries=summaries))

    assert (
        "## Summaries\n\n"
        "### 2026-10-20 · 2026-10-01 to 2026-10-31 · Categories: Learning, Achievement"
        " · Tags: Testing\n\n"
        "October was about testing.\n\n"
    ) in markdown
    # The creation date is the UTC date; an empty list means no restriction.
    assert (
        "### 2026-04-03 · 2026-01-01 to 2026-03-31 · Categories: all · Tags: all\n\n"
        "The first quarter.\n"
    ) in markdown
    assert "## Entries\n\nNone\n\n## Summaries" in markdown


def test_fr_d1_markdown_export_includes_text_exactly_as_written_without_escaping():
    result = "**Saved** 3 days & <time>"
    markdown = render_markdown(
        _data([_entry(text=RAW_TEXT, result_impact=result)], [_summary(text=RAW_TEXT)])
    )

    assert markdown.count(RAW_TEXT) == 2
    assert f"Result/Impact: {result}" in markdown


def test_fr_d1_markdown_export_keeps_non_english_text_unchanged():
    text = "Ärger 日本語 🎉"
    markdown = render_markdown(
        _data(
            [_entry(text=text, result_impact="Größe ✓", tags=["日本"])],
            [_summary(text=text, filter={"tags": ["Ärger"]})],
        )
    )

    assert markdown.count(text) == 2
    assert "Result/Impact: Größe ✓" in markdown
    assert "Tags: 日本" in markdown
    assert "Tags: Ärger" in markdown


# --- Downloads ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exported_at", "date"),
    [
        (EXPORTED_AT, "2026-11-01"),
        (dt.datetime(2026, 11, 1, 23, 59, 59, tzinfo=dt.UTC), "2026-11-01"),
        # 20:00 in New York on 1 November is 2 November in UTC.
        (dt.datetime(2026, 11, 1, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5))), "2026-11-02"),
    ],
)
def test_fr_d1_export_file_names_use_the_utc_date(exported_at: dt.datetime, date: str):
    data = _data(exported_at=exported_at)

    assert file_name(data, "json") == f"winlog-export-{date}.json"
    assert file_name(data, "md") == f"winlog-export-{date}.md"
    assert f"Exported on {date}" in render_markdown(data)


@pytest.mark.parametrize("path", OPERATIONS)
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer"}, {"Authorization": "Basic x"}])
def test_fr_a3_export_without_a_token_is_not_authenticated(
    client: TestClient, contract, path: str, headers: dict
):
    response = client.get(path, headers=headers)

    assert response.status_code == 401
    contract("Error").validate(response.json())
    assert response.json()["code"] == "not_authenticated"
    assert "Content-Disposition" not in response.headers
