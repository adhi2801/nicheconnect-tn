"""A direct offer's pure rules (D-189): every branch, without a database.

Mutated nightly with the module (pyproject.toml, D-091), so each boundary
here is pinned by an exact example on both sides of it.
"""

import hashlib
import hmac
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.clock import IST
from app.core.config import settings
from app.modules.deal_memo import direct_offer_rules as rules
from app.modules.deal_memo.direct_offer_models import (
    DIRECT_OFFER_LIFETIME,
    ENDED_OFFER_KEPT_FOR,
)

# 10:00 on 20 November 2026 in Tamil Nadu.
NOW = datetime(2026, 11, 20, 4, 30, tzinfo=UTC)
TODAY = date(2026, 11, 20)


def test_a_link_token_is_256_bits_in_64_hex_characters_and_never_repeats():
    tokens = {rules.new_link_token() for _ in range(200)}

    assert len(tokens) == 200
    assert all(len(token) == 64 and rules.is_link_token(token) for token in tokens)
    assert rules.LINK_TOKEN_BYTES * 8 == 256


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "a" * 63 + "=",
        " " + "a" * 63,
        "a" * 64 + "\n",
    ],
)
def test_anything_but_a_token_s_shape_is_no_token(value):
    assert not rules.is_link_token(value)


def test_the_token_is_kept_only_as_a_keyed_hash_under_its_own_label():
    token = rules.new_link_token()
    stored = rules.hash_link_token(token)

    assert len(stored) == 64 and token not in stored
    assert stored == rules.hash_link_token(token)
    assert stored != rules.hash_link_token(rules.new_link_token())
    # The same value under the number's label hashes differently: one key,
    # two purposes, never interchangeable.
    assert stored != rules.hash_recipient_phone(token)


def test_the_hashes_are_pinned_to_their_labels_and_key():
    """Known answers, worked out here without the module: a change to a
    label, or to the separator, would orphan every hash already stored (a
    link would stop opening, a "stop these" stop blocking), so it must fail
    a test, not pass silently."""
    key = settings.otp_hash_key.get_secret_value().encode()

    def expected(label: bytes, value: str) -> str:
        return hmac.new(key, label + b"\x00" + value.encode(), hashlib.sha256).hexdigest()

    token = "a" * 64
    phone = "+919876543210"
    assert rules.hash_link_token(token) == expected(b"direct-offer-link", token)
    assert rules.hash_recipient_phone(phone) == expected(b"direct-offer-phone", phone)


def test_a_number_s_hash_is_its_own_not_a_team_invite_s():
    from app.modules.auth.team_invites import hash_invited_phone

    phone = "+919876543210"

    assert rules.hash_recipient_phone(phone) == rules.hash_recipient_phone(phone)
    assert rules.hash_recipient_phone(phone) != hash_invited_phone(phone)
    assert rules.hash_recipient_phone(phone) != rules.hash_recipient_phone(
        "+919876543211"
    )


@pytest.mark.parametrize("status", ["accepted", "withdrawn", "stopped", "expired"])
def test_an_ended_offer_shows_as_it_ended_whatever_its_date(status):
    assert rules.shown_status(status, NOW + timedelta(days=1), NOW) == status
    assert rules.shown_status(status, NOW - timedelta(days=1), NOW) == status
    assert not rules.is_waiting(status, NOW + timedelta(days=1), NOW)


def test_a_waiting_offer_expires_at_its_last_moment_exactly():
    expires_at = NOW

    assert (
        rules.shown_status("sent", expires_at, NOW - timedelta(microseconds=1)) == "sent"
    )
    assert rules.is_waiting("sent", expires_at, NOW - timedelta(microseconds=1))
    assert rules.shown_status("sent", expires_at, NOW) == "expired"
    assert not rules.is_waiting("sent", expires_at, NOW)


def test_a_due_date_from_today_to_a_year_ahead_may_be_offered():
    assert rules.due_date_problem(TODAY, NOW) is None
    assert rules.due_date_problem(TODAY + timedelta(days=365), NOW) is None


def test_a_due_date_before_today_in_tamil_nadu_has_passed():
    assert rules.due_date_problem(TODAY - timedelta(days=1), NOW) == "passed"
    # 23:59 on the 19th in UTC is already the 20th in Tamil Nadu.
    late_evening = datetime(2026, 11, 19, 23, 59, tzinfo=UTC)
    assert rules.due_date_problem(date(2026, 11, 19), late_evening) == "passed"


def test_a_due_date_past_a_year_is_too_far():
    assert rules.due_date_problem(TODAY + timedelta(days=366), NOW) == "too_far"


def test_the_day_starts_at_midnight_in_tamil_nadu():
    assert rules.start_of_india_day(NOW) == datetime(2026, 11, 20, tzinfo=IST)
    midnight = datetime(2026, 11, 20, tzinfo=IST)
    assert rules.start_of_india_day(midnight) == midnight
    assert rules.start_of_india_day(midnight - timedelta(microseconds=1)) == datetime(
        2026, 11, 19, tzinfo=IST
    )


def test_tomorrow_is_counted_in_whole_seconds_and_never_zero():
    assert rules.seconds_until_tomorrow(NOW) == 14 * 3600
    last = datetime(2026, 11, 21, tzinfo=IST) - timedelta(microseconds=1)
    assert rules.seconds_until_tomorrow(last) == 1
    assert (
        rules.seconds_until_tomorrow(
            datetime(2026, 11, 21, tzinfo=IST) - timedelta(seconds=1, microseconds=1)
        )
        == 2
    )


def test_a_number_frees_when_its_oldest_offer_of_the_week_leaves_it():
    oldest = NOW - timedelta(days=6)

    assert rules.seconds_until_number_frees(oldest, NOW) == 86400
    assert rules.seconds_until_number_frees(NOW - rules.NUMBER_WINDOW, NOW) == 1
    assert (
        rules.seconds_until_number_frees(oldest, NOW - timedelta(microseconds=1)) == 86401
    )


def test_the_limits_are_the_approved_ones():
    assert rules.DAILY_OFFERS_PER_CREATOR == 10
    assert rules.WEEKLY_OFFERS_PER_NUMBER == 3
    assert timedelta(days=7) == rules.NUMBER_WINDOW
    assert timedelta(days=365) == rules.MAX_DUE_AHEAD
    # The privacy impact assessment's numbers (D-189): a link works 14 days,
    # and an offer ended without a deal is gone 30 days later.
    assert timedelta(days=14) == DIRECT_OFFER_LIFETIME
    assert timedelta(days=30) == ENDED_OFFER_KEPT_FOR


# Hypothesis takes naive bounds and adds the zone itself (timezones=).
moments = st.datetimes(
    min_value=datetime(2020, 1, 1),  # noqa: DTZ001
    max_value=datetime(2040, 1, 1),  # noqa: DTZ001
    timezones=st.just(UTC),
)


@given(moment=moments)
def test_every_moment_lies_in_its_own_day_and_before_tomorrow(moment):
    start = rules.start_of_india_day(moment)

    assert start <= moment < start + timedelta(days=1)
    assert 1 <= rules.seconds_until_tomorrow(moment) <= 86400


@given(
    moment=moments,
    ahead=st.integers(min_value=-800, max_value=800),
)
def test_a_due_date_is_refused_exactly_outside_today_to_a_year(moment, ahead):
    today = moment.astimezone(IST).date()
    problem = rules.due_date_problem(today + timedelta(days=ahead), moment)

    if ahead < 0:
        assert problem == "passed"
    elif ahead > 365:
        assert problem == "too_far"
    else:
        assert problem is None
