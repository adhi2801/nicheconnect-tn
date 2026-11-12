"""`india_date_sql`: the Tamil Nadu day of a moment, in SQL, whatever the
session's TimeZone (the independent review of audit C11).

The content library once added five and a half hours to the moment and cast
it to a date: right while the session ran in UTC, a day out either side of
midnight on a server set to anything else.
"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import DateTime, literal, select, text

from app.core.clock import india_date_sql


@pytest.mark.parametrize("zone", ["UTC", "Asia/Kolkata", "America/New_York"])
@pytest.mark.parametrize(
    ("moment", "day"),
    [
        (datetime(2026, 9, 20, 18, 29, 59, tzinfo=UTC), date(2026, 9, 20)),
        (datetime(2026, 9, 20, 18, 30, tzinfo=UTC), date(2026, 9, 21)),
        (datetime(2026, 9, 20, 0, 0, tzinfo=UTC), date(2026, 9, 20)),
    ],
)
def test_the_day_is_tamil_nadus_whatever_the_sessions_zone(db, zone, moment, day):
    db.execute(text(f"SET LOCAL TimeZone = '{zone}'"))

    found = db.scalar(select(india_date_sql(literal(moment, DateTime(timezone=True)))))

    assert found == day
