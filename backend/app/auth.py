"""Login tokens and request authentication (issue #7). Covers FR-A2 and FR-A3.

A token is a random value from `secrets`. Only its SHA-256 hash is stored, so a copy of the
database cannot be used to log in. Clients send the token as `Authorization: Bearer <token>`
(openapi.yaml, `bearerAuth`).

Every operation that needs authentication depends on `get_current_user`.
"""

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
