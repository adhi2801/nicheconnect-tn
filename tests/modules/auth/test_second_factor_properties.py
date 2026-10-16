"""What holds for every secret and every moment (item 101, D-105; testing.md section 6)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.auth import second_factor
from app.modules.auth.models.totp_factor import SECRET_BYTES

secrets_ = st.binary(min_size=SECRET_BYTES, max_size=SECRET_BYTES)
moments = st.datetimes(
    min_value=datetime(2026, 1, 1),  # noqa: DTZ001
    max_value=datetime(2100, 1, 1),  # noqa: DTZ001
    timezones=st.just(UTC),
)
# Earlier steps before which a code may already have been used.
last_used = st.one_of(st.none(), st.integers(min_value=0, max_value=10))


def step(now: datetime, offset: int) -> int:
    return second_factor.step_at(now) + offset


@given(secret=secrets_, now=moments)
def test_the_code_shown_now_is_accepted_exactly_once(secret, now):
    shown = second_factor.code_at_step(secret, step(now, 0))

    first = second_factor.accepted_step(secret, shown, now, None)

    assert first == step(now, 0)
    assert second_factor.accepted_step(secret, shown, now, first) is None


@given(
    secret=secrets_,
    now=moments,
    offset=st.one_of(st.integers(-1000, -2), st.integers(1, 1000)),
)
def test_only_the_current_step_and_the_one_before_ever_count(secret, now, offset):
    """A code from two steps back, or from the future, is never accepted,
    unless it happens to equal the current or the previous code (one in a
    million each, which is what a 6-digit code is)."""
    shown = second_factor.code_at_step(secret, step(now, offset))
    in_window = {
        second_factor.code_at_step(secret, step(now, 0)),
        second_factor.code_at_step(secret, step(now, -1)),
    }

    accepted = second_factor.accepted_step(secret, shown, now, None)

    assert accepted is None or shown in in_window


@given(secret=secrets_, now=moments, back=last_used)
def test_a_step_at_or_before_the_last_one_used_is_never_accepted(secret, now, back):
    last = None if back is None else step(now, -back)
    for offset in (0, -1):
        shown = second_factor.code_at_step(secret, step(now, offset))

        accepted = second_factor.accepted_step(secret, shown, now, last)

        assert accepted is None or last is None or accepted > last


@given(secret=secrets_, now=moments, seconds=st.integers(0, 29))
def test_a_code_typed_within_thirty_seconds_of_appearing_still_works(
    secret, now, seconds
):
    shown = second_factor.code_at_step(secret, step(now, 0))

    later = now + timedelta(seconds=seconds)

    assert second_factor.accepted_step(secret, shown, later, None) is not None


@given(secret=secrets_, step_number=st.integers(0, 2**40))
def test_a_code_is_always_six_digits(secret, step_number):
    shown = second_factor.code_at_step(secret, step_number)

    assert len(shown) == 6 and shown.isdigit()
