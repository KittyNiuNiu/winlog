"""FastAPI application. Run it with `uv run uvicorn app.main:app --reload`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import health
from app.errors import register_error_handlers
from app.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Without explicit settings, they are loaded from the environment."""
    settings = settings or load_settings()

    app = FastAPI(title="Winlog API", version="0.1.0")
    app.state.settings = settings

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
    return app


app = create_app()
