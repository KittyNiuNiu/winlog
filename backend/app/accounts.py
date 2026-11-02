"""Registration (`register` in openapi.yaml). Covers FR-A1."""

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session, violates
from app.errors import ApiError
from app.models import User
from app.passwords import hash_password, password_problems

router = APIRouter(tags=["Accounts"])


class Registration(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _store_in_lower_case(cls, email: str) -> str:
        # EmailStr already trims surrounding spaces and lower-cases the domain.
        return email.lower()

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
