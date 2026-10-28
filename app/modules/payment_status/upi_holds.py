"""Which UPI ID brands are shown, and which is still waiting (item 82, D-107).

Pure rules over the two rows, against an injected `now`, so they are tested
without a database and the answer is never a stored copy that can drift
(backend.md section 2). See `upi_change_models` for why a new ID waits.
"""

from dataclasses import dataclass
from datetime import datetime

from app.modules.payment_status.upi_change_models import CreatorUpiChange
from app.modules.payment_status.upi_models import CreatorUpi


@dataclass(frozen=True)
class UpiInEffect:
    """The ID brands are shown now, the consent it was given under, and since when."""

    upi_id: str
    consented_at: datetime
    notice_version: str
    # When brands began to be shown it: when it was set, or when its wait ended.
    set_at: datetime


@dataclass(frozen=True)
class UpiWaiting:
    """A new ID the creator asked for, not yet shown to brands."""

    upi_id: str
    consented_at: datetime
    notice_version: str
    usable_at: datetime


def in_effect(
    current: CreatorUpi | None, change: CreatorUpiChange | None, now: datetime
) -> UpiInEffect | None:
    """The ID brands are shown: a change whose wait is over, else the current one."""
    if change is not None and now >= change.usable_at:
        return UpiInEffect(
            upi_id=change.upi_id,
            consented_at=change.consented_at,
            notice_version=change.notice_version,
            set_at=change.usable_at,
        )
    if current is None:
        return None
    return UpiInEffect(
        upi_id=current.upi_id,
        consented_at=current.consented_at,
        notice_version=current.notice_version,
        set_at=current.updated_at,
    )


def waiting(change: CreatorUpiChange | None, now: datetime) -> UpiWaiting | None:
    """The change still waiting, or None when there is none or its wait is over."""
    if change is None or now >= change.usable_at:
        return None
    return UpiWaiting(
        upi_id=change.upi_id,
        consented_at=change.consented_at,
        notice_version=change.notice_version,
        usable_at=change.usable_at,
    )
