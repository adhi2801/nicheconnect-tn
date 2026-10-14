"""Turn overload into a quick "busy, try again" instead of a freeze (item 5a, D-093).

The load test froze a process at 400 people (D-092). A process has 15 database
connections and 40 worker threads. A request takes its connection in the
sign-in check, then waits for a thread to run the endpoint, while every
thread waits for a connection. Nothing moves until a 30-second timeout
answers 500, and the process stayed stuck after the load had gone.

This lets in at most `MAX_IN_FLIGHT_REQUESTS` at once, fewer than the
connections, so every request let in can always get one and the freeze
cannot form. A request that finds every place taken may wait
`BUSY_QUEUE_MS` for one to come free, which absorbs a burst. After that it
gets 503 with Retry-After at once, in our one error format, so a phone
backs off and retries rather than hanging.

The health checks are never held back. `/healthz` must keep saying the
process is alive, and `/readyz` has the connection kept free for it, so a
busy container is not mistaken for a dead one and restarted.

One process is one event loop, so the count needs no lock: nothing runs
between reading it and changing it. A waiting request checks again every few
milliseconds rather than holding an asyncio primitive, which is tied to one
event loop.
"""

import asyncio
import logging
import time

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import busy_response

logger = logging.getLogger(__name__)

# Never held back: liveness and readiness must answer when the process is
# busy, or a busy container looks dead.
EXEMPT_PATHS = frozenset({"/healthz", "/readyz"})
# How often a waiting request looks for a free place.
POLL_SECONDS = 0.005


class LoadSheddingMiddleware:
    """Pure ASGI middleware. See app/main.py for where it sits."""

    def __init__(self, app: ASGIApp, *, max_in_flight: int, queue_ms: int) -> None:
        self.app = app
        self.max_in_flight = max_in_flight
        self.queue_seconds = queue_ms / 1000
        self.in_flight = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        if not await self._take_a_place():
            logger.warning(
                "request.shed reason=in_flight_limit request_id=%s",
                scope.get("state", {}).get("request_id"),
            )
            await busy_response(Request(scope))(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1

    async def _take_a_place(self) -> bool:
        """A place among those in flight, waiting up to the queue time."""
        deadline = time.monotonic() + self.queue_seconds
        while self.in_flight >= self.max_in_flight:
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(POLL_SECONDS)
        self.in_flight += 1
        return True
