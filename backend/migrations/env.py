"""Alembic environment.

The database URL comes from DATABASE_URL (environment or the repository-root .env), the
same setting the app uses. Tests pass their own URL through `sqlalchemy.url` instead.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db import sqlalchemy_url
from app.models import Base
from app.settings import load_settings

config = context.config

# Tests set configure_logger=False so Alembic does not replace pytest's logging setup.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        url = load_settings().database_url.get_secret_value()
    return sqlalchemy_url(url)


def run_migrations_offline() -> None:
    """Write the SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
