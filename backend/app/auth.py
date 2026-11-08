"""Login tokens and request authentication (issue #7). Covers FR-A2 and FR-A3.

A token is a random value from `secrets`. Only its SHA-256 hash is stored, so a copy of the
database cannot be used to log in. Clients send the token as `Authorization: Bearer <token>`
(openapi.yaml, `bearerAuth`).

Every operation that needs authentication depends on `get_current_user`, and every router
uses `AuthenticateFirstRoute`, so a request without a valid token is rejected with 401 even
when its body is not valid JSON.
"""

import datetime as dt
import hashlib
import secrets
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import solve_dependencies
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.db import get_session
from app.errors import ApiError
from app.models import Token, User

# 32 random bytes, as the token from `secrets.token_urlsafe` (43 characters).
TOKEN_BYTES = 32

# Reads the header without raising, so a missing or malformed header gets the shared error.
# The scheme name matches openapi.yaml, so the generated schema names the same scheme.
_bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """The SHA-256 hash of the token, as stored in `tokens.token_hash`."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(session: Session, user_id: uuid.UUID, lifetime: dt.timedelta) -> tuple[str, Token]:
    """Add a new token for the user and delete the user's expired tokens.

    Returns the token itself, which only the client keeps, and the stored row. The caller
    commits. Other tokens that have not expired keep working, so each device has its own login.
    """
    now = utc_now()
    session.execute(delete(Token).where(Token.user_id == user_id, Token.expires_at <= now))
    token = new_token()
    row = Token(
        user_id=user_id, token_hash=hash_token(token), created_at=now, expires_at=now + lifetime
    )
    session.add(row)
    return token, row


def not_authenticated() -> ApiError:
    return ApiError(
        401, "not_authenticated", "Please log in.", headers={"WWW-Authenticate": "Bearer"}
    )


@dataclass(frozen=True)
class CurrentLogin:
    """The token used for this request, and its user."""

    token_id: uuid.UUID
    user: User


def get_current_login(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> CurrentLogin:
    """FastAPI dependency: the login behind the request's bearer token, or 401.

    The header is missing or malformed, or the token is unknown, expired or logged out: all
    of these get the same `not_authenticated` error.
    """
    if credentials is None:
        raise not_authenticated()
    row = session.execute(
        select(Token.id, User)
        .join(User, User.id == Token.user_id)
        .where(
            Token.token_hash == hash_token(credentials.credentials), Token.expires_at > utc_now()
        )
    ).one_or_none()
    if row is None:
        raise not_authenticated()
    return CurrentLogin(token_id=row[0], user=row[1])


def get_current_user(login: Annotated[CurrentLogin, Depends(get_current_login)]) -> User:
    """FastAPI dependency: the authenticated user. Rejects the request with 401 otherwise."""
    return login.user


CurrentUser = Annotated[User, Depends(get_current_user)]


# FastAPI reads the request body before it runs any dependency. A body it cannot read ends
# the request with one of these two errors, before `get_current_login` has checked the token:
# a RequestValidationError for JSON it cannot decode, or Starlette's HTTPException (not
# FastAPI's subclass) for anything else, such as bytes that are not UTF-8.
_BODY_PARSE_ERROR_DETAIL = "There was an error parsing the body"


def _is_body_parse_error(error: Exception) -> bool:
    if isinstance(error, RequestValidationError):
        return all(err.get("type") == "json_invalid" for err in error.errors())
    return (
        isinstance(error, HTTPException)
        and error.status_code == 400
        and error.detail == _BODY_PARSE_ERROR_DETAIL
    )


def _calls(dependant: Dependant) -> set[Callable[..., Any]]:
    found = {dependant.call} if dependant.call else set()
    for sub in dependant.dependencies:
        found |= _calls(sub)
    return found


class AuthenticateFirstRoute(APIRoute):
    """A route that checks the token before it reports a body it cannot read (FR-A3).

    FastAPI parses a JSON body before it runs the route's dependencies, so a body that is not
    valid JSON would get 422 `validation_failed` (or 400) even without a valid token. On such
    an error, an operation that needs authentication first solves the dependencies that lead
    to `get_current_login`: without a valid token they raise `not_authenticated`. With a
    valid token, the original body error is raised again, so it keeps its response.

    Only the error path runs the check, so a valid request still checks its token once.
    Nothing has run yet when the body fails to parse, so the request changes nothing.
    Operations without authentication, such as login, keep the body error. Only the route's
    own dependencies count, so authentication must not be added as a router-level dependency.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()
        login_dependencies = [
            sub for sub in self.dependant.dependencies if get_current_login in _calls(sub)
        ]
        if not login_dependencies:
            return handler
        login_check = Dependant(dependencies=login_dependencies, path=self.path_format)

        async def handler_checking_the_token_first(request: Request) -> Response:
            try:
                return await handler(request)
            except (RequestValidationError, HTTPException) as error:
                if not _is_body_parse_error(error):
                    raise
                # Raises `not_authenticated` if the token is missing or not valid. Test
                # overrides of these dependencies apply, as for the route itself.
                await solve_dependencies(
                    request=request,
                    dependant=login_check,
                    dependency_overrides_provider=request.app,
                    async_exit_stack=request.scope["fastapi_inner_astack"],
                    embed_body_fields=False,
                )
                raise

        return handler_checking_the_token_first
