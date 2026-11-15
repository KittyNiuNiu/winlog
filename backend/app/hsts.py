"""The HTTP Strict Transport Security header on every response (issue #99).

With `HSTS_MAX_AGE_SECONDS` (app/settings.py, default 31,536,000, one year) greater than 0,
every response the app sends has one header `Strict-Transport-Security: max-age=<seconds>;
includeSubDomains`. A browser that has reached the backend over HTTPS then uses only HTTPS for
its host, for that many seconds, so a typed or followed `http://` address to the API (its docs
at `/docs`, `/health`) no longer goes out unencrypted first. There is no `preload`. With 0 the
app sends no such header. RFC 6797: https://www.rfc-editor.org/rfc/rfc6797

The setting alone decides. The middleware does not look at the request's scheme or at
`X-Forwarded-Proto`: on Render, TLS ends at Render's load balancer, which forwards every
request to the app over plain HTTP, and only after it has redirected plain `http://` requests
to `https://` (ops/deployment.md, "HTTPS"). So every request that reaches the app there came
over HTTPS. Where the backend itself serves plain HTTP (Docker Compose, a local `.env` copied
from `.env.example`), the setting is 0, because the header must not be sent over plain HTTP
(RFC 6797 §7.2), and browsers ignore it there (§8.1).

How it works, as a pure ASGI middleware: it adds the header to the `http.response.start`
message, so the status, the body and every other header stay as they are. A response that
already has the header, in any letter case, keeps its own and gets no second one. Add it
outside the CORS middleware (app/main.py), so it also covers the answers the CORS middleware
sends itself, the 413 of app/body_limit.py and the shared 500.

Out of scope, because they never pass through the app: Render's redirect and error pages, and
uvicorn's plain-text 400 for a request line and headers over 16 KiB. Starlette's last-resort
500, for an error raised in a middleware outside UnexpectedErrorMiddleware (app/errors.py), is
sent from Starlette's outermost layer, outside every middleware the app adds, so it gets
neither the CORS headers nor this one. The shared 500 for an error in a route has both.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER_NAME = b"strict-transport-security"


def hsts_header_value(max_age_seconds: int) -> str:
    """The header's value for `max_age_seconds`: `max-age=<seconds>; includeSubDomains`."""
    return f"max-age={max_age_seconds}; includeSubDomains"


class StrictTransportSecurityMiddleware:
    """Adds `Strict-Transport-Security` to every HTTP response, unless `max_age_seconds` is 0."""

    def __init__(self, app: ASGIApp, max_age_seconds: int) -> None:
        self.app = app
        self.header_value = (
            hsts_header_value(max_age_seconds).encode("latin-1") if max_age_seconds > 0 else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.header_value is None:
            await self.app(scope, receive, send)
            return

        header_value = self.header_value

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(bytes(name).lower() == HEADER_NAME for name, _ in headers):
                    headers.append((HEADER_NAME, header_value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
