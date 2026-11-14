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
USER winlog

# The default port. Render sets PORT, and start.sh then listens on that port instead.
EXPOSE 8000
# Apply the database migrations, reset the demo account when DEMO_EMAIL is set, then start the
# server on PORT or 8000 (see start.sh). A failed step stops the start.
CMD ["sh", "/app/start.sh"]
