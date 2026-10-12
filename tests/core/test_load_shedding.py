"""Overload becomes a quick "busy, try again", never a freeze (item 5a, D-093).

The middleware is driven directly, with endpoints held open on purpose, so
each limit is crossed on every run rather than by luck (testing.md section
4). Then the real app shows the 503 in our one error format, with every
header, and the startup check refuses a limit that would let the freeze back.
"""

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.types import Receive, Scope, Send

from app.core.errors import BUSY_RETRY_AFTER_SECONDS
from app.core.load_shedding import EXEMPT_PATHS, LoadSheddingMiddleware
from app.core.request_id import REQUEST_ID_HEADER
from app.db.session import get_db
from app.main import app
from tests.core.test_config import load


class HeldEndpoint:
    """An ASGI app whose requests stay open until released."""

    def __init__(self, *, fail: bool = False) -> None:
        self.release = asyncio.Event()
        self.started = 0
        self.fail = fail

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.started += 1
        await self.release.wait()
        if self.fail:
            raise RuntimeError("the endpoint broke")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def call(app: Any, path: str = "/api/v1/campaigns") -> dict[str, Any]:
    """One request through `app`; its status, headers and body."""
    scope = {"type": "http", "path": path, "method": "GET", "headers": [], "state": {}}
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    return {"status": start["status"], "headers": headers, "body": body}


def bounded(scenario) -> Any:
    """Run a scenario, failing in 5 s rather than hanging if a limit breaks:
    with no limit, a request meant to be turned away waits on the held one."""
    return asyncio.run(asyncio.wait_for(scenario(), timeout=5))


async def until(condition, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.001)


def test_requests_under_the_limit_all_go_through():
    async def scenario():
        held = HeldEndpoint()
        shedding = LoadSheddingMiddleware(held, max_in_flight=2, queue_ms=0)
        calls = [asyncio.create_task(call(shedding)) for _ in range(2)]
        await until(lambda: held.started == 2)
        held.release.set()
        return [r["status"] for r in await asyncio.gather(*calls)], shedding.in_flight

    statuses, left = bounded(scenario)

    assert statuses == [200, 200]
    assert left == 0


def test_past_the_limit_it_answers_busy_at_once_in_our_error_format():
    async def scenario():
        held = HeldEndpoint()
        shedding = LoadSheddingMiddleware(held, max_in_flight=1, queue_ms=50)
        first = asyncio.create_task(call(shedding))
        await until(lambda: held.started == 1)
        turned_away = await call(shedding)
        held.release.set()
        await first
        return turned_away, held.started

    busy, started = bounded(scenario)

    assert busy["status"] == 503
    assert busy["headers"]["retry-after"] == str(BUSY_RETRY_AFTER_SECONDS)
    assert busy["headers"]["content-type"] == "application/problem+json"
    assert json.loads(busy["body"])["code"] == "service_busy"
    assert started == 1  # the endpoint never saw the second request


def test_a_place_that_frees_while_waiting_is_taken():
    async def scenario():
        held = HeldEndpoint()
        shedding = LoadSheddingMiddleware(held, max_in_flight=1, queue_ms=2000)
        first = asyncio.create_task(call(shedding))
        await until(lambda: held.started == 1)
        second = asyncio.create_task(call(shedding))
        await asyncio.sleep(0.05)  # waiting in the queue
        held.release.set()
        return [r["status"] for r in await asyncio.gather(first, second)]

    assert bounded(scenario) == [200, 200]


@pytest.mark.parametrize("path", sorted(EXEMPT_PATHS))
def test_the_health_checks_are_never_held_back(path):
    async def scenario():
        held = HeldEndpoint()
        shedding = LoadSheddingMiddleware(held, max_in_flight=1, queue_ms=0)
        first = asyncio.create_task(call(shedding))
        await until(lambda: held.started == 1)
        probe = asyncio.create_task(call(shedding, path))
        await until(lambda: held.started == 2)  # let through, not turned away
        held.release.set()
        return (await probe)["status"], (await first)["status"]

    assert bounded(scenario) == (200, 200)


def test_a_failed_request_still_gives_its_place_back():
    async def scenario():
        held = HeldEndpoint(fail=True)
        shedding = LoadSheddingMiddleware(held, max_in_flight=1, queue_ms=0)
        task = asyncio.create_task(call(shedding))
        await until(lambda: held.started == 1)
        held.release.set()
        with pytest.raises(RuntimeError):
            await task
        return shedding.in_flight

    assert bounded(scenario) == 0


# --- the real app ------------------------------------------------------------------------


def test_a_connection_that_does_not_come_free_is_busy_not_an_error():
    """The second guard: background jobs share the pool, so the limit alone
    cannot promise a connection; a wait past the pool timeout is a 503."""

    def no_connection_free():
        raise PoolTimeoutError("QueuePool limit reached")

    app.dependency_overrides[get_db] = no_connection_free
    try:
        response = TestClient(app).get("/api/v1/campaigns/discover")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["code"] == "service_busy"
    assert response.headers["retry-after"] == str(BUSY_RETRY_AFTER_SECONDS)
    assert response.headers[REQUEST_ID_HEADER.lower()]
    assert "content-security-policy" in response.headers


def test_every_operation_documents_the_busy_answer():
    missing = [
        f"{method.upper()} {path}"
        for path, item in app.openapi()["paths"].items()
        for method, operation in item.items()
        if "503" not in operation.get("responses", {})
    ]

    assert missing == []


@pytest.mark.parametrize(
    ("pool", "overflow", "in_flight"), [(5, 10, 15), (5, 10, 16), (2, 0, 2)]
)
def test_a_limit_that_could_use_every_connection_stops_the_app(pool, overflow, in_flight):
    with pytest.raises(ValidationError, match="MAX_IN_FLIGHT_REQUESTS"):
        load(
            db_pool_size=pool, db_max_overflow=overflow, max_in_flight_requests=in_flight
        )


def test_the_defaults_leave_connections_spare():
    found = load()

    assert found.max_in_flight_requests < found.db_pool_size + found.db_max_overflow
    assert found.db_pool_timeout_seconds <= 2
