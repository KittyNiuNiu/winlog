"""Seed or reset the shared demo account (FR-X1, issue #21).

Run in `backend/`: `uv run python -m scripts.seed_demo`

It reads the backend's settings (environment variables, or the repository-root `.env` file)
and needs the database at the latest migration (`uv run alembic upgrade head`). It creates the
user `DEMO_EMAIL` if missing, gives it a new random password and replaces its entries, tags
and summaries with the sample data in `app/demo_seed.py`. Other users are never touched, and
the AI is never called. The password is never printed or logged. With `DEMO_EMAIL` empty or not
set, the demo is turned off and the script changes nothing.
"""

import datetime as dt
import sys

from sqlalchemy.orm import Session

from app.db import create_db_engine
from app.demo_seed import reset_demo_account
from app.settings import Settings, SettingsError, load_settings


def run(settings: Settings, today: dt.date | None = None) -> str:
    """Reset the demo account in one transaction and return what to print."""
    if settings.demo_email is None:
        return "The demo is turned off (DEMO_EMAIL is not set). Nothing was changed."
    # UTC, like every other day boundary in the backend (§8).
    today = today or dt.datetime.now(dt.UTC).date()
    engine = create_db_engine(settings)
    try:
        with Session(engine) as session:
            result = reset_demo_account(session, settings.demo_email, today)
            session.commit()
    finally:
        engine.dispose()
    return (
        f"Reset the demo account {settings.demo_email} to the sample data "
        f"(entries: {result.entries}, tags: {result.tags}, summaries: {result.summaries})."
    )


def main() -> int:
    try:
        settings = load_settings()
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 2
    print(run(settings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
