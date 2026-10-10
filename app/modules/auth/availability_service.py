"""A creator's availability: "booked until 20 Nov" (D-083).

One date, the last Tamil Nadu day the creator is not taking new work.
Signed-in brands see it in search and in a campaign's suggested creators, so
fewer applications and invitations go nowhere on either side. It is **not**
on the public Passport: creators published that page before this existed,
and their consent covered what it showed then (D-036).

**Worked out, never stored.** A date that has passed means "taking work", and
every read says so through `booked_until_shown`; nothing has to clear it at
midnight. The creator's own setting is kept as they gave it, and is in their
data export.

**Nothing blocks.** A booked creator can still apply, and a brand can still
contact them: availability informs, it never decides (the same line as D-024).
"""

from datetime import date, timedelta

from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import Session

from app.modules.auth.exceptions import InvalidAvailability
from app.modules.auth.models.creator import Creator

# A year: anything further ahead is almost certainly a mistyped year.
FURTHEST_AHEAD = timedelta(days=365)


def booked_until_shown(booked_until: date | None, today: date) -> date | None:
    """The date to show, or None when the creator is taking work today."""
    if booked_until is None or booked_until < today:
        return None
    return booked_until


def available_from(booked_until: date | None, today: date) -> date:
    """The first Tamil Nadu day the creator is taking work."""
    shown = booked_until_shown(booked_until, today)
    return today if shown is None else shown + timedelta(days=1)


def free_on(day: date) -> ColumnElement[bool]:
    """A filter: creators not booked on `day`."""
    return or_(Creator.booked_until.is_(None), Creator.booked_until < day)


def set_booked_until(
    db: Session, creator: Creator, booked_until: date | None, *, today: date
) -> Creator:
    """Set or clear the date. Raises InvalidAvailability outside today..a year.

    Clearing (None) is always allowed. Replacing the whole value makes a
    retry or two saves at once harmless: the last one wins, and both meant it.
    """
    if booked_until is not None:
        if booked_until < today:
            raise InvalidAvailability(
                "Choose today or a later date, or clear it if you are taking work."
            )
        if booked_until > today + FURTHEST_AHEAD:
            raise InvalidAvailability(
                "Choose a date within a year from today; check the year."
            )
    creator.booked_until = booked_until
    db.commit()
    db.refresh(creator)
    return creator
