"""The demo account's sample data, and the reset that puts it back (FR-X1, issue #21).

`reset_demo_account` creates the demo user if it is missing and gives it a new random
password. Then it replaces all of the user's entries, tags and summaries with the sample data
below. It only ever reads or changes the demo user's rows, and running it twice gives the
same data. It never calls the AI: the sample summary's text is written here.

The script `scripts/seed_demo` runs it (see AGENTS.md). Running it on every backend start is
issue #38.

Dates are given as days before the run, so the data always looks recent: the entries spread
over the 6 months before the run, and the newest is dated 2 days before it.
"""

import datetime as dt
import secrets
import string
import uuid
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Entry, EntryTag, Summary, Tag, User
from app.passwords import DIGITS, hash_password, password_problems

# Random characters after the three that the password rule needs (#6): 256 bits from
# `secrets`, so nobody can guess it. 3 + 43 characters is far below the 128-character limit.
_RANDOM_BYTES = 32
_UPPERCASE = string.ascii_uppercase
_SPECIAL = "!#-_."


def random_password() -> str:
    """A new random password that meets #6's password rule.

    It has an uppercase letter, a digit and a special character in random places, plus
    random URL-safe characters. It is only ever hashed: never stored, logged or shown.
    """
    chars = [
        secrets.choice(_UPPERCASE),
        secrets.choice(DIGITS),
        secrets.choice(_SPECIAL),
        *secrets.token_urlsafe(_RANDOM_BYTES),
    ]
    secrets.SystemRandom().shuffle(chars)
    password = "".join(chars)
    if password_problems(password):  # cannot happen; checked so a change cannot break it
        raise RuntimeError("The random demo password does not meet the password rule.")
    return password


@dataclass(frozen=True)
class SampleEntry:
    days_ago: int
    category: str
    text: str
    tags: tuple[str, ...] = ()
    result_impact: str | None = None
    # The language the entry is written in (ISO 639-1), so a test can check §9's mix.
    language: str = "en"


@dataclass(frozen=True)
class SampleSummary:
    # The period, as days before the run. Both days are included, as in a summary filter.
    start_days_ago: int
    end_days_ago: int
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    text: str


SAMPLE_ENTRIES: tuple[SampleEntry, ...] = (
    SampleEntry(
        175,
        "Learning",
        "Finished an online course on PostgreSQL query planning. Practised reading EXPLAIN "
        "ANALYZE output on our own slow queries.",
        ("PostgreSQL", "Performance"),
    ),
    SampleEntry(
        168,
        "Achievement",
        "Cut the nightly report job from 40 minutes to 6 by adding two indexes and batching "
        "the inserts.",
        ("PostgreSQL", "Performance"),
        "The finance team now gets its reports before 8 am instead of after lunch.",
    ),
    SampleEntry(
        160,
        "Feedback",
        "My manager said my design document for the billing migration was the clearest one "
        "this quarter, and asked me to share the template with the team.",
        ("Writing",),
    ),
    SampleEntry(
        152,
        "Side project",
        "Started a small command-line tool that turns my Markdown notes into flash cards.",
        ("Python",),
    ),
    SampleEntry(
        145,
        "Achievement",
        "Led the incident review for the checkout outage and wrote the follow-up plan.",
        ("Incident", "Teamwork"),
        "All five follow-up actions were done within two weeks, and the outage has not "
        "happened again.",
    ),
    SampleEntry(
        138,
        "Learning",
        "Paired with a security engineer on threat modelling for the new login flow. Learned "
        "how to use STRIDE to find gaps early.",
        ("Security",),
    ),
    SampleEntry(
        131,
        "Feedback",
        "A new teammate told me the onboarding guide I wrote saved her about a week of asking "
        "around.",
        ("Mentoring", "Writing"),
    ),
    SampleEntry(
        124,
        "Achievement",
        "Habe den Workshop zu Code-Reviews für das Team in Berlin auf Deutsch gehalten.",
        ("Public speaking", "Mentoring"),
        "Zwölf Teilnehmende, und zwei Teams haben danach eine Review-Checkliste eingeführt.",
        language="de",
    ),
    SampleEntry(
        117,
        "Side project",
        "Published version 0.1 of the flash-card tool and got the first three stars.",
        ("Python",),
    ),
    SampleEntry(
        110,
        "Learning",
        "Read the chapters on replication in 'Designing Data-Intensive Applications' and wrote "
        "a one-page summary for the team wiki.",
        ("Writing",),
    ),
    SampleEntry(
        103,
        "Achievement",
        "Shipped the new invoice export for enterprise customers, two days ahead of plan.",
        ("Release",),
        "Three enterprise customers who had asked for it renewed their contracts.",
    ),
    SampleEntry(
        96,
        "Feedback",
        "In my mid-year review, my lead asked me to speak up earlier when I see risks in a plan.",
        ("Teamwork",),
    ),
    SampleEntry(
        89,
        "Achievement",
        "Mentored an intern through her first production feature, from design to release.",
        ("Mentoring", "Release"),
        "She shipped it on time and is joining the team full time.",
    ),
    SampleEntry(
        82,
        "Learning",
        "Tried property-based testing on the price calculation. It found a rounding edge case "
        "that our unit tests had missed.",
        ("Python", "Testing"),
    ),
    SampleEntry(
        75,
        "Side project",
        "Gave a lightning talk about the flash-card tool at the local Python meetup.",
        ("Public speaking", "Python"),
    ),
    SampleEntry(
        68,
        "Feedback",
        "The support team thanked me for the runbook for failed payments. They can now solve "
        "most cases without paging an engineer.",
        ("Incident", "Writing"),
    ),
    SampleEntry(
        61,
        "Achievement",
        "Raised a risk early in planning: the data migration had no rollback step. We added "
        "one, and it was needed on launch day.",
        ("Teamwork", "Release"),
        "The rollback took 4 minutes and no customer data was lost.",
    ),
    SampleEntry(
        54,
        "Learning",
        "Empecé un curso de español para hablar mejor con el equipo de Madrid.",
        ("Teamwork",),
        language="es",
    ),
    SampleEntry(
        47,
        "Achievement",
        "Changed our CI pipeline to run the tests in parallel.",
        ("Performance", "Testing"),
        "Every pull request now waits 7 minutes for the pipeline instead of 18.",
    ),
    SampleEntry(
        40,
        "Feedback",
        "A customer wrote that the new invoice export saves them a full day of work each month.",
        ("Release",),
    ),
    SampleEntry(
        33,
        "Learning",
        "Attended a workshop on writing incident postmortems. Main lesson: describe the "
        "system, not the people.",
        ("Incident",),
    ),
    SampleEntry(
        26,
        "Achievement",
        "Fixed a security issue: session tokens were written to the access log. Removed them "
        "and added a test so it cannot happen again.",
        ("Security", "Testing"),
        "Closed the finding from the external security audit before its deadline.",
    ),
    SampleEntry(
        19,
        "Side project",
        "Added spaced repetition to the flash-card tool, so cards I know well come back less "
        "often.",
        ("Python",),
    ),
    SampleEntry(
        12,
        "Feedback",
        "My skip-level manager mentioned my incident work at the all-hands as an example of "
        "good ownership.",
        ("Incident",),
    ),
    SampleEntry(
        5,
        "Learning",
        "Joined the product manager in three customer interviews. Learned to ask about the "
        "problem before showing a solution.",
        ("Teamwork",),
    ),
    SampleEntry(
        2,
        "Achievement",
        "Started a weekly 30-minute review clinic where anyone can bring a pull request.",
        ("Mentoring", "Teamwork"),
        "Eight people joined the first session.",
    ),
)

# Written here, so the reset never calls the AI. It summarises the achievements in its
# period: the entries 89, 61, 47, 26 and 2 days before the run.
SAMPLE_SUMMARIES: tuple[SampleSummary, ...] = (
    SampleSummary(
        start_days_ago=90,
        end_days_ago=0,
        categories=("Achievement",),
        tags=(),
        text=(
            "Over the last three months I delivered results in four areas.\n\n"
            "Delivery and reliability: I raised an early risk that the data migration had no "
            "rollback step, and we added one. On launch day the rollback was needed: it took "
            "4 minutes and no customer data was lost.\n\n"
            "Engineering productivity: I changed the CI pipeline to run the tests in "
            "parallel, so every pull request now waits 7 minutes instead of 18.\n\n"
            "Security: I removed session tokens from the access log, added a test so it "
            "cannot happen again, and closed the external audit finding before its "
            "deadline.\n\n"
            "Mentoring: I guided an intern through her first production feature. She shipped "
            "it on time and is joining the team full time. I also started a weekly review "
            "clinic, and eight people joined the first session."
        ),
    ),
)


def sample_tag_names() -> list[str]:
    """Every tag the sample entries use, each once, in the order they first appear."""
    return list(dict.fromkeys(name for entry in SAMPLE_ENTRIES for name in entry.tags))


@dataclass(frozen=True)
class ResetResult:
    user_id: uuid.UUID
    entries: int
    tags: int
    summaries: int


def reset_demo_account(session: Session, email: str, today: dt.date) -> ResetResult:
    """Create the demo user if missing, then replace its entries, tags and summaries.

    `email` is the demo email in lower case (the `DEMO_EMAIL` setting). `today` is the day
    of the run: the sample dates count back from it. The user gets a new random password
    on every run. The user's tokens and AI usage are kept, so visitors stay logged in and the
    reset does not give more AI requests. Runs in the caller's transaction and does not
    commit, so a failure leaves the old data in place.
    """
    password_hash = hash_password(random_password())
    # One statement, so it also works if the user is created at the same moment elsewhere.
    user_id = session.execute(
        insert(User)
        .values(email=email, password_hash=password_hash)
        .on_conflict_do_update(index_elements=[User.email], set_={"password_hash": password_hash})
        .returning(User.id)
    ).scalar_one()

    # Only this user's rows. Entry-tag links go with the entries and tags (foreign keys).
    for model in (Summary, Entry, Tag):
        session.execute(delete(model).where(model.user_id == user_id))

    tags = {name: Tag(user_id=user_id, name=name) for name in sample_tag_names()}
    session.add_all(tags.values())
    entries = [
        Entry(
            user_id=user_id,
            date=today - dt.timedelta(days=sample.days_ago),
            text=sample.text,
            category=sample.category,
            result_impact=sample.result_impact,
        )
        for sample in SAMPLE_ENTRIES
    ]
    session.add_all(entries)
    session.flush()
    session.add_all(
        EntryTag(entry_id=entry.id, tag_id=tags[name].id)
        for entry, sample in zip(entries, SAMPLE_ENTRIES, strict=True)
        for name in sample.tags
    )
    session.add_all(
        Summary(
            user_id=user_id,
            period_start=today - dt.timedelta(days=sample.start_days_ago),
            period_end=today - dt.timedelta(days=sample.end_days_ago),
            filter_categories=list(sample.categories),
            filter_tags=list(sample.tags),
            text=sample.text,
        )
        for sample in SAMPLE_SUMMARIES
    )
    session.flush()
    return ResetResult(
        user_id=user_id,
        entries=len(entries),
        tags=len(tags),
        summaries=len(SAMPLE_SUMMARIES),
    )
