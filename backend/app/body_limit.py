"""The limit on the size of a request body (issue #88).

No request can make the backend read, parse or store more than `REQUEST_BODY_MAX_BYTES` bytes
of body (app/settings.py, default 262,144). A larger body gets 413 `request_too_large` in the
shared error format (openapi.yaml, `components.responses.RequestTooLarge`), on every path and
method, before routing, authentication and validation. Nothing is saved and no AI call is made.

How it works, as an ASGI middleware that runs before the app sees the request:

- A `Content-Length` over the limit is refused at once. The body is not read, so a request
  without a body in the contract (`GET /entries`, `POST /auth/logout`) and an unknown path get
  the same 413.
- Otherwise the middleware reads the body itself, counting the bytes as they arrive, after the
  server has removed any chunked transfer encoding. As soon as more than the limit has
  arrived it stops reading and answers 413, so a chunked body without `Content-Length` cannot
  get past it. A body within the limit is then handed to the app unchanged, as one message,
  so the app behaves as before. At most the limit plus one received chunk is held in memory.

Starlette's `RequestBodyLimitMiddleware` is not used: its own answers are plain text, it
replaces the app's response when `Content-Length` is over the limit, and in a FastAPI route
its error arrives after the body has started to parse, where the token check of
`AuthenticateFirstRoute` (app/auth.py) would answer first. Reading the body here, before the
app runs, gives the same 413 with or without a valid token.

Add it inside the CORS middleware and inside `TelemetryMiddleware` (app/main.py), so the 413
gets the CORS headers of every other error response and its `request finished` line. The
body is never logged or put into telemetry.

Out of scope: uvicorn's own limit of 16 KiB on the request line and headers (h11), which it
enforces before the app runs with a plain-text 400 (openapi.yaml, Size limits).
"""

from collections import deque

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import request_too_large_response


class RequestBodyLimitMiddleware:
    """Answers 413 `request_too_large` for a request body of more than `max_body_bytes`."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await request_too_large_response()(scope, receive, send)
            return

        body = bytearray()
        disconnect: Message | None = None
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # The client went away (`http.disconnect`): the app sees that, as before.
                disconnect = message
                break
            body += message.get("body", b"")
            if len(body) > self.max_body_bytes:
                await request_too_large_response()(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        # The body as one message, so memory holds it once however it was sent. Then the
        # server's own messages, such as `http.disconnect`.
        pending: deque[Message] = deque(
            [{"type": "http.request", "body": bytes(body), "more_body": disconnect is not None}]
        )
        if disconnect is not None:
            pending.append(disconnect)
        del body

        async def receive_again() -> Message:
            if pending:
                return pending.popleft()
            return await receive()

        await self.app(scope, receive_again, send)


def _content_length(scope: Scope) -> int | None:
    """The request's `Content-Length` as a number, or None when it is missing or not one."""
    value = Headers(scope=scope).get("content-length")
    if value is None or not value.strip().isascii() or not value.strip().isdigit():
        return None
    return int(value.strip())
