# Backend image: Python 3.13 (pinned in .python-version), dependencies installed with uv.
FROM python:3.13-slim

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

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 winlog
USER winlog

EXPOSE 8000
# Apply the database migrations, then start the server. `exec` makes uvicorn the main
# process, so it receives stop signals directly.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
