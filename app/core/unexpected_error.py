"""Turn an unexpected error into our 500 answer inside the middleware (D-045).

Starlette runs a handler registered for `Exception` in its outermost layer,
outside every middleware we add. So the 500 it built skipped the security
headers, and would skip the CORS permission a browser needs before a page
may read an answer: the dashboard would see a bare "network error", with no
request ID to quote. Measured on 22 Sep 2026: a 500 carried no
Content-Security-Policy and no X-Content-Type-Options, while a 404 had both.

This layer sits inside the security headers, the request ID and CORS, so
the answer it builds passes out through all three. It calls the same handler
(app/core/errors.py), so the body and the log line do not change. That
handler also stays registered for `Exception`, as the backstop for anything
that fails outside this layer.

Once an answer has started going out, a clean 500 can no longer replace it.
Then the error is passed on unchanged, for the backstop and the server to
deal with.
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import handle_unexpected_error


class UnexpectedErrorMiddleware:
    """Pure ASGI middleware. See app/main.py for where it sits."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_noting_start(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_noting_start)
        except Exception as exc:
            if started:
                raise
            response = await handle_unexpected_error(Request(scope), exc)
            await response(scope, receive, send)
