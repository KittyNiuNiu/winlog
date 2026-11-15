"""The health endpoint (`getHealth` in openapi.yaml)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import AuthenticateFirstRoute
from app.db import database_is_reachable
from app.errors import error_response
from app.git_commit import recorded_commit

router = APIRouter(tags=["Health"], route_class=AuthenticateFirstRoute)


class Health(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    # The commit the backend was built from, or None (app/git_commit.py, #102).
    commit: str | None


def check_database(request: Request) -> bool:
    return database_is_reachable(
        request.app.state.engine, request.app.state.settings.database_connect_timeout_seconds
    )


@router.get(
    "/health",
    operation_id="getHealth",
    summary="Check that the API and the database are up.",
    response_model=Health,
    responses={503: {"description": "The database cannot be reached."}},
)
def get_health(database_ok: Annotated[bool, Depends(check_database)]) -> Health | JSONResponse:
    if not database_ok:
        return error_response(503, "database_unreachable", "The database is not reachable.")
    return Health(status="ok", database="ok", commit=recorded_commit())
