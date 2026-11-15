"""The Git commit the backend was built from, for `GET /health` (`Health.commit`, #102).

The commit is build metadata, not configuration. CI's Backend image job passes the commit it
builds as the build argument GIT_COMMIT, and backend/Dockerfile writes it into the file
/app/git-commit, next to the `app` package, while the image is built. This module reads that
file. It reads no environment variable, so no value on Render, in Docker Compose or in .env can
change what `/health` reports. The Deploy workflow compares the value with the commit it
deployed, to tell the new deploy from the previous one.

A backend built without a commit reports `None` (null): Docker Compose builds the image without
the build argument, so the file is empty, and `uv run uvicorn` and the tests run from a checkout
that has no such file. A file whose content is not exactly a valid commit (40 lowercase
hexadecimal characters, with nothing before or after them) also gives `None`, never an invalid
string.

The file is read on each call. It holds 40 bytes and never changes in a running image.
"""

import re
from pathlib import Path

# /app/git-commit in the image; backend/git-commit in a checkout, where it does not exist.
GIT_COMMIT_FILE = Path(__file__).resolve().parent.parent / "git-commit"

_VALID_COMMIT = re.compile(r"[0-9a-f]{40}")


def recorded_commit() -> str | None:
    """The commit recorded in the image, or None when there is none or it is not valid."""
    try:
        value = GIT_COMMIT_FILE.read_text(encoding="ascii")
    except (OSError, ValueError):
        return None
    return value if _VALID_COMMIT.fullmatch(value) else None
