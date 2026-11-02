"""Fixtures shared by unit and integration tests."""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.yaml"
CONTRACT_URI = "urn:winlog:openapi"


@pytest.fixture(scope="session")
def contract() -> Callable[[str], Draft202012Validator]:
    """Return a validator for a schema in openapi.yaml, for example contract("Error")."""
    spec = yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))
    registry = Registry().with_resource(
        CONTRACT_URI, Resource(contents=spec, specification=DRAFT202012)
    )

    def validator(schema_name: str) -> Draft202012Validator:
        ref = {"$ref": f"{CONTRACT_URI}#/components/schemas/{schema_name}"}
        return Draft202012Validator(ref, registry=registry)

    return validator
