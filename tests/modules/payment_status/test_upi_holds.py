"""Which UPI ID brands see, and which is waiting: the pure rules (item 82, D-107)."""

from datetime import timedelta

from app.modules.payment_status.upi_change_models import UPI_CHANGE_HOLD, CreatorUpiChange
from app.modules.payment_status.upi_holds import in_effect, waiting
from app.modules.payment_status.upi_models import CreatorUpi
from tests.factories import FIXED_NOW

SET_AT = FIXED_NOW - timedelta(days=10)


def current(upi_id: str = "old@okaxis") -> CreatorUpi:
    return CreatorUpi(
        upi_id=upi_id, consented_at=SET_AT, notice_version="v1", updated_at=SET_AT
    )


def change(upi_id: str = "new@okaxis", asked_at=FIXED_NOW) -> CreatorUpiChange:
    return CreatorUpiChange(
        upi_id=upi_id,
        consented_at=asked_at,
        notice_version="v2",
        usable_at=asked_at + UPI_CHANGE_HOLD,
    )


def test_nothing_given_is_nothing_in_effect_and_nothing_waiting():
    assert in_effect(None, None, FIXED_NOW) is None
    assert waiting(None, FIXED_NOW) is None


def test_the_current_id_is_in_effect_since_it_was_set():
    shown = in_effect(current(), None, FIXED_NOW)

    assert shown is not None
    assert (shown.upi_id, shown.set_at, shown.notice_version) == (
        "old@okaxis",
        SET_AT,
        "v1",
    )


def test_during_the_wait_the_current_id_stays_and_the_new_one_waits():
    row = change()

    assert in_effect(current(), row, FIXED_NOW).upi_id == "old@okaxis"
    assert waiting(row, FIXED_NOW).upi_id == "new@okaxis"


def test_a_first_id_is_not_in_effect_during_its_wait():
    assert in_effect(None, change(), FIXED_NOW) is None


def test_a_second_before_the_end_it_still_waits():
    row = change()
    moment = row.usable_at - timedelta(seconds=1)

    assert in_effect(current(), row, moment).upi_id == "old@okaxis"
    assert waiting(row, moment) is not None


def test_at_its_end_the_new_id_is_in_effect_since_then():
    row = change()

    shown = in_effect(current(), row, row.usable_at)

    assert (shown.upi_id, shown.set_at, shown.notice_version) == (
        "new@okaxis",
        row.usable_at,
        "v2",
    )
    assert waiting(row, row.usable_at) is None
