"""Database access: one SQLAlchemy engine per app, using the psycopg (v3) driver."""

import threading
from collections.abc import Iterator
from concurrent.futures import Future

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
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


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        sqlalchemy_url(settings.database_url.get_secret_value()),
        pool_pre_ping=True,
        # Database errors name the statement but never its values, so entry text, summaries
        # and password hashes cannot reach the server log through a traceback (AGENTS.md).
        hide_parameters=True,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )


def database_is_reachable(engine: Engine, timeout_seconds: float) -> bool:
    """Run `SELECT 1`, but give up after `timeout_seconds` instead of hanging.

    libpq's `connect_timeout` only limits opening a new connection. A connection already in
    the pool has no time limit: if the database stops answering but keeps the TCP connection
    open (for example a paused container), the pre-ping and the query wait with no limit. Neither
    psycopg nor SQLAlchemy has a client-side query timeout, and the server enforces
    `statement_timeout` itself, so it cannot help when the server is stuck. The check
    therefore runs in its own thread, and the caller waits for it at most `timeout_seconds`.

    A check that times out finishes in the background. Its connection stays checked out until
    the database answers and then goes back to the pool as usual. If the connection broke
    instead, SQLAlchemy discards it. Either way, the pool works again once the database is back.
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
