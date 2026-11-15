"""Database access: one SQLAlchemy engine per app, using the psycopg (v3) driver.

The engine has two time limits (issues #4 and #95), so a database that stops answering
cannot keep a request waiting:

- Opening a new connection: `DATABASE_CONNECT_TIMEOUT_SECONDS`, libpq's `connect_timeout`.
- Each database call on an open connection: `DATABASE_QUERY_TIMEOUT_SECONDS`. A call is the
  pool's check of a connection before use (pre-ping), a statement with its result, a commit
  or a rollback. Waiting for a free connection in the pool has the same limit.

Neither psycopg nor SQLAlchemy has a public client-side limit for a call, and PostgreSQL's
`statement_timeout` is enforced by the server itself, so it cannot fire when the server is
stuck. The engine therefore opens its connections as `TimeLimitedConnection`, which passes
the limit to psycopg's own wait loop. Time between calls does not count.

Migrations (`migrations/env.py`) build their own engine without these limits, so a deploy or
a wake-up is never cut off halfway through a migration.
"""

import threading
from collections.abc import Iterator
from concurrent.futures import Future
from typing import Any

import psycopg
from fastapi import Request
from psycopg.abc import PQGen
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.settings import Settings

_PLAIN_SCHEMES = ("postgresql://", "postgres://")


def sqlalchemy_url(database_url: str) -> str:
    """Use the psycopg driver for plain PostgreSQL URLs (as Neon and Render provide them)."""
    for scheme in _PLAIN_SCHEMES:
        if database_url.startswith(scheme):
            return "postgresql+psycopg://" + database_url[len(scheme) :]
    return database_url


class DatabaseCallTimeout(psycopg.OperationalError):
    """The database did not answer one call within `DATABASE_QUERY_TIMEOUT_SECONDS`.

    The connection is closed when this is raised. SQLAlchemy therefore treats it as a
    disconnect: it discards the connection, and the request fails with the shared 500 response.
    """


class TimeLimitedConnection(psycopg.Connection):
    """A psycopg connection that waits at most `call_timeout_seconds` for each database call.

    psycopg runs every call on a connection (a statement with its result, a commit, a
    rollback, ...) through `Connection.wait`, whose `timeout` limits the whole call and raises
    `psycopg.errors._WaitTimeout` when it runs out. psycopg never sets that timeout itself for
    these calls; this class sets it to `call_timeout_seconds`. No thread is started.

    A call that runs out stopped halfway, so the connection's state is unknown. It is closed
    (`broken`), which SQLAlchemy's psycopg dialect counts as a disconnect: SQLAlchemy discards
    the connection and never hands it out again. PostgreSQL ends the session once it sees the
    closed socket; a commit that was already sent may still be applied, as with any lost
    connection.

    `_WaitTimeout` and the way psycopg uses `Connection.wait` are not public psycopg API.
    `tests/unit/test_db.py` fails when an upgrade changes them.
    """

    # None: no limit. create_db_engine sets it on every connection it opens.
    call_timeout_seconds: float | None = None

    def wait(
        self, gen: PQGen[Any], interval: float | None = None, timeout: float | None = None
    ) -> Any:
        options = {} if interval is None else {"interval": interval}
        if timeout is not None or self.call_timeout_seconds is None:
            # A limit psycopg sets itself (only `notifies()` does), or no limit at all.
            return super().wait(gen, timeout=timeout, **options)
        try:
            return super().wait(gen, timeout=self.call_timeout_seconds, **options)
        except psycopg.errors._WaitTimeout:
            # Like psycopg's own handling of a query that does not stop after a cancel.
            self.pgconn.finish()
            raise DatabaseCallTimeout(
                "the database did not answer within DATABASE_QUERY_TIMEOUT_SECONDS"
            ) from None


def create_db_engine(settings: Settings) -> Engine:
    call_timeout = settings.database_query_timeout_seconds
    engine = create_engine(
        sqlalchemy_url(settings.database_url.get_secret_value()),
        pool_pre_ping=True,
        # The longest a request waits for a free connection when all are in use.
        pool_timeout=call_timeout,
        # Database errors name the statement but never its values, so entry text, summaries
        # and password hashes cannot reach the server log through a traceback (AGENTS.md).
        hide_parameters=True,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )

    @event.listens_for(engine, "do_connect")
    def _connect_time_limited(
        dialect: Any, connection_record: Any, cargs: list[Any], cparams: dict[str, Any]
    ) -> TimeLimitedConnection:
        # The same call SQLAlchemy makes (`psycopg.connect`), on the subclass.
        connection = TimeLimitedConnection.connect(*cargs, **cparams)
        connection.call_timeout_seconds = call_timeout
        return connection

    return engine


def database_is_reachable(engine: Engine, timeout_seconds: float) -> bool:
    """Run `SELECT 1`, but give up after `timeout_seconds` instead of hanging.

    The health check answers within `DATABASE_CONNECT_TIMEOUT_SECONDS`, which is usually
    shorter than the engine's limit for one call (`DATABASE_QUERY_TIMEOUT_SECONDS`), so that
    Render's health check gets a quick answer. The check therefore runs in its own thread, and
    the caller waits for it at most `timeout_seconds`.

    A check that times out finishes in the background. The engine's own limits end it: the
    pre-ping or the query after at most `DATABASE_QUERY_TIMEOUT_SECONDS`, opening a new
    connection after at most `DATABASE_CONNECT_TIMEOUT_SECONDS`. A connection that was cut off
    is closed and discarded; one that answered goes back to the pool as usual. Either way, no
    connection stays checked out while the database does not answer, and the pool works again
    once the database is back.
    """
    outcome: Future[bool] = Future()

    def check() -> None:
        try:
            outcome.set_result(_select_one(engine))
        except Exception as error:
            outcome.set_exception(error)

    threading.Thread(target=check, name="database-check", daemon=True).start()
    try:
        return outcome.result(timeout=timeout_seconds)
    except TimeoutError:
        return False


def _select_one(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with Session(request.app.state.engine) as session:
        yield session


def violates(error: IntegrityError, constraint: str) -> bool:
    """True if the database rejected the change because of the named constraint."""
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint
