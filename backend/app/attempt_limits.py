"""Login and demo-login attempt limits (FR-A4, issue #46).

Two limits, each counted in a window that starts with the window's first counted attempt:

- `login`: failed logins per email, after the same trimming and lower-casing as login,
  whether or not the account exists. Wrong passwords on account deletion count toward the
  same limit, using the account's email. A successful login clears the count.
- `demo`: demo-logins per visitor IP address. Every demo-login request counts.

When the limit is reached, every attempt for that key is refused with openapi.yaml's 429
`too_many_attempts` error and a `Retry-After` header until the window ends: no password is
checked and no token is created.

Atomic: an attempt takes a slot before anything else runs, in one
`INSERT ... ON CONFLICT DO UPDATE ... WHERE count < limit OR window ended` statement.
PostgreSQL locks the row and checks the condition against its latest version, so parallel
requests cannot get past the limit. The transaction commits before the password is checked,
so no lock is held during the slow argon2 check. A login takes a slot as a failure; a
correct password then clears the email's count, so only failures stay counted.

Privacy: the email or IP is stored only as its SHA-256 hash (`login_attempts.key_hash`),
and nothing here is logged. Rows whose window has ended are deleted whenever new attempts
are written.
"""

import datetime as dt
import hashlib
import ipaddress
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy import BigInteger, Connection, Engine, case, delete, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.errors import ApiError
from app.models import LoginAttempt
from app.settings import Settings

AttemptKind = Literal["login", "demo"]

TOO_MANY_ATTEMPTS_MESSAGE = "Too many attempts. Please try again later."


class TooManyAttemptsError(ApiError):
    """openapi.yaml's 429 `too_many_attempts` error, with the seconds left in `Retry-After`."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            429,
            "too_many_attempts",
            TOO_MANY_ATTEMPTS_MESSAGE,
            headers={"Retry-After": str(retry_after_seconds)},
        )
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class AttemptLimit:
    """At most `max_attempts` counted attempts per key within `window`."""

    max_attempts: int
    window: dt.timedelta


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def hash_key(value: str) -> str:
    """The SHA-256 hash of an email or IP, as stored in `login_attempts.key_hash`."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def visitor_ip(request: Request) -> str:
    """The visitor's IP address, for the demo-login limit.

    The hosting proxy (Render) appends the address it received the request from to
    `X-Forwarded-For`. Anything a client sent in that header stands to the left of it, so
    only the last entry is trusted. Without the header (local development), the address of
    the direct connection is used.
    """
    forwarded = ",".join(request.headers.getlist("x-forwarded-for"))
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    if entries:
        address = entries[-1]
    elif request.client is not None and request.client.host:
        address = request.client.host
    else:
        return "unknown"
    try:
        # One spelling per address, for example for IPv6.
        return str(ipaddress.ip_address(address))
    except ValueError:
        return address


class AttemptLimiter:
    """Counts login and demo-login attempts and refuses them over the limit."""

    def __init__(
        self,
        engine: Engine,
        limits: dict[AttemptKind, AttemptLimit],
        clock: Callable[[], dt.datetime] = utc_now,
    ) -> None:
        self._engine = engine
        self._limits = limits
        self._clock = clock

    @classmethod
    def from_settings(cls, engine: Engine, settings: Settings) -> "AttemptLimiter":
        return cls(
            engine,
            {
                "login": AttemptLimit(
                    settings.login_max_failed_attempts,
                    dt.timedelta(minutes=settings.login_attempt_window_minutes),
                ),
                "demo": AttemptLimit(
                    settings.demo_login_max_attempts,
                    dt.timedelta(minutes=settings.demo_login_window_minutes),
                ),
            },
        )

    def take_login_attempt(self, email: str) -> None:
        """Count a login attempt for the (normalised) email, or raise TooManyAttemptsError.

        It counts as a failure until `clear_login_attempts` is called after a correct password.
        """
        self._take("login", email)

    def clear_login_attempts(self, email: str) -> None:
        """Clear the email's failure count, after a correct password."""
        with self._engine.begin() as connection:
            connection.execute(
                delete(LoginAttempt).where(
                    LoginAttempt.kind == "login", LoginAttempt.key_hash == hash_key(email)
                )
            )

    def take_demo_login(self, ip: str) -> None:
        """Count a demo-login for the visitor IP, or raise TooManyAttemptsError."""
        self._take("demo", ip)

    def _take(self, kind: AttemptKind, key: str) -> None:
        now = self._clock()
        limit = self._limits[kind]
        key_hash = hash_key(key)
        # Raising inside the block rolls back, but a refused attempt has changed nothing.
        with self._engine.begin() as connection:
            self._delete_ended_windows(connection, now)
            if not _count(connection, kind, key_hash, limit, now):
                raise TooManyAttemptsError(_seconds_left(connection, kind, key_hash, limit, now))

    def _delete_ended_windows(self, connection: Connection, now: dt.datetime) -> None:
        """Delete the rows of every kind whose window has ended.

        Rows another transaction holds are skipped, so two cleanups never wait for each other
        and cannot deadlock; a later write deletes them.
        """
        ended = or_(
            *(
                (LoginAttempt.kind == kind) & (LoginAttempt.window_start <= now - limit.window)
                for kind, limit in self._limits.items()
            )
        )
        rows = (
            select(LoginAttempt.kind, LoginAttempt.key_hash)
            .where(ended)
            .with_for_update(skip_locked=True)
        )
        connection.execute(
            delete(LoginAttempt).where(tuple_(LoginAttempt.kind, LoginAttempt.key_hash).in_(rows))
        )


def _count(
    connection: Connection, kind: str, key_hash: str, limit: AttemptLimit, now: dt.datetime
) -> bool:
    """Add one to the key's count if it is below the limit, or start a new window if the old
    one has ended. False if the limit is reached."""
    window_ended = LoginAttempt.window_start <= now - limit.window
    statement = (
        insert(LoginAttempt)
        .values(kind=kind, key_hash=key_hash, window_start=now, attempt_count=1)
        .on_conflict_do_update(
            index_elements=[LoginAttempt.kind, LoginAttempt.key_hash],
            set_={
                "window_start": case((window_ended, now), else_=LoginAttempt.window_start),
                "attempt_count": case((window_ended, 1), else_=LoginAttempt.attempt_count + 1),
            },
            where=or_(
                LoginAttempt.attempt_count < literal(limit.max_attempts, BigInteger), window_ended
            ),
        )
        .returning(LoginAttempt.attempt_count)
    )
    return connection.execute(statement).one_or_none() is not None


def _seconds_left(
    connection: Connection, kind: str, key_hash: str, limit: AttemptLimit, now: dt.datetime
) -> int:
    """Whole seconds until the key's window ends, at least 1.

    The refused INSERT ... ON CONFLICT has locked the row, so it is still there.
    """
    window_start = connection.execute(
        select(LoginAttempt.window_start).where(
            LoginAttempt.kind == kind, LoginAttempt.key_hash == key_hash
        )
    ).scalar_one()
    left = (window_start + limit.window - now).total_seconds()
    return max(1, math.ceil(left))


def get_attempt_limiter(request: Request) -> AttemptLimiter:
    """FastAPI dependency: the app's attempt limiter."""
    return request.app.state.attempt_limiter


AttemptLimiterDependency = Annotated[AttemptLimiter, Depends(get_attempt_limiter)]
