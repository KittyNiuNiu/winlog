from pathlib import Path

import yaml

from app.models import CATEGORIES, Base

OPENAPI_PATH = Path(__file__).resolve().parents[3] / "openapi.yaml"


def test_categories_match_the_contract():
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))

    assert list(CATEGORIES) == spec["components"]["schemas"]["Category"]["enum"]


def test_models_cover_the_tables_from_the_data_model():
    assert set(Base.metadata.tables) == {
        "users",
        "tokens",
        "entries",
        "tags",
        "entry_tags",
        "summaries",
        "ai_usage",
    }


def test_deleting_a_user_cascades_to_every_table_that_references_it():
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            assert foreign_key.ondelete == "CASCADE", f"{table.name}.{foreign_key.parent.name}"
