"""The shared demo account: demo-login and the block on deleting it (FR-X1, issue #21).

Operation `demoLogin` and the `demo_account_not_deletable` error of `deleteAccount` in
openapi.yaml. The demo account is the user whose email is `DEMO_EMAIL`. An empty or missing
`DEMO_EMAIL` turns the demo off. The seed script (`scripts/seed_demo`, using
`app/demo_seed.py`) creates the user with a random password that nobody knows, so demo-login
is the only way in.

Apart from deletion, a demo session is a normal login: its token is created and checked like
any other, and every visitor uses the same user, so they share its data and its daily AI
limits (§8).
"""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attempt_limits import AttemptLimiterDependency, visitor_ip
from app.auth import AuthenticateFirstRoute, CurrentUser, create_token
from app.db import get_session
from app.errors import ApiError
from app.models import User
from app.settings import Settings

router = APIRouter(tags=["Accounts"], route_class=AuthenticateFirstRoute)


def is_demo_user(settings: Settings, user: User) -> bool:
    """True if the demo is turned on and the user is the demo account."""
    # Both emails are stored in lower case (registration and the setting normalise them).
    return settings.demo_email is not None and user.email == settings.demo_email


class DemoLoginResult(BaseModel):
    token: str
    expires_at: dt.datetime
    # Always true: marks the session as a demo session.
    demo: Literal[True]


def _demo_not_available() -> ApiError:
    return ApiError(404, "not_found", "The demo is not available.")


@router.post(
    "/auth/demo",
    operation_id="demoLogin",
    summary="Log in to the shared demo account.",
    response_model=DemoLoginResult,
    responses={
        404: {"description": "No demo account is configured or created."},
        429: {"description": "Too many demo-logins from this visitor (FR-A4)."},
    },
)
def demo_login(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    attempts: AttemptLimiterDependency,
) -> DemoLoginResult:
    # FR-A4: every demo-login request counts for the visitor's IP, before anything else.
    attempts.take_demo_login(visitor_ip(request))
    settings: Settings = request.app.state.settings
    if settings.demo_email is None:
        raise _demo_not_available()
    user_id = session.scalars(
        select(User.id).where(User.email == settings.demo_email)
    ).one_or_none()
    if user_id is None:
        # Configured, but the seed script has not created the account yet.
        raise _demo_not_available()

    # Exactly as login: the same lifetime, and the account's expired tokens are deleted.
    lifetime = dt.timedelta(days=settings.token_lifetime_days)
    token, row = create_token(session, user_id, lifetime)
    session.commit()
    return DemoLoginResult(token=token, expires_at=row.expires_at, demo=True)


def demo_account_not_deletable() -> ApiError:
    return ApiError(409, "demo_account_not_deletable", "The demo account cannot be deleted.")


def refuse_demo_account(request: Request, user: CurrentUser) -> None:
    """FastAPI dependency for account deletion: the demo account gets the demo error.

    It depends on the login, so a request without a valid token still gets 401 first. FastAPI
    runs dependencies before it reports an invalid body, and `AuthenticateFirstRoute` runs the
    dependencies that lead to the login before it reports a body it cannot read. So a demo
    session gets this error whatever its body: before the body is validated and before the
    password is checked. Nothing has been changed when it is raised.
    """
    if is_demo_user(request.app.state.settings, user):
        raise demo_account_not_deletable()
