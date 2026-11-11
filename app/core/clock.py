"""What day it is, for people in Tamil Nadu (D-030 point 1).

Every deadline in this product is a date somebody experiences: the day a
payment is due, the day a dispute stops waiting. Read on the server's clock,
a deadline set at 23:00 UTC would already have moved on for the person
relying on it, taking a day off their notice without anyone deciding to.

A fixed offset rather than a named zone: India has no daylight saving, so
+05:30 is always correct, and it needs no timezone database on the machine.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def india_date(moment: datetime) -> date:
    """The calendar date this moment falls on in Tamil Nadu."""
    return moment.astimezone(IST).date()


def end_of_india_day(day: date) -> datetime:
    """The first moment after `day` in Tamil Nadu, in UTC: midnight there.

    A half-open end, as Google's API guidance gives an instant rather than a
    date for a deadline (AIP-142): something open "until `day`" is open while
    `now < end_of_india_day(day)`, with no last second to argue over.
    """
    return datetime.combine(day + timedelta(days=1), time(0), IST).astimezone(UTC)
