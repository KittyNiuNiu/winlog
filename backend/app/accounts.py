"""Registration, login and logout (`register`, `login` and `logout` in openapi.yaml).

Covers FR-A1 and FR-A2.
"""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import CurrentLogin, create_token, get_current_login, get_current_user
from app.db import get_session, violates
from app.errors import ApiError
from app.models import Token, User
from app.passwords import (
    MAX_LENGTH,
    hash_password,
    password_problems,
    verify_against_dummy_hash,
    verify_password,
)

router = APIRouter(tags=["Accounts"])


def _normalise_email(email: str) -> str:
    # EmailStr already trims surrounding spaces and lower-cases the domain.
    return email.lower()


class Registration(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _store_in_lower_case(cls, email: str) -> str:
        return _normalise_email(email)

    @field_validator("password")
    @classmethod
    def _meet_the_password_rule(cls, password: str) -> str:
        problems = password_problems(password)
        if problems:
            raise PydanticCustomError("password_rule", "Password " + "; ".join(problems) + ".")
        return password


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    created_at: dt.datetime


@router.post(
    "/auth/register",
    operation_id="register",
    summary="Register with an email address and a password.",
    status_code=201,
    response_model=UserResponse,
)
def register(
    registration: Registration, session: Annotated[Session, Depends(get_session)]
) -> UserResponse:
    user = User(email=registration.email, password_hash=hash_password(registration.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        # The unique constraint also settles two registrations arriving at the same time.
        if violates(error, "uq_users_email"):
            raise ApiError(
                409, "email_already_registered", "This email is already registered."
            ) from None
        raise
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)


class Credentials(BaseModel):
    email: EmailStr
    # No strength rule, so passwords keep working if the rule changes. An empty password
    # counts as missing. No account can have a longer password than registration allows.
    # With a length limit, pydantic also rejects an unpaired surrogate, which argon2 cannot
    # hash, so such a password gets the validation error instead of a 500.
    password: str = Field(min_length=1, max_length=MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def _compare_in_lower_case(cls, email: str) -> str:
        return _normalise_email(email)


class LoginResult(BaseModel):
    token: str
    expires_at: dt.datetime


def _invalid_credentials() -> ApiError:
    return ApiError(401, "invalid_credentials", "Wrong email or password.")


@router.post(
    "/auth/login",
    operation_id="login",
    summary="Log in with an email address and a password.",
    response_model=LoginResult,
)
def login(
    credentials: Credentials,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> LoginResult:
    user = session.scalars(select(User).where(User.email == credentials.email)).one_or_none()
    if user is None:
        # Same work as a wrong password, so the response time does not reveal the account.
        verify_against_dummy_hash(credentials.password)
        raise _invalid_credentials()
    if not verify_password(user.password_hash, credentials.password):
        raise _invalid_credentials()

    lifetime = dt.timedelta(days=request.app.state.settings.token_lifetime_days)
    token, row = create_token(session, user.id, lifetime)
    session.commit()
    return LoginResult(token=token, expires_at=row.expires_at)


@router.post(
    "/auth/logout",
    operation_id="logout",
    summary="Log out by revoking the current token.",
    status_code=204,
    dependencies=[Depends(get_current_user)],
)
def logout(
    current: Annotated[CurrentLogin, Depends(get_current_login)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    # Only the token of this request; the user's other tokens keep working.
    session.execute(delete(Token).where(Token.id == current.token_id))
    session.commit()
    return Response(status_code=204)
