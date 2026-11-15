# Backend image: Python 3.13 (pinned in .python-version), dependencies installed with uv.
FROM python:3.13-slim

# Links the image in GitHub Container Registry to this repository (#39).
LABEL org.opencontainers.image.source=https://github.com/KittyNiuNiu/winlog

# uv is installed from PyPI at a pinned version.
RUN pip install --no-cache-dir --root-user-action=ignore uv==0.11.32

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so code changes don't reinstall them. Only runtime dependencies.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-cache

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
# The demo reset that start.sh runs (issue #21). Only this script: scripts/model_comparison/
# and its result files stay out of the image (also excluded in .dockerignore).
COPY scripts/__init__.py scripts/seed_demo.py ./scripts/
COPY start.sh ./

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 winlog

# The Git commit this image is built from, as build metadata (#102). CI's Backend image job
# passes it as the build argument GIT_COMMIT (the same commit as the revision label), and
# GET /health reports it (app/git_commit.py), so the Deploy workflow can tell the new deploy
# from the previous one. It is written into the file /app/git-commit, owned by root and
# read-only for the app's user, and the backend reads no environment variable for it: no value
# on Render, in Docker Compose or in .env can change it. A build without the argument (Docker
# Compose) writes an empty file, and /health then reports null. These lines come after the
# dependency install and the code, so a new commit rebuilds only this small layer.
ARG GIT_COMMIT=
RUN printf '%s' "$GIT_COMMIT" > /app/git-commit

USER winlog

# The default port. Render sets PORT, and start.sh then listens on that port instead.
EXPOSE 8000
# Apply the database migrations, reset the demo account when DEMO_EMAIL is set, then start the
# server on PORT or 8000 (see start.sh). A failed step stops the start.
CMD ["sh", "/app/start.sh"]
