import logging

import pytest

from app.core.config import settings
from app.modules.auth.sender import (
    FakeOtpSender,
    OtpSenderNotConfigured,
    get_otp_sender,
)
from tests.factories import fake_phone


def test_fake_sender_records_codes_per_phone():
    sender = FakeOtpSender()
    first_phone, second_phone = fake_phone(), fake_phone()

    sender.send_code(first_phone, "111111")
    sender.send_code(second_phone, "222222")
    sender.send_code(first_phone, "333333")

    assert sender.last_code_for(first_phone) == "333333"
    assert sender.last_code_for(second_phone) == "222222"
    assert len(sender.sent) == 3


def test_fake_sender_returns_none_for_unknown_phone():
    assert FakeOtpSender().last_code_for(fake_phone()) is None


def test_fake_sender_clear_forgets_everything():
    sender = FakeOtpSender()
    phone = fake_phone()
    sender.send_code(phone, "111111")

    sender.clear()

    assert sender.sent == []
    assert sender.last_code_for(phone) is None


def test_fake_sender_never_logs_the_code_or_phone(caplog):
    sender = FakeOtpSender()
    phone = fake_phone()

    with caplog.at_level(logging.DEBUG):
        sender.send_code(phone, "987654")

    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "987654" not in logged
    assert phone not in logged
    assert phone[-4:] not in logged


@pytest.mark.parametrize("environment", ["local", "test"])
def test_fake_sender_is_used_in_local_and_test(monkeypatch, environment):
    monkeypatch.setattr(settings, "environment", environment)

    assert isinstance(get_otp_sender(), FakeOtpSender)


@pytest.mark.parametrize("environment", ["staging", "production", ""])
def test_no_sender_outside_local_and_test(monkeypatch, environment):
    monkeypatch.setattr(settings, "environment", environment)

    with pytest.raises(OtpSenderNotConfigured):
        get_otp_sender()
