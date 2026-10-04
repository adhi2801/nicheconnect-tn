"""Error tracking: crashes reach Sentry once, personal data never does (D-074).

Nothing here talks to Sentry. A transport that keeps each event in a list
stands in for the network, so the tests read exactly what would have left
the process.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.core.config import Settings
from app.core.error_tracking import init_error_tracking, redact
from app.core.errors import register_error_handlers
from app.core.unexpected_error import UnexpectedErrorMiddleware
from tests.core.test_config import load

DSN = "https://0123456789abcdef0123456789abcdef@o1.ingest.de.sentry.io/42"
PHONE = "+919876543210"
TOKEN = "eyJhbGciOiJIUzI1NiJ9.secret-access-token"
REQUEST_ID_LIKE = "0b1f8a3c-5d2e-4f6a-9b7c-123456789012"


class Collect(Transport):
    """Keeps every envelope instead of sending it."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)

    @property
    def events(self) -> list[dict[str, Any]]:
        found = (envelope.get_event() for envelope in self.envelopes)
        return [event for event in found if event is not None]


@pytest.fixture
def sent() -> Iterator[Collect]:
    transport = Collect()
    assert init_error_tracking(
        load(sentry_dsn=DSN, app_release="abc1234", environment="staging"),
        transport=transport,
    )
    try:
        yield transport
    finally:
        # Back to no client, so no other test reports anything.
        sentry_sdk.init(dsn=None)


def make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(UnexpectedErrorMiddleware)

    @app.post("/crash")
    async def crash(request: Request) -> None:
        phone = PHONE  # a local variable the trace must not carry
        raise RuntimeError(f"duplicate key: Key (phone)=({phone}) already exists")

    @app.get("/log-error")
    def log_error() -> dict[str, str]:
        logging.getLogger("app.test").error("otp.send_failed for %s", PHONE)
        return {"status": "ok"}

    @app.get("/missing")
    def missing() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404)

    @app.get("/unavailable")
    def unavailable() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503)

    return app


def text_of(event: dict[str, Any]) -> str:
    return json.dumps(event, default=str)


# --- on and off ---------------------------------------------------------------------------


def test_off_without_a_dsn():
    assert init_error_tracking(load()) is False


def test_an_empty_dsn_means_off():
    assert load(sentry_dsn="", app_release="").sentry_dsn is None


@pytest.mark.parametrize(
    "dsn",
    [
        "http://0123456789abcdef0123456789abcdef@o1.ingest.sentry.io/42",  # not https
        "https://o1.ingest.sentry.io/42",  # no key
        "https://0123456789abcdef0123456789abcdef@o1.ingest.sentry.io/",  # no project
        "not a dsn",
    ],
)
def test_a_malformed_dsn_stops_the_app(dsn):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{**load().model_dump(mode="json"), "sentry_dsn": dsn})


# --- a crash -------------------------------------------------------------------------------


def test_a_crash_is_reported_once_with_its_release_and_environment(sent):
    response = TestClient(make_app(), raise_server_exceptions=False).post("/crash")

    assert response.status_code == 500
    assert len(sent.events) == 1
    event = sent.events[0]
    assert event["exception"]["values"][-1]["type"] == "RuntimeError"
    assert event["release"] == "abc1234"
    assert event["environment"] == "staging"


def test_a_crash_report_carries_no_personal_data(sent):
    TestClient(make_app(), raise_server_exceptions=False).post(
        f"/crash?phone={PHONE}",
        json={"phone": PHONE, "upi_id": "priya@okaxis"},
        headers={"Authorization": f"Bearer {TOKEN}", "Cookie": f"session={TOKEN}"},
    )

    text = text_of(sent.events[0])
    assert PHONE not in text and "9876543210" not in text
    assert TOKEN not in text
    assert "priya@okaxis" not in text
    request = sent.events[0]["request"]
    assert "data" not in request
    assert "query_string" not in request
    assert "cookies" not in request
    assert "user" not in sent.events[0]


def test_a_crash_report_still_says_what_went_wrong(sent):
    TestClient(make_app(), raise_server_exceptions=False).post("/crash")

    value = sent.events[0]["exception"]["values"][-1]["value"]
    assert value == "duplicate key: Key (phone)=([phone]) already exists"


def test_the_stack_trace_carries_no_local_variables(sent):
    TestClient(make_app(), raise_server_exceptions=False).post("/crash")

    frames = sent.events[0]["exception"]["values"][-1]["stacktrace"]["frames"]
    assert frames
    assert all("vars" not in frame for frame in frames)


# --- error lines and ordinary refusals ----------------------------------------------------------


def test_an_error_log_line_is_reported_scrubbed(sent):
    TestClient(make_app()).get("/log-error")

    assert len(sent.events) == 1
    assert sent.events[0]["logentry"]["formatted"] == "otp.send_failed for [phone]"
    assert PHONE not in text_of(sent.events[0])


def test_an_ordinary_refusal_is_not_an_error(sent):
    assert TestClient(make_app()).get("/missing").status_code == 404

    assert sent.events == []


def test_a_deliberate_503_is_not_an_error(sent):
    assert TestClient(make_app()).get("/unavailable").status_code == 503

    assert sent.events == []


# --- the redaction net ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+919876543210", "[phone]"),
        ("call 98765 43210 now", "call [phone] now"),
        ("91-9876543210", "[phone]"),
        ("mail priya@example.in", "mail [email]"),
        ("pay priya@okaxis", "pay [email]"),
        ("account 001234567890123", "account [number]"),
        ("postgresql://app:hunter2@db.internal/app", "postgresql://app:[email]/app"),
    ],
)
def test_personal_data_is_replaced(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        REQUEST_ID_LIKE,
        "request.unhandled_error request_id=" + REQUEST_ID_LIKE,
        "deal DM-1234 at 2026-10-04T10:15:30.123456Z",
        "₹8000 for 3 reels",
        "a1b2c3d4e5f60718293a4b5c6d7e8f90",  # an event ID
    ],
)
def test_ids_dates_and_amounts_are_kept(text):
    assert redact(text) == text


def test_redaction_reaches_nested_values():
    event = {"extra": {"rows": [{"phone": PHONE}, ("keep", "98765 43210")]}, "level": 40}

    assert redact(event) == {
        "extra": {"rows": [{"phone": "[phone]"}, ["keep", "[phone]"]]},
        "level": 40,
    }
