"""Login codes by WhatsApp through MSG91 (D-058), against a fake MSG91.

Nothing here reaches the real service: every request is answered by an
httpx2 MockTransport, so the tests pin down what we send and how we react to
each kind of answer, including the ones that must not be retried.
"""

import json
import logging

import httpx2
import pytest

from app.core.config import settings
from app.modules.auth import sender as sender_module
from app.modules.auth.msg91_sender import (
    API_URL,
    MAX_ATTEMPTS,
    TIMEOUT,
    Msg91WhatsAppSender,
    OtpDeliveryFailed,
)
from app.modules.auth.sender import OtpSenderNotConfigured, get_otp_sender

PHONE = "+919876543210"
CODE = "482915"
KEY = "test-auth-key-not-real"


class FakeMsg91:
    """Answers each request with the next queued reply, and keeps what it got."""

    def __init__(self, *replies: httpx2.Response | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_sender(
    fake: FakeMsg91, sleeps: list[float] | None = None
) -> Msg91WhatsAppSender:
    recorded = sleeps if sleeps is not None else []
    return Msg91WhatsAppSender(
        auth_key=KEY,
        integrated_number="919000000001",
        template="login_code",
        language="en",
        client=httpx2.Client(transport=httpx2.MockTransport(fake)),
        sleep=recorded.append,
        jitter=lambda: 0.5,  # the middle of the jitter range, so delays are exact
    )


def ok(body: dict | None = None) -> httpx2.Response:
    return httpx2.Response(200, json=body or {"status": "success", "hasError": False})


# --- what we send -----------------------------------------------------------------


def test_the_code_goes_in_the_body_and_the_copy_code_button():
    fake = FakeMsg91(ok())

    make_sender(fake).send_code(PHONE, CODE)

    [request] = fake.requests
    assert str(request.url) == API_URL
    assert request.method == "POST"
    assert request.headers["authkey"] == KEY
    body = json.loads(request.content)
    assert body["integrated_number"] == "919000000001"
    assert body["content_type"] == "template"
    template = body["payload"]["template"]
    assert template["name"] == "login_code"
    assert template["language"] == {"code": "en", "policy": "deterministic"}
    [recipient] = template["to_and_components"]
    assert recipient["to"] == ["919876543210"]  # digits, no plus, as MSG91 writes them
    assert recipient["components"]["body_1"]["value"] == CODE
    assert recipient["components"]["button_1"]["value"] == CODE


def test_timeouts_are_the_ones_the_standard_sets():
    """backend.md section 6: connect 3 s, read 10 s."""
    assert TIMEOUT.connect == 3.0
    assert TIMEOUT.read == 10.0


# --- retrying only where it can help ----------------------------------------------


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_busy_or_failing_service_is_retried(status):
    fake = FakeMsg91(httpx2.Response(status), ok())
    sleeps: list[float] = []

    make_sender(fake, sleeps).send_code(PHONE, CODE)

    assert len(fake.requests) == 2
    assert sleeps == [0.5]  # 0.5 s, scaled by the jitter's middle value


def test_a_network_failure_is_retried():
    fake = FakeMsg91(httpx2.ConnectError("unreachable"), ok())

    make_sender(fake).send_code(PHONE, CODE)

    assert len(fake.requests) == 2


def test_it_gives_up_after_three_attempts_with_growing_waits():
    fake = FakeMsg91(*[httpx2.Response(503)] * MAX_ATTEMPTS)
    sleeps: list[float] = []

    with pytest.raises(OtpDeliveryFailed, match="after 3 attempts"):
        make_sender(fake, sleeps).send_code(PHONE, CODE)

    assert len(fake.requests) == 3
    assert sleeps == [0.5, 1.0]  # no wait after the last attempt


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_a_request_msg91_refuses_is_not_retried(status):
    """Sending a wrong request again would only repeat it."""
    fake = FakeMsg91(httpx2.Response(status))

    with pytest.raises(OtpDeliveryFailed, match=f"status {status}"):
        make_sender(fake).send_code(PHONE, CODE)

    assert len(fake.requests) == 1


def test_a_success_status_that_reports_an_error_is_a_failure():
    fake = FakeMsg91(
        ok({"status": "fail", "hasError": True, "errors": "template not approved"})
    )

    with pytest.raises(OtpDeliveryFailed):
        make_sender(fake).send_code(PHONE, CODE)

    assert len(fake.requests) == 1


# --- nothing leaks ------------------------------------------------------------------


@pytest.mark.parametrize(
    "replies",
    [
        [httpx2.Response(400, json={"errors": f"bad number {PHONE} code {CODE}"})],
        [httpx2.Response(503, text=f"{PHONE} {CODE}")] * MAX_ATTEMPTS,
        [httpx2.ConnectError(f"cannot reach, was sending {CODE} to {PHONE}")]
        * MAX_ATTEMPTS,
    ],
    ids=["refused", "unavailable", "unreachable"],
)
def test_no_failure_ever_carries_the_phone_or_code(caplog, replies):
    """Provider replies and network errors can echo either; neither may reach
    a log line or an error message (backend.md section 9)."""
    caplog.set_level(logging.DEBUG)

    with pytest.raises(OtpDeliveryFailed) as exc_info:
        make_sender(FakeMsg91(*replies)).send_code(PHONE, CODE)

    for text in (str(exc_info.value), caplog.text):
        assert CODE not in text
        assert PHONE.removeprefix("+") not in text
        assert PHONE[-4:] not in text


# --- which sender the app uses ------------------------------------------------------


@pytest.fixture
def msg91_configured(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "otp_sender", "msg91")
    monkeypatch.setattr(settings, "msg91_auth_key", SecretStr(KEY))
    monkeypatch.setattr(settings, "msg91_whatsapp_number", "919000000001")
    sender_module._msg91_sender.cache_clear()
    yield
    sender_module._msg91_sender.cache_clear()


@pytest.mark.parametrize("environment", ["local", "staging", "production"])
def test_msg91_is_used_wherever_it_is_configured(
    monkeypatch, msg91_configured, environment
):
    monkeypatch.setattr(settings, "environment", environment)

    assert isinstance(get_otp_sender(), Msg91WhatsAppSender)


def test_one_msg91_sender_is_shared_so_connections_are_reused(msg91_configured):
    assert get_otp_sender() is get_otp_sender()


def test_msg91_without_its_settings_refuses_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(settings, "otp_sender", "msg91")
    monkeypatch.setattr(settings, "msg91_auth_key", None)
    sender_module._msg91_sender.cache_clear()
    try:
        with pytest.raises(OtpSenderNotConfigured):
            get_otp_sender()
    finally:
        sender_module._msg91_sender.cache_clear()
