"""Data export: all of the user's entries and summaries as JSON and as Markdown (issue #19).

Operations `exportJson` and `exportMarkdown` in openapi.yaml. Covers FR-D1 and FR-A3, and the
acceptance criteria in product-spec.md §7.6.

- `collect_export` is the one function that collects the data. Both formats are rendered
  from its result, so they always hold the same entries and summaries (FR-D1).
- Entries come from #11's shared `filter_entries` without any filter, so they are in the
  entry list's order: date, then creation time, newest first. Summaries come from #18's
  `user_summaries`: creation time, newest first. Both are scoped to the user (FR-A3).
- The JSON file (`ExportFile`) has the format version 1, the export time, and the entries and
  summaries with exactly the fields of the `Entry` and `Summary` schemas. It holds no email,
  password hash, token or usage data.
- The Markdown file has a title, the export date, an "Entries" and a "Summaries" section.
  Each entry is a heading with its date and category, then its text, its Result/Impact (if
  it has one) and its tags. Each summary is a heading with its creation date and its filter,
  then its text. Text is written exactly as stored, without escaping. An empty section says
  "None".
- Both are downloads (`Content-Disposition: attachment`) named
  `winlog-export-YYYY-MM-DD.json` or `.md`, with the UTC date of the export. Both declare
  UTF-8, and text in any language is written unchanged (not as `\\u` escapes).
- The export never calls the AI and counts against no AI limit, so it works when the AI is
  unavailable (§8). It only reads the database.

Privacy: nothing here is logged. Entry and summary text never appear in a log.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthenticateFirstRoute, CurrentUser, utc_now
from app.db import get_session
from app.entries import Entry, EntryFilter, filter_entries
from app.summaries import Summary, user_summaries

router = APIRouter(tags=["Export"], route_class=AuthenticateFirstRoute)

FORMAT_VERSION = 1
JSON_MEDIA_TYPE = "application/json; charset=utf-8"
MARKDOWN_MEDIA_TYPE = "text/markdown; charset=utf-8"
NONE = "None"
"""What an empty section, or an entry without tags, shows in the Markdown file."""


class ExportFile(BaseModel):
    """The JSON export file (components.schemas.ExportFile)."""

    format_version: Literal[1]
    exported_at: dt.datetime
    entries: list[Entry]
    summaries: list[Summary]


@dataclass(frozen=True)
class ExportData:
    """Everything an export holds. Both formats are rendered from one of these."""

    exported_at: dt.datetime
    entries: list[Entry]
    summaries: list[Summary]


def collect_export(session: Session, user: models.User, now: dt.datetime) -> ExportData:
    """All of the user's entries and summaries, in the order the app lists them (FR-D1).

    Only the user's own data is read (FR-A3). `now` is the export time, in UTC.
    """
    return ExportData(
        exported_at=now,
        entries=filter_entries(session, user, EntryFilter()),
        summaries=user_summaries(session, user),
    )


def file_name(data: ExportData, extension: str) -> str:
    """`winlog-export-YYYY-MM-DD.<extension>`, with the UTC date of the export."""
    return f"winlog-export-{_utc_date(data.exported_at).isoformat()}.{extension}"


def render_json(data: ExportData) -> str:
    """The JSON file. Non-ASCII text is written as it is, not as `\\u` escapes."""
    return ExportFile(
        format_version=FORMAT_VERSION,
        exported_at=data.exported_at,
        entries=data.entries,
        summaries=data.summaries,
    ).model_dump_json()


def _utc_date(moment: dt.datetime) -> dt.date:
    return moment.astimezone(dt.UTC).date()


def _names(values: list[str], when_empty: str) -> str:
    return ", ".join(values) if values else when_empty


def _entry_block(entry: Entry) -> list[str]:
    block = [f"### {entry.date.isoformat()} · {entry.category}", entry.text]
    if entry.result_impact is not None:
        block.append(f"Result/Impact: {entry.result_impact}")
    block.append(f"Tags: {_names(entry.tags, NONE)}")
    return block


def _summary_block(summary: Summary) -> list[str]:
    summary_filter = summary.filter
    # An empty list of categories or tags means no restriction (SummaryFilter).
    heading = " · ".join(
        [
            _utc_date(summary.created_at).isoformat(),
            f"{summary_filter.period_start.isoformat()} to {summary_filter.period_end.isoformat()}",
            f"Categories: {_names(list(summary_filter.categories), 'all')}",
            f"Tags: {_names(list(summary_filter.tags), 'all')}",
        ]
    )
    return [f"### {heading}", summary.text]


def render_markdown(data: ExportData) -> str:
    """The Markdown file. Entry and summary text is included exactly as written."""
    blocks = ["# Winlog export", f"Exported on {_utc_date(data.exported_at).isoformat()}"]
    blocks.append("## Entries")
    if data.entries:
        for entry in data.entries:
            blocks.extend(_entry_block(entry))
    else:
        blocks.append(NONE)
    blocks.append("## Summaries")
    if data.summaries:
        for summary in data.summaries:
            blocks.extend(_summary_block(summary))
    else:
        blocks.append(NONE)
    return "\n\n".join(blocks) + "\n"


def _download(content: str, media_type: str, name: str) -> Response:
    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


_CONTENT_DISPOSITION = {
    "Content-Disposition": {
        "description": "Marks the response as a file download and names the file (UTC date).",
        "schema": {"type": "string"},
    }
}


@router.get(
    "/export/json",
    operation_id="exportJson",
    summary="Download all entries and summaries as JSON.",
    response_model=ExportFile,
    responses={200: {"description": "The JSON export file.", "headers": _CONTENT_DISPOSITION}},
)
def export_json(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    data = collect_export(session, user, utc_now())
    return _download(render_json(data), JSON_MEDIA_TYPE, file_name(data, "json"))


@router.get(
    "/export/markdown",
    operation_id="exportMarkdown",
    summary="Download all entries and summaries as Markdown.",
    response_class=Response,
    responses={
        200: {
            "description": "The Markdown export file.",
            "headers": _CONTENT_DISPOSITION,
            "content": {"text/markdown": {"schema": {"type": "string"}}},
        }
    },
)
def export_markdown(
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    data = collect_export(session, user, utc_now())
    return _download(render_markdown(data), MARKDOWN_MEDIA_TYPE, file_name(data, "md"))
