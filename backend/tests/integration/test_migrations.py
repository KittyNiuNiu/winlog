from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from tests.integration.conftest import APP_TABLES, reset_schema, table_names


def test_migrations_create_every_table_in_an_empty_database(engine: Engine, alembic_config: Config):
    reset_schema(engine)
    assert table_names(engine) == set()

    command.upgrade(alembic_config, "head")

    assert table_names(engine) == APP_TABLES | {"alembic_version"}


def test_migrations_can_be_undone_and_applied_again(engine: Engine, alembic_config: Config):
    command.upgrade(alembic_config, "head")

    command.downgrade(alembic_config, "base")
    assert table_names(engine) == {"alembic_version"}

    command.upgrade(alembic_config, "head")
    assert table_names(engine) == APP_TABLES | {"alembic_version"}


def test_models_match_the_migrations(alembic_config: Config):
    """Same as `uv run alembic check`: raises if the models and migrations differ."""
    command.upgrade(alembic_config, "head")

    command.check(alembic_config)


def _column_types(engine: Engine, data_type: str) -> set[tuple[str, str]]:
    query = text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND data_type = :data_type"
    )
    with engine.connect() as connection:
        return {tuple(row) for row in connection.execute(query, {"data_type": data_type})}


def test_ids_are_uuids_as_in_openapi(migrated_db: Engine):
    uuid_columns = _column_types(migrated_db, "uuid")

    for table in ("users", "tokens", "entries", "tags", "summaries"):
        assert (table, "id") in uuid_columns


def test_every_timestamp_is_time_zone_aware(migrated_db: Engine):
    assert _column_types(migrated_db, "timestamp without time zone") == set()
    assert _column_types(migrated_db, "timestamp with time zone") == {
        ("users", "created_at"),
        ("tokens", "created_at"),
        ("tokens", "expires_at"),
        ("entries", "created_at"),
        ("entries", "updated_at"),
        ("summaries", "created_at"),
        ("summaries", "updated_at"),
    }
