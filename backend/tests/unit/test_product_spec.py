"""The spec's "Last updated" date stays in step with its change log (issue #114).

`docs/product-spec.md` shows a "Last updated" date in its header and records every change in
§14 "Change log", newest first. A task that edits the spec adds an entry at the top of §14 and
sets the header date to that entry's date (`AGENTS.md`, "Working rules"). No requirement ID
covers this (it keeps the spec's own record), so the test names describe the behaviour.

Dates are read with a fixed list of English month names, not with the system locale, and
compared as dates. Nothing here depends on today's date.
"""

import re
from datetime import date
from itertools import pairwise
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs" / "product-spec.md"

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
DATE = r"(\d{1,2}) ([A-Z][a-z]+) (\d{4})"
HEADER = re.compile(r"^\*\*Last updated:\*\*(.*)$", re.MULTILINE)
CHANGE_LOG = "## 14. Change log"
# A §14 entry starts a paragraph with a bold version number: `**0.2 …`, `**1.0 …`.
ENTRY_START = re.compile(r"^\*\*\d+\.")
# The two forms the change log uses: `**0.2, updated 15 November 2026.**` and
# `**0.2 (1 November 2026).**`.
ENTRY = re.compile(rf"^\*\*\d+\.\d+(?:, updated {DATE}| \({DATE}\))\.\*\*")


def _parse_date(day: str, month: str, year: str) -> date | None:
    if month not in MONTHS:
        return None
    try:
        return date(int(year), MONTHS.index(month) + 1, int(day))
    except ValueError:
        return None


def _format(value: date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def _header_date(text: str) -> date:
    match = HEADER.search(text)
    if match is None:
        pytest.fail(f"{SPEC.name} has no '**Last updated:** <day> <Month> <year>' line")
    value = match.group(1).strip()
    parts = re.fullmatch(DATE, value)
    parsed = _parse_date(*parts.groups()) if parts else None
    if parsed is None:
        pytest.fail(f"{SPEC.name}: cannot read the 'Last updated' date {value!r}")
    return parsed


def _change_log_dates(text: str) -> list[date]:
    lines = text.splitlines()
    if CHANGE_LOG not in lines:
        pytest.fail(f"{SPEC.name} has no '{CHANGE_LOG}' heading")
    section = []
    for line in lines[lines.index(CHANGE_LOG) + 1 :]:
        if line.startswith("## "):
            break
        section.append(line)

    dates = []
    for line in section:
        if not ENTRY_START.match(line):
            continue
        match = ENTRY.match(line)
        parsed = None
        if match:
            groups = match.groups()
            parsed = _parse_date(*(groups[:3] if groups[0] else groups[3:]))
        if parsed is None:
            pytest.fail(f"{SPEC.name} §14: cannot read the date of the entry {line[:60]!r}")
        dates.append(parsed)
    if not dates:
        pytest.fail(f"{SPEC.name} §14 has no entry")
    return dates


def _spec_record() -> tuple[date, list[date]]:
    """The header date and the §14 entry dates, top to bottom."""
    text = SPEC.read_text(encoding="utf-8")
    return _header_date(text), _change_log_dates(text)


def test_product_spec_header_date_equals_the_newest_change_log_entry():
    header, entries = _spec_record()
    newest = max(entries)

    assert header == newest, (
        f"Last updated is {_format(header)}, the newest §14 entry is {_format(newest)}"
    )


def test_product_spec_change_log_is_newest_first():
    _, entries = _spec_record()

    # Two entries on the same day are allowed.
    for position, (above, below) in enumerate(pairwise(entries), start=1):
        assert below <= above, (
            f"§14 entry {position + 1} ({_format(below)}) is later than "
            f"entry {position} above it ({_format(above)})"
        )
