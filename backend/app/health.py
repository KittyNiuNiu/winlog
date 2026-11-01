"""The health endpoint (`getHealth` in openapi.yaml)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Health"])


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


@router.get(
    "/health",
    operation_id="getHealth",
    summary="Check that the API and the database are up.",
    response_model=Health,
)
def get_health() -> Health:
    # The real database check, and the "database unreachable" error, are added in issue #4.
    return Health(status="ok", database="ok")
