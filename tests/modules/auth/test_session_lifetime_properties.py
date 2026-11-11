"""What holds for every login time and every refresh (item 144, D-174)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.core.config import settings
from app.modules.auth.login_age import ESTABLISHED_LOGIN, LOST_NUMBER_LOGIN
from app.modules.auth.models.auth_session import (
    MEMBER_SESSION_LIMIT,
    refresh_token_expiry,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
seconds_in = st.integers(min_value=0, max_value=60 * 24 * 3600)
roles = st.sampled_from(["brand", "creator"])


@given(role=roles, logged_in=seconds_in, since=seconds_in)
def test_a_refresh_never_reaches_past_thirty_days_from_the_login(role, logged_in, since):
    login = START + timedelta(seconds=logged_in)
    now = login + timedelta(seconds=since)

    expiry = refresh_token_expiry(role, now, None, login)

    assert expiry <= login + MEMBER_SESSION_LIMIT
    assert expiry <= now + timedelta(days=settings.refresh_token_expire_days)
    assert expiry == min(
        login + MEMBER_SESSION_LIMIT,
        now + timedelta(days=settings.refresh_token_expire_days),
    )


@given(role=roles, gaps=st.lists(st.integers(min_value=1, max_value=29 * 24 * 3600)))
def test_refreshing_in_time_forever_still_ends_at_the_limit(role, gaps):
    """Each refresh made before the last token expired, as an active app does."""
    login = START
    now = login
    expiry = refresh_token_expiry(role, now, None, login)
    for gap in gaps:
        now = now + timedelta(seconds=gap)
        if now >= expiry:
            break
        expiry = refresh_token_expiry(role, now, None, login)

    assert expiry <= login + MEMBER_SESSION_LIMIT


def test_a_lost_number_login_exists_before_a_login_ends():
    """A login must be able to reach the age that moves a lost number (D-110).

    At 30 days it could not, once logins ended at 30 (D-174).
    """
    assert ESTABLISHED_LOGIN < LOST_NUMBER_LOGIN < MEMBER_SESSION_LIMIT
