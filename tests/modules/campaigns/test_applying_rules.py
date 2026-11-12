"""The one rule for joining a campaign, without a database (D-180).

Pure rules get pure tests (testing.md section 3): every branch here, each
mutation of it caught. The review of audit C11 found the status branch
untested, so deleting it survived.
"""

from datetime import UTC, date, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import india_date
from app.modules.campaigns.applying import applications_open
from app.modules.campaigns.models import CAMPAIGN_STATUSES

CLOSE_ON = date(2026, 9, 20)


@pytest.mark.parametrize("status", [s for s in CAMPAIGN_STATUSES if s != "open"])
def test_only_an_open_campaign_takes_creators_whatever_its_date(status):
    now = datetime(2026, 9, 1, tzinfo=UTC)

    assert applications_open(status, None, now) is False
    assert applications_open(status, CLOSE_ON, now) is False


def test_an_open_campaign_with_no_closing_date_takes_creators():
    assert applications_open("open", None, datetime(2030, 1, 1, tzinfo=UTC)) is True


@pytest.mark.parametrize(
    ("moment", "is_open"),
    [
        (datetime(2026, 9, 20, 18, 29, 59, 999_999, tzinfo=UTC), True),
        (datetime(2026, 9, 20, 18, 30, tzinfo=UTC), False),
        (datetime(2026, 9, 20, 20, 0, tzinfo=UTC), False),  # still the 20th in UTC
    ],
)
def test_the_closing_day_ends_at_midnight_in_tamil_nadu(moment, is_open):
    assert applications_open("open", CLOSE_ON, moment) is is_open


# Hypothesis takes naive bounds and attaches the zone itself.
moments = st.datetimes(
    min_value=datetime(2026, 1, 1),  # noqa: DTZ001
    max_value=datetime(2030, 12, 31),  # noqa: DTZ001
    timezones=st.just(UTC),
)
days = st.dates(min_value=date(2026, 1, 1), max_value=date(2030, 12, 31))


@given(moment=moments, close_on=days)
def test_open_exactly_while_the_tamil_nadu_day_is_not_after_the_closing_date(
    moment, close_on
):
    assert applications_open("open", close_on, moment) == (india_date(moment) <= close_on)
