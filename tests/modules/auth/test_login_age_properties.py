"""What holds for every login time and every moment (D-109)."""

import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.modules.auth.exceptions import LoginTooRecent
from app.modules.auth.login_age import ESTABLISHED_LOGIN, allowed_from, ensure_established

START = datetime(2026, 1, 1, tzinfo=UTC)
moments = st.integers(min_value=0, max_value=30 * 24 * 3600).map(
    lambda seconds: START + timedelta(seconds=seconds)
)


@given(logged_in=moments, now=moments)
def test_allowed_exactly_from_a_week_after_the_login(logged_in, now):
    try:
        ensure_established(logged_in, now)
        allowed = True
    except LoginTooRecent:
        allowed = False

    assert allowed == (now >= logged_in + timedelta(days=7))


@given(logged_in=moments, now=moments)
def test_a_refusal_says_how_long_to_wait_and_never_less(logged_in, now):
    try:
        ensure_established(logged_in, now)
    except LoginTooRecent as refused:
        wait = int(refused.headers["Retry-After"])
        assert wait >= 1
        assert now + timedelta(seconds=wait) >= allowed_from(logged_in, now)
        assert wait == max(
            1, math.ceil((logged_in + ESTABLISHED_LOGIN - now).total_seconds())
        )


@given(now=moments)
def test_a_login_of_unknown_age_is_never_old_enough(now):
    with pytest.raises(LoginTooRecent):
        ensure_established(None, now)
