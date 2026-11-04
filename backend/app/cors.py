"""CORS for the frontend origins listed in CORS_ALLOWED_ORIGINS."""

from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers
from starlette.types import Message, Receive, Scope, Send


class AllowedOriginsCORSMiddleware(CORSMiddleware):
    """FastAPI's CORS middleware, but other origins get no CORS headers at all.

    The parent class leaves out only Access-Control-Allow-Origin for an origin that is not
    allowed. It still adds Access-Control-Expose-Headers to every response with an Origin
    header, and its fixed Access-Control-Allow-Methods, -Allow-Headers and -Max-Age to every
    preflight. For other origins this class removes every Access-Control-* header and keeps
    the rest of the response (status, body, Vary) as the parent class builds it.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await super().__call__(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin is None or self.is_allowed_origin(origin):
            await super().__call__(scope, receive, send)
            return

        async def send_without_cors_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if not name.lower().startswith(b"access-control-")
                ]
            await send(message)

        await super().__call__(scope, receive, send_without_cors_headers)
