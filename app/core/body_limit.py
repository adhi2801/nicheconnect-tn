"""Refuse request bodies over a fixed size (security.md section 3).

Without this, anyone can post a 500 MB body to a public endpoint and make the
process buy the memory to hold it. No login is needed to try, which matters
more now that the Creator Passport answers to the open internet.

There are two checks here, because one alone is not enough:

1. **The declared size.** If `Content-Length` is already over the limit, the
   answer is 413 and the app is never called, so the body is never read. This
   is the path an honest client takes.
2. **The real size.** A body sent with `Transfer-Encoding: chunked` has no
   `Content-Length` at all, and a hostile client can simply declare a small
   one and send more. So the bytes are counted as they actually arrive, and
   the count is what decides.

Both answers are built from the same exception object, so the two paths
cannot drift into returning different error bodies.

Scope note: check 2 counts the body as the route reads it, rather than
buffering it here first. That keeps streaming intact for whenever uploads
arrive. It also means a route that never reads its body is protected by
check 1 alone — which is exactly the case check 1 covers.
"""

from http import HTTPStatus

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import DomainError, problem_response

# security.md section 3. Every request we accept today is JSON measured in
# kilobytes, so 1 MB is already generous. It lives here rather than in config
# because it is a safety rail, not a per-environment setting; move it to
# config.py when a founder wants to tune it per deployment.
MAX_BODY_BYTES = 1024 * 1024


class RequestBodyTooLarge(DomainError):
    """Raised once the bytes actually received pass the limit."""

    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    code = "body_too_large"
    title = "That request is too large"


def declared_length(scope: Scope) -> int | None:
    """The Content-Length the client claims, or None if it didn't say.

    A header that isn't a plain number tells us nothing, so it counts as
    "didn't say" and the real byte count decides instead.
    """
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodyLimitMiddleware:
    """Pure ASGI middleware. Add it before the rate limiter, so that a flood
    of oversized requests still counts against the sender's limit."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._refuse(scope, receive, send)
            return

        received = 0

        async def receive_counting() -> Message:
            """Pass the body through, keeping a running total of its size."""
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # Raised inside the route's read, so the existing
                    # DomainError handler turns it into Problem Details.
                    raise self._error()
            return message

        await self.app(scope, receive_counting, send)

    def _error(self) -> RequestBodyTooLarge:
        return RequestBodyTooLarge(
            f"Requests are limited to {self.max_bytes:,} bytes."
        )

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 413 directly, without calling the app or reading the body."""
        error = self._error()
        response = problem_response(
            Request(scope, receive),
            status=error.status_code,
            code=error.code,
            title=error.title,
            detail=error.detail,
        )
        await response(scope, receive, send)
