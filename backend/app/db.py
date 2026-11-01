"""Database access: one SQLAlchemy engine per app, using the psycopg (v3) driver."""

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

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
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )


def database_is_reachable(engine: Engine) -> bool:
    """Run a trivial query. Gives up after the connect timeout instead of hanging."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return False
    return True
