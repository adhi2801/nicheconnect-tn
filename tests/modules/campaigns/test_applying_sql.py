"""`taking_creators`, the SQL half of the one rule, agrees with the Python
half for every status, closing date and moment (D-180).

Discovery, matching, alerts and city figures filter with the SQL; a
campaign's own answer and every joining write ask the Python. The
independent review of audit C11 found nothing tied the two, so a change to
one would leave lists and answers disagreeing about the same campaign.
"""

from datetime import UTC, date, datetime

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select

from app.core.clock import india_date
from app.modules.campaigns.applying import applications_open, taking_creators
from app.modules.campaigns.models import CAMPAIGN_STATUSES, Campaign
from tests.factories import build_campaign

# Hypothesis takes naive bounds and attaches the zone itself.
moments = st.datetimes(
    min_value=datetime(2026, 1, 1),  # noqa: DTZ001
    max_value=datetime(2027, 12, 31),  # noqa: DTZ001
    timezones=st.just(UTC),
)
closing_days = st.none() | st.dates(
    min_value=date(2026, 1, 1), max_value=date(2027, 12, 31)
)


def listed(db, campaign: Campaign, now: datetime) -> bool:
    found = db.scalar(
        select(Campaign.id).where(
            Campaign.id == campaign.id, taking_creators(india_date(now))
        )
    )
    return found is not None


@settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(status=st.sampled_from(CAMPAIGN_STATUSES), close_on=closing_days, now=moments)
def test_the_sql_lists_a_campaign_exactly_when_python_says_it_is_open(
    db, status, close_on, now
):
    campaign = build_campaign(db, status=status, applications_close_on=close_on)
    db.add(campaign)
    db.flush()

    assert listed(db, campaign, now) == applications_open(status, close_on, now)


def test_both_halves_agree_either_side_of_tamil_nadu_midnight(db):
    """The boundary itself, named, so a failure reads plainly."""
    campaign = build_campaign(db, applications_close_on=date(2026, 9, 20))
    db.add(campaign)
    db.flush()
    last_moment = datetime(2026, 9, 20, 18, 29, 59, 999_999, tzinfo=UTC)
    midnight = datetime(2026, 9, 20, 18, 30, tzinfo=UTC)

    assert listed(db, campaign, last_moment) is True
    assert listed(db, campaign, midnight) is False
