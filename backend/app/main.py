"""FastAPI application. Run it with `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import accounts, demo, entries, export, health, suggestions, summaries, tags
from app.ai import AILimits, create_ai_provider
from app.attempt_limits import AttemptLimiter
from app.cors import AllowedOriginsCORSMiddleware
from app.db import create_db_engine
from app.errors import UnexpectedErrorMiddleware, register_error_handlers
from app.settings import Settings, load_settings
from app.telemetry import Telemetry, TelemetryMiddleware, configure_logging


def create_app(settings: Settings | None = None, telemetry: Telemetry | None = None) -> FastAPI:
    """Build the app. Without explicit settings, they are loaded from the environment.

    Without explicit telemetry, it comes from the settings: OTLP export when
    OTEL_EXPORTER_OTLP_ENDPOINT is set, none otherwise. Tests pass in-memory exporters.
    """
    settings = settings or load_settings()
    ai_provider = create_ai_provider(settings)  # an unknown AI_PROVIDER stops the app here
    engine = create_db_engine(settings)  # connects lazily, on first use
    # JSON logs for the `app` loggers, and uvicorn's access log off (app/telemetry.py, #74).
    configure_logging()
    if telemetry is None:
        telemetry = Telemetry.from_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The OTLP export starts only here, so an app that is built but never started (an
        # import, a test client without its lifespan) never connects to a collector.
        telemetry.start()
        try:
            yield
        finally:
            engine.dispose()
            # Flushes the last signals. The export timeout is short, so a missing collector
            # cannot hold up the shutdown.
            telemetry.shutdown()

    app = FastAPI(title="Winlog API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.ai_provider = ai_provider
    app.state.telemetry = telemetry
    # The daily AI limits, checked by the limited entry point (app/ai/limits.py, issue #15).
    app.state.ai_limits = AILimits.from_settings(settings)
    # The login and demo-login attempt limits (app/attempt_limits.py, FR-A4, issue #46).
    app.state.attempt_limiter = AttemptLimiter.from_settings(engine, settings)

    # The middleware added last runs first. UnexpectedErrorMiddleware runs inside the CORS
    # middleware, so the shared 500 response gets CORS headers like every other response.
    app.add_middleware(UnexpectedErrorMiddleware)
    app.add_middleware(
        AllowedOriginsCORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        # Authorization carries the bearer token (openapi.yaml, bearerAuth).
        allow_headers=["Authorization", "Content-Type"],
        # Lets the frontend read the export file name and, after too many login attempts,
        # the seconds to wait (FR-A4) from cross-origin responses.
        expose_headers=["Content-Disposition", "Retry-After"],
    )
    # Added last, so it runs first: its SERVER span and `request finished` line cover every
    # response, including the CORS answers and the shared 500 response.
    app.add_middleware(TelemetryMiddleware, telemetry=telemetry)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(accounts.router)
    app.include_router(demo.router)
    app.include_router(entries.router)
    app.include_router(tags.router)
    app.include_router(suggestions.router)
    app.include_router(summaries.router)
    app.include_router(export.router)
    return app


app = create_app()
