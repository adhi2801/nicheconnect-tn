"""How one-time codes reach a phone (D-013).

Everything sends through the OtpSender interface. Until a real provider is
decided, only the fake exists, and it refuses to run outside local/test.
Codes and phone numbers are never logged (backend.md section 9).
"""

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings

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


def get_otp_sender() -> OtpSender:
    """FastAPI dependency: the sender for this environment.

    Fails loudly in staging or production until a real provider is chosen,
    so the fake can never silently swallow real users' codes.
    """
    if settings.environment not in FAKE_SENDER_ENVIRONMENTS:
        raise OtpSenderNotConfigured(
            f"no OTP provider configured for environment '{settings.environment}'"
        )
    return _fake_sender
