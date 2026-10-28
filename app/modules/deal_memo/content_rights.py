"""Where a post's usage window stands (item 70, D-132). Pure.

The window is the days the accepted memo states (`usage_rights_days`),
counted from the Tamil Nadu day the work was approved. What those days
mean in law is a Confirm item (legal.md section 3.11); this only counts.
"""

from datetime import date, datetime, timedelta
from typing import Literal

from app.core.clock import india_date

RightsState = Literal["active", "lapsing", "lapsed", "not_agreed"]
RIGHTS_STATES: tuple[RightsState, ...] = ("active", "lapsing", "lapsed", "not_agreed")
# A window ending within this many days reads `lapsing`.
LAPSING_WITHIN_DAYS = 30


def rights_until(approved_at: datetime, usage_rights_days: int | None) -> date | None:
    """The day the agreed window ends: the approval's Tamil Nadu day plus the days."""
    if usage_rights_days is None:
        return None
    return india_date(approved_at) + timedelta(days=usage_rights_days)


def rights_state(until: date | None, today: date) -> RightsState:
    """Where a window stands on `today`. Pure."""
    if until is None:
        return "not_agreed"
    if until <= today:
        return "lapsed"
    if until <= today + timedelta(days=LAPSING_WITHIN_DAYS):
        return "lapsing"
    return "active"
