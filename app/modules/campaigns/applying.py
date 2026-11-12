"""Whether a campaign takes creators: the one rule, in Python and in SQL (D-180).

A campaign takes applications, invitations and the acceptance of an
invitation while it is open and its Tamil Nadu closing day has not ended
(Adhi, 11 November 2026: the date closes everything). A brand may still
decide on the applications it has after that day, and both sides may still
negotiate an application already made: neither is a creator joining. An
invitation not yet accepted is not in, so its counter-offers stop with the
day too.

Every place that asks the question asks it here: applying, inviting,
accepting an invitation, a counter-offer on one, every campaign's answer,
discovery, matching, alerts, feedback, the attention list and city figures.
Until audit C11 four of them each carried their own copy, and two (applying
and matching) compared the UTC date.
"""

from datetime import date, datetime

from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import Session

from app.core.clock import end_of_india_day
from app.modules.campaigns.models import Campaign


def applications_open(status: str, close_on: date | None, now: datetime) -> bool:
    """Whether a creator may join at `now`: open, and before the first moment
    of the day after `close_on` in Tamil Nadu."""
    if status != "open":
        return False
    return close_on is None or now < end_of_india_day(close_on)


def taking_creators(today: date) -> ColumnElement[bool]:
    """The same rule as a query condition, for a Tamil Nadu `today`."""
    return and_(
        Campaign.status == "open",
        or_(
            Campaign.applications_close_on.is_(None),
            Campaign.applications_close_on >= today,
        ),
    )


def lock_for_joining(db: Session, campaign: Campaign) -> None:
    """Share-lock the campaign and read its rule's columns again.

    Creators joining at once never wait on each other; a brand closing or
    changing the campaign (which locks it for update) waits for them, or
    they for it, so nobody joins a campaign closed a moment before.
    """
    db.refresh(
        campaign,
        attribute_names=["status", "applications_close_on"],
        with_for_update={"read": True},
    )
