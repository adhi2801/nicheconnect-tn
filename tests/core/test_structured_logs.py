"""Log lines as JSON, with no personal data (D-102).

Each test formats a real log record and reads the line exactly as it would
be written to CloudWatch.
"""

import json
import logging
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st
from opentelemetry.sdk.trace import TracerProvider

from app.core.request_id import request_id_var
from app.core.structured_logs import (
    ACCESS_LOGGER,
    UVICORN_LOGGERS,
    JsonFormatter,
    configure_logging,
)

FORMATTER = JsonFormatter()


def record(
    message: str, *args, name: str = "app.test", exc_info=None
) -> logging.LogRecord:
    return logging.LogRecord(name, logging.WARNING, __file__, 1, message, args, exc_info)


def line(rec: logging.LogRecord) -> dict:
    text = FORMATTER.format(rec)
    assert "\n" not in text  # one event, one line
    return json.loads(text)


def test_a_line_has_every_field_and_nothing_else():
    got = line(record("campaign.created campaign_id=%s", "c-1"))

    assert set(got) == {"time", "level", "logger", "event", "request_id", "trace_id"}
    assert got["event"] == "campaign.created campaign_id=c-1"
    assert (got["level"], got["logger"]) == ("WARNING", "app.test")
    assert got["time"].endswith("+00:00")


def test_the_request_id_of_the_request_is_on_its_lines():
    token = request_id_var.set("req-123")
    try:
        assert line(record("x"))["request_id"] == "req-123"
    finally:
        request_id_var.reset(token)


def test_a_line_inside_a_trace_names_the_trace():
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("request") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        assert line(record("x"))["trace_id"] == expected
    assert line(record("x"))["trace_id"] is None


@pytest.mark.parametrize(
    "value",
    [
        "9876543210",
        "+91 98765 43210",
        "987 654 3210",
        "priya@example.com",
        "priya.reels@okaxis",
    ],
)
def test_personal_data_in_an_event_is_redacted(value):
    got = line(record("otp.send_failed to=%s", value))

    assert value not in json.dumps(got)


@given(st.from_regex(r"[6-9]\d{9}", fullmatch=True))
def test_no_mobile_number_survives_in_any_line(number):
    assert number not in json.dumps(line(record("lookup phone=%s", number)))


def test_an_exception_logs_its_type_and_place_never_its_message():
    try:
        raise ValueError("row (+919876543210, priya@example.com) refused")
    except ValueError:
        got = line(record("request.unhandled_error", exc_info=sys.exc_info()))

    assert got["exception"]["type"] == "ValueError"
    assert "test_structured_logs.py" in got["exception"]["stack"]
    assert "9876543210" not in json.dumps(got)
    assert "priya" not in json.dumps(got)


def test_an_access_line_keeps_no_address_and_no_query():
    access = record(
        '%s - "%s %s HTTP/%s" %d',
        "203.0.113.7:51234",
        "GET",
        "/api/v1/creators?q=priya&city=Madurai",
        "1.1",
        200,
        name=ACCESS_LOGGER,
    )

    got = line(access)

    assert got["event"] == "http.request method=GET path=/api/v1/creators status=200"
    assert "203.0.113.7" not in json.dumps(got)
    assert "priya" not in json.dumps(got)


@pytest.fixture
def clean_logging():
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    uvicorn = {
        n: (logging.getLogger(n).handlers[:], logging.getLogger(n).propagate)
        for n in UVICORN_LOGGERS
    }
    yield
    root.handlers, root.level = saved[0], saved[1]
    for name, (handlers, propagate) in uvicorn.items():
        logging.getLogger(name).handlers = handlers
        logging.getLogger(name).propagate = propagate


def test_json_mode_sends_every_line_through_one_json_handler(clean_logging):
    logging.getLogger(ACCESS_LOGGER).handlers = [logging.NullHandler()]

    configure_logging("json")

    [handler] = logging.getLogger().handlers
    assert isinstance(handler.formatter, JsonFormatter)
    for name in UVICORN_LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True


def test_text_mode_changes_nothing(clean_logging):
    before = logging.getLogger().handlers[:]

    configure_logging("text")

    assert logging.getLogger().handlers == before
