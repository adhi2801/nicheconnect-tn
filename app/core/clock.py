"""What day it is, for people in Tamil Nadu (D-030 point 1).

Every deadline in this product is a date somebody experiences: the day a
payment is due, the day a dispute stops waiting. Read on the server's clock,
a deadline set at 23:00 UTC would already have moved on for the person
relying on it, taking a day off their notice without anyone deciding to.

A fixed offset rather than a named zone: India has no daylight saving, so
+05:30 is always correct, and it needs no timezone database on the machine.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

from sqlalchemy import Date, SQLColumnExpression, cast, func
from sqlalchemy.sql.elements import ColumnElement

IST_OFFSET = timedelta(hours=5, minutes=30)
IST = timezone(IST_OFFSET)


def india_date(moment: datetime) -> date:
    """The calendar date this moment falls on in Tamil Nadu."""
    return moment.astimezone(IST).date()


def india_date_sql(moment: SQLColumnExpression[datetime | None]) -> ColumnElement[date]:
    """`india_date` in SQL, for a `timestamptz` column: whatever the session's
    TimeZone, since the moment is put in Tamil Nadu's zone before its date is
    taken. Adding five and a half hours and casting was right only while the
    session ran in UTC (the independent review of audit C11)."""
    return cast(func.timezone("Asia/Kolkata", moment), Date)


def end_of_india_day(day: date) -> datetime:
    """The first moment after `day` in Tamil Nadu, in UTC: midnight there.

    A half-open end, as Google's API guidance gives an instant rather than a
    date for a deadline (AIP-142): something open "until `day`" is open while
    `now < end_of_india_day(day)`, with no last second to argue over.

    Worked out in UTC on the day itself, so it holds for every date Python
    has: adding the day first overflowed on 31 December 9999, and a campaign
    holding that date answered 500 on every read (the independent review of
    audit C11). IST's offset is fixed, so this is the same instant.
    """
    return datetime.combine(day, time(0), UTC) + (timedelta(days=1) - IST_OFFSET)
