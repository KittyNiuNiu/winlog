"""SQLAlchemy models for the tables in docs/product-spec.md §10.5.

The schema itself is created by the Alembic migrations in backend/migrations/.
`uv run alembic check` verifies that these models and the migrations match.
"""

import datetime as dt
import uuid

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    Uuid,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# The four categories, exactly as in openapi.yaml (components.schemas.Category).
CATEGORIES = ("Achievement", "Learning", "Feedback", "Side project")

# Unique index on (user_id, lower(name)): tag names are unique per user, ignoring case.
TAG_NAME_UNIQUE_INDEX = "uq_tags_user_id_lower_name"

# Kinds of AI request counted per user and day.
AI_REQUEST_TYPES = ("suggestion", "summary")

# Kinds of attempt counted in login_attempts (FR-A4): failed logins per email, and
# demo-logins per visitor IP address.
ATTEMPT_KINDS = ("login", "demo")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


class Base(DeclarativeBase):
    # Predictable constraint names, so later migrations can refer to them.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=func.gen_random_uuid())


def _created_at() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated_at() -> Mapped[dt.datetime]:
    # A database trigger (see the migration) sets this on every update.
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )


def _owner() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = _created_at()


class Token(Base):
    """A login (issue #7). Only the SHA-256 hash of the token is stored, never the token."""

    __tablename__ = "tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = _created_at()
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint(f"category IN ({_sql_list(CATEGORIES)})", name="category"),
        # Listing and filtering always select one user's entries by date (issue #11).
        Index(None, "user_id", "date"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    result_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _created_at()
    updated_at: Mapped[dt.datetime] = _updated_at()


class Tag(Base):
    """A user's tag. Names are unique per user, ignoring case (issue #8, see app/tags.py)."""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    name: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        # Lookups compare lower(name) in the same way, so they can use this index.
        Index(TAG_NAME_UNIQUE_INDEX, "user_id", func.lower(name), unique=True),
    )


class EntryTag(Base):
    __tablename__ = "entry_tags"

    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (CheckConstraint("period_start <= period_end", name="period_order"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    period_start: Mapped[dt.date] = mapped_column(Date, nullable=False)
    period_end: Mapped[dt.date] = mapped_column(Date, nullable=False)
    # Stored as values (tag names, not ids), so a summary keeps its filter as it was.
    filter_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    filter_tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=sql_text("'{}'")
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = _created_at()
    updated_at: Mapped[dt.datetime] = _updated_at()


class AiUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        CheckConstraint(f"request_type IN ({_sql_list(AI_REQUEST_TYPES)})", name="request_type"),
        CheckConstraint("request_count >= 0", name="request_count"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    request_type: Mapped[str] = mapped_column(Text, primary_key=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class AiUsageGlobal(Base):
    """The day's AI requests across all users: the global cap (issue #15, §8).

    One row per UTC day. It has no user id and no other personal data, so deleting an
    account does not lower the day's count.
    """

    __tablename__ = "ai_usage_global"
    __table_args__ = (CheckConstraint("request_count >= 0", name="request_count"),)

    day: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class LoginAttempt(Base):
    """Login and demo-login attempts in the current window (FR-A4, issue #46).

    One row per kind and key: `login` counts failed logins per email, `demo` counts
    demo-logins per visitor IP address. The key is stored only as its SHA-256 hash, so the
    table holds no readable email or IP. Rows whose window has ended are deleted whenever
    new attempts are written (app/attempt_limits.py).
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_sql_list(ATTEMPT_KINDS)})", name="kind"),
        CheckConstraint("attempt_count >= 0", name="attempt_count"),
        # The cleanup selects rows by the start of their window.
        Index(None, "window_start"),
    )

    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    key_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
