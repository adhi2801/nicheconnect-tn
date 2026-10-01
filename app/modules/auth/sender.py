"""How one-time codes reach a phone (D-013, D-058).

Everything sends through the OtpSender interface. `OTP_SENDER` chooses the
implementation: "msg91" sends by WhatsApp through MSG91, in any environment;
"fake" keeps codes in memory and refuses to run outside local and test.
Codes and phone numbers are never logged (backend.md section 9).
"""

import logging
from dataclasses import dataclass
from functools import cache
from typing import Protocol

from app.core.config import settings
from app.modules.auth.msg91_sender import Msg91WhatsAppSender

logger = logging.getLogger(__name__)

FAKE_SENDER_ENVIRONMENTS = frozenset({"local", "test"})


class OtpSender(Protocol):
    def send_code(self, phone: str, code: str) -> None:
        """Deliver `code` to `phone`. Raise on failure."""
        ...


@dataclass(frozen=True)
class SentCode:
    phone: str
    code: str


class FakeOtpSender:
    """Keeps sent codes in memory instead of sending them. Never for real users."""

    def __init__(self) -> None:
        self.sent: list[SentCode] = []

    def send_code(self, phone: str, code: str) -> None:
        self.sent.append(SentCode(phone=phone, code=code))
        logger.info("otp.fake_sent count=%d", len(self.sent))

    def last_code_for(self, phone: str) -> str | None:
        """The most recent code 'sent' to `phone`, for tests."""
        for sent in reversed(self.sent):
            if sent.phone == phone:
                return sent.code
        return None

    def clear(self) -> None:
        self.sent.clear()


class OtpSenderNotConfigured(RuntimeError):
    """Raised when no real provider exists for this environment."""


_fake_sender = FakeOtpSender()


@cache
def _msg91_sender() -> Msg91WhatsAppSender:
    """One sender for the process, so its HTTP connections are reused.

    The settings are checked at startup, so this refusal should never be
    reached; it exists so the types say so rather than an assert.
    """
    if settings.msg91_auth_key is None or settings.msg91_whatsapp_number is None:
        raise OtpSenderNotConfigured("otp_sender is msg91 but MSG91 is not configured")
    return Msg91WhatsAppSender(
        auth_key=settings.msg91_auth_key.get_secret_value(),
        integrated_number=settings.msg91_whatsapp_number,
        template=settings.msg91_otp_template,
        language=settings.msg91_template_language,
    )


def get_otp_sender() -> OtpSender:
    """FastAPI dependency: the sender this deployment is configured for.

    The fake fails loudly in staging or production, so it can never silently
    swallow real users' codes.
    """
    if settings.otp_sender == "msg91":
        return _msg91_sender()
    if settings.environment not in FAKE_SENDER_ENVIRONMENTS:
        raise OtpSenderNotConfigured(
            f"no OTP provider configured for environment '{settings.environment}'"
        )
    return _fake_sender
