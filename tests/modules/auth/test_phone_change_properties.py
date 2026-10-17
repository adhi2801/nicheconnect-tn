"""What holds for every moment and every pair of numbers (item 80, D-108)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.auth import service as login
from app.modules.auth.models.account_phone_change import (
    PHONE_CHANGE_WAIT,
    AccountPhoneChange,
)
from app.modules.auth.phone_changes import is_due

START = datetime(2026, 1, 1, tzinfo=UTC)
moments = st.integers(min_value=0, max_value=10 * 24 * 3600).map(
    lambda seconds: START + timedelta(seconds=seconds)
)
phones = st.from_regex(r"\A\+91[6-9][0-9]{9}\Z")


def change_at(moment: datetime) -> AccountPhoneChange:
    return AccountPhoneChange(
        new_phone="+919812300001",
        requested_at=moment,
        takes_effect_at=moment + PHONE_CHANGE_WAIT,
    )


@given(asked=moments, now=moments)
def test_a_change_is_due_exactly_from_72_hours_after_it_was_asked(asked, now):
    assert is_due(change_at(asked), now) == (now >= asked + timedelta(hours=72))


@given(asked=moments, earlier=moments, later=moments)
def test_once_due_a_change_stays_due(asked, earlier, later):
    earlier, later = min(earlier, later), max(earlier, later)

    if is_due(change_at(asked), earlier):
        assert is_due(change_at(asked), later)


@given(numbers=st.lists(phones, min_size=1, max_size=4))
def test_numbers_are_always_locked_in_one_order_and_once_each(numbers):
    """Two transactions locking the same numbers can never wait in a circle."""
    locked: list[str] = []
    original = login.lock_phone
    login.lock_phone = lambda db, phone: locked.append(phone)  # type: ignore[assignment]
    try:
        login.lock_phones(None, *numbers)  # type: ignore[arg-type]
        forwards = list(locked)
        locked.clear()
        login.lock_phones(None, *reversed(numbers))  # type: ignore[arg-type]
    finally:
        login.lock_phone = original  # type: ignore[assignment]

    assert forwards == locked == sorted(set(numbers))
