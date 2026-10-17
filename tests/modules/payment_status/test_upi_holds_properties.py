"""What holds for every moment and every pair of rows (item 82, D-107)."""

from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from app.modules.payment_status.upi_change_models import UPI_CHANGE_HOLD, CreatorUpiChange
from app.modules.payment_status.upi_holds import in_effect, waiting
from app.modules.payment_status.upi_models import CreatorUpi

START = datetime(2026, 1, 1, tzinfo=UTC)
moments = st.integers(min_value=0, max_value=10 * 24 * 3600).map(
    lambda seconds: START + timedelta(seconds=seconds)
)


def current_at(moment: datetime) -> CreatorUpi:
    return CreatorUpi(
        upi_id="old@okaxis", consented_at=moment, notice_version="v1", updated_at=moment
    )


def change_at(moment: datetime) -> CreatorUpiChange:
    return CreatorUpiChange(
        upi_id="new@okaxis",
        consented_at=moment,
        notice_version="v2",
        usable_at=moment + UPI_CHANGE_HOLD,
    )


@given(asked=moments, now=moments, has_current=st.booleans())
def test_a_new_id_never_reaches_a_brand_before_its_24_hours(asked, now, has_current):
    shown = in_effect(current_at(START) if has_current else None, change_at(asked), now)

    if now < asked + UPI_CHANGE_HOLD:
        assert shown is None or shown.upi_id == "old@okaxis"
    else:
        assert shown is not None and shown.upi_id == "new@okaxis"


@given(asked=moments, now=moments)
def test_a_change_is_either_waiting_or_in_effect_never_both(asked, now):
    row = change_at(asked)
    shown = in_effect(None, row, now)

    assert (waiting(row, now) is None) == (shown is not None)


@given(asked=moments, now=moments)
def test_an_id_in_effect_was_set_no_later_than_now(asked, now):
    shown = in_effect(current_at(START), change_at(asked), now)

    assert shown is not None
    assert shown.set_at <= max(now, START)
