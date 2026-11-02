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

    def __init__(self, status_code: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
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
    return error_response(exc.status_code, exc.code, exc.message, **exc.extra)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "internal_error", "Something went wrong.")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _handle_api_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
