"""The shared error format from openapi.yaml (`components.schemas.Error`).

Every error response has a machine-readable `code` and a human-readable `message`.
Validation errors also list each failing field in `fields`.
"""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_PARTS = {"body", "query", "path", "header", "cookie"}


def error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    content = {"code": code, "message": message, **extra}
    return JSONResponse(status_code=status_code, content=content, headers=headers)


class ApiError(Exception):
    """Raise from an endpoint to answer with the shared error format."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        self.extra = extra


def _field_name(location: Sequence[Any]) -> str:
    """Turn a location such as ("body", "tags", 0) into "tags.0"."""
    parts = list(location)
    if len(parts) > 1 and parts[0] in _REQUEST_PARTS:
        parts = parts[1:]
    return ".".join(str(part) for part in parts) or "request"


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only the location and message are used. The submitted values are never echoed or logged.
    fields = [{"field": _field_name(err["loc"]), "reason": err["msg"]} for err in exc.errors()]
    return error_response(
        422, "validation_failed", "The request has invalid fields.", fields=fields
    )


async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:
        return error_response(404, "not_found", "Not found.", headers=exc.headers)
    if exc.status_code == 405:
        return error_response(405, "method_not_allowed", "Method not allowed.", headers=exc.headers)
    return error_response(
        exc.status_code, "internal_error", "Something went wrong.", headers=exc.headers
    )


async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, headers=exc.headers, **exc.extra)


def _internal_error_response() -> JSONResponse:
    # Never says what went wrong: exception details stay on the server.
    return error_response(500, "internal_error", "Something went wrong.")


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return _internal_error_response()


class UnexpectedErrorMiddleware:
    """Answers an unexpected error with the shared 500 response, inside the CORS middleware.

    Starlette runs the handler registered for `Exception` in its outermost middleware,
    outside every middleware the app adds. A 500 response sent from there skips the CORS
    middleware, so a browser blocks it and the frontend cannot read the error. Add this
    middleware before the CORS middleware, so that it runs inside it: the 500 response then
    gets the same CORS headers as every other response.

    After answering, it raises the error again, so the server still logs it. The outer
    handler sees that a response has started and sends no second one.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_and_track_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_and_track_start)
        except Exception:
            if not response_started:
                await _internal_error_response()(scope, receive, send)
            raise


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    # Fallback for errors outside UnexpectedErrorMiddleware, for example in the CORS middleware.
    app.add_exception_handler(Exception, _handle_unexpected_error)
