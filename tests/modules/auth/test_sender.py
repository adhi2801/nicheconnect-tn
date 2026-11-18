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


def msg91_on(monkeypatch, template: str | None) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "otp_sender", "msg91")
    monkeypatch.setattr(settings, "msg91_auth_key", SecretStr("test-key-not-a-secret"))
    monkeypatch.setattr(settings, "msg91_whatsapp_number", "919000000001")
    monkeypatch.setattr(settings, "msg91_direct_offer_template", template)


def test_a_direct_offer_s_code_goes_on_its_own_template(monkeypatch):
    """D-189: never the login template, which says nothing about the offer."""
    from app.modules.auth.sender import direct_offer_code_sender

    msg91_on(monkeypatch, "direct_offer_code")

    sender = direct_offer_code_sender(FakeOtpSender())

    assert sender._template == "direct_offer_code"  # type: ignore[attr-defined]
    assert sender._template != settings.msg91_otp_template  # type: ignore[attr-defined]


def test_without_its_template_a_direct_offer_s_code_is_never_sent(monkeypatch):
    from app.modules.auth.sender import direct_offer_code_sender

    msg91_on(monkeypatch, None)
    login = FakeOtpSender()

    with pytest.raises(OtpSenderNotConfigured):
        direct_offer_code_sender(login).send_code(fake_phone(), "123456")
    assert login.sent == []


def test_locally_a_direct_offer_s_code_is_kept_by_login_s_fake(monkeypatch):
    from app.modules.auth.sender import direct_offer_code_sender

    monkeypatch.setattr(settings, "otp_sender", "fake")
    login = FakeOtpSender()

    assert direct_offer_code_sender(login) is login
