"""FastAPI application. Run it with `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import accounts, entries, health, suggestions, tags
from app.ai import AILimits, create_ai_provider
from app.cors import AllowedOriginsCORSMiddleware
from app.db import create_db_engine
from app.errors import UnexpectedErrorMiddleware, register_error_handlers
from app.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Without explicit settings, they are loaded from the environment."""
    settings = settings or load_settings()
    ai_provider = create_ai_provider(settings)  # an unknown AI_PROVIDER stops the app here
    engine = create_db_engine(settings)  # connects lazily, on first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="Winlog API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.ai_provider = ai_provider
    # The daily AI limits, checked by the limited entry point (app/ai/limits.py, issue #15).
    app.state.ai_limits = AILimits.from_settings(settings)

    # The middleware added last runs first. UnexpectedErrorMiddleware runs inside the CORS
    # middleware, so the shared 500 response gets CORS headers like every other response.
    app.add_middleware(UnexpectedErrorMiddleware)
    app.add_middleware(
        AllowedOriginsCORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        # Authorization carries the bearer token (openapi.yaml, bearerAuth).
        allow_headers=["Authorization", "Content-Type"],
        # Lets the frontend read the export file name from cross-origin responses.
        expose_headers=["Content-Disposition"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(entries.router)
    app.include_router(tags.router)
    app.include_router(suggestions.router)
    return app


app = create_app()
