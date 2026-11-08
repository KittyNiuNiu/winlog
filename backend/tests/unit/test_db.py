import pytest

from app.db import sqlalchemy_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
    ],
)
def test_plain_postgres_urls_use_the_psycopg_driver(given, expected):
    assert sqlalchemy_url(given) == expected


def test_database_errors_hide_the_values_of_the_statement(settings):
    """AGENTS.md: never log entry text, summaries or passwords, also not through a traceback."""
    from app.db import create_db_engine

    engine = create_db_engine(settings)

    assert engine.hide_parameters is True
