"""FastAPI application. Run it with `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import accounts, health
from app.db import create_db_engine
from app.errors import register_error_handlers
from app.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Without explicit settings, they are loaded from the environment."""
    settings = settings or load_settings()
    engine = create_db_engine(settings)  # connects lazily, on first use

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="Winlog API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine

    app.add_middleware(
        CORSMiddleware,
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
    return app


app = create_app()
