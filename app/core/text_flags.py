"""Warnings on free text one person sends another (item 60).

docs/standards/trust-and-safety.md section 4. Two scams start in text:

- **A request for money from a creator.** "Pay ₹2,000 registration to
  confirm your slot" is how fake brands work. A creator never pays to get a
  deal on this platform, so such text gets a warning beside it.
- **Contact details before a deal is agreed.** A phone number, an email, a
  UPI ID or a WhatsApp or Telegram link pulls the conversation off the
  record, which is where scams happen. Flagged, not hidden (D-086).

Flags are **warnings, never blocks or rewrites**: the text is shown as sent,
with the flag next to it, and the person who wrote it sees the same flag
before anyone else does. They are worked out on every read, never stored, so
a better rule applies to old text too (backend.md section 2).

The line that matters is between a scam and ordinary business. "We pay
₹5,000 per reel" is a brand paying a creator, the whole point, and must not
be flagged; the money patterns look for **someone asking to be paid** a fee,
deposit or charge. Every pattern has tests with real wording, including the
ones that must not match.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

TextFlag = Literal["asks_for_money", "phone_number", "email", "upi_id", "messaging_link"]
TEXT_FLAGS: tuple[str, ...] = (
    "asks_for_money",
    "phone_number",
    "email",
    "upi_id",
    "messaging_link",
)
CONTACT_FLAGS: tuple[str, ...] = ("phone_number", "email", "upi_id", "messaging_link")

_MONEY = r"(?:₹|rs\.?|inr|rupees?)\s*\d"
_ASKS_FOR_MONEY = re.compile(
    "|".join(
        (
            r"\bregistration\s+(?:fee|charge|charges|amount|cost)",
            r"\b(?:security|refundable|caution|booking)\s+(?:deposit|amount)",
            r"\b(?:processing|joining|onboarding|verification|listing|membership|"
            r"enrol?ment|activation|application)\s+(?:fee|fees|charge|charges)",
            r"\bpay\s+(?:the\s+)?(?:shipping|courier|delivery|handling)\s+(?:fee|charge|charges|cost)",
            r"\b(?:shipping|courier|delivery|handling)\s+(?:fee|charge|charges)\s+of\s+"
            + _MONEY,
            r"\bpay\s+(?:us\s+)?(?:first|upfront|up\s+front|in\s+advance)\b",
            r"\b(?:send|transfer)\s+" + _MONEY,
            r"\bpay\s+" + _MONEY + r"[\d,]*\s+(?:to|for)\s+(?:register|join|confirm|book|"
            r"secure|activate|verify|unlock|get)",
            r"\brefund(?:ed|able)?\s+(?:after|once|when)\b",
        )
    ),
    re.IGNORECASE,
)
# An Indian mobile, with or without +91 and spaces or dashes.
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_EMAIL = re.compile(r"\b[\w.+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+\b", re.IGNORECASE)
# A UPI ID: name@handle (okaxis, ybl). An email looks the same up to its dot,
# so emails are taken out of the text before this is searched.
_UPI = re.compile(r"\b[\w.-]{2,}@[a-z][a-z0-9]{1,63}\b", re.IGNORECASE)
_MESSAGING = re.compile(
    r"\b(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com|t\.me|telegram\.me|"
    r"whats\s?app\s+(?:me|us|number|no)|telegram\s+(?:me|us|id))\b",
    re.IGNORECASE,
)


def flags_in(text: str | None, *, money: bool, contact: bool) -> list[TextFlag]:
    """The flags this text raises, in a fixed order.

    `money`: the reader is a creator, who must never be asked to pay.
    `contact`: no deal is agreed yet, so contact details would take the
    talk off the record.
    """
    if not text:
        return []
    found: list[TextFlag] = []
    if money and _ASKS_FOR_MONEY.search(text):
        found.append("asks_for_money")
    if contact:
        if _PHONE.search(text):
            found.append("phone_number")
        if _EMAIL.search(text):
            found.append("email")
        if _UPI.search(_EMAIL.sub(" ", text)):
            found.append("upi_id")
        if _MESSAGING.search(text):
            found.append("messaging_link")
    return found


class FieldFlag(BaseModel):
    """One warning on one field, for the app to show beside that text."""

    field: str
    flag: TextFlag = Field(
        description=(
            "asks_for_money: someone is asked to pay a fee or deposit, which never "
            "happens here; phone_number, email, upi_id, messaging_link: contact "
            "details before a deal is agreed. Clients must tolerate new values"
        )
    )


def field_flags(
    fields: dict[str, str | None], *, money: bool, contact: bool
) -> list[FieldFlag]:
    """Every flag on every field given, field by field in the order given."""
    return [
        FieldFlag(field=name, flag=flag)
        for name, text in fields.items()
        for flag in flags_in(text, money=money, contact=contact)
    ]
