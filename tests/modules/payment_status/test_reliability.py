"""A brand's payment record: what it says, and what it refuses to hide.

A creator reads this before deciding to spend a week filming for someone. The
tests below are mostly about the ways a record like this misleads people if
it is built carelessly.
"""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.modules.payment_status import reliability
from app.modules.payment_status.models import PaymentStatus

BRAND = uuid.uuid4()
RRN = "412345678901"
APPROVED = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
DUE_ON = date(2026, 9, 8)  # approval + the default 7-day window
TODAY = date(2026, 9, 20)


def record(**overrides) -> PaymentStatus:
    """One payment row. Unsaved: the calculation is pure."""
    fields = {
        "amount_paise": 800_000,
        "due_on": DUE_ON,
        "created_at": APPROVED,
        "updated_at": APPROVED,
    }
    fields.update(overrides)
    return PaymentStatus(**fields)


def paid_on(day: int, **overrides) -> PaymentStatus:
    """A payment the brand marked sent on that day of September."""
    return record(
        method="upi",
        reference=RRN,
        marked_paid_at=datetime(2026, 9, day, 10, 0, tzinfo=UTC),
        **overrides,
    )


def never_paid(due_on: date = date(2026, 8, 1)) -> PaymentStatus:
    """Long past due and past the silence window: an unpaid record."""
    return record(due_on=due_on, created_at=datetime(2026, 7, 25, 9, 0, tzinfo=UTC))


def build(payments, today=TODAY):
    return reliability.build_record(payments, BRAND, today)


# --- the floor ------------------------------------------------------------


def test_a_paid_date_is_never_invented_for_an_unpaid_record():
    # Speed and on-time figures read the paid date. Asking for one on a
    # record nobody marked paid is a bug in the caller, and must say so.
    with pytest.raises(ValueError, match="marked as paid"):
        reliability._paid_on(never_paid())


def test_a_brand_with_no_deals_has_nothing_to_report():
    result = build([])

    assert result.status == reliability.NO_HISTORY_YET
    assert result.deals_completed == 0
    assert result.paid_on_time_share is None
    assert result.median_days_to_pay is None


def test_figures_are_withheld_below_three_completed_deals():
    """D-027. Two out of two is not evidence of anything."""
    result = build([paid_on(5), paid_on(6)])

    assert result.status == reliability.NO_HISTORY_YET
    assert result.deals_completed == 2
    assert result.paid_on_time_share is None


def test_withheld_is_not_the_same_as_zero():
    """None must never be rendered as 0%. It means 'not enough to say'."""
    result = build([paid_on(5)])

    assert result.paid_on_time_share is None
    assert result.deals_paid == 1


def test_three_completed_deals_is_enough_to_speak():
    result = build([paid_on(5), paid_on(6), paid_on(7)])

    assert result.status == reliability.HAS_HISTORY
    assert result.deals_completed == 3
    assert result.paid_on_time_share == 1.0


# --- silence must not launder a bad record --------------------------------


def test_a_brand_that_never_paid_is_counted_without_anyone_complaining():
    """The central point.

    A creator who was never paid is the least likely person to come back and
    report it. The calendar reports it instead.
    """
    result = build([never_paid(), never_paid(), never_paid()])

    assert result.deals_completed == 3
    assert result.deals_unpaid == 3
    assert result.status == reliability.HAS_HISTORY
    assert result.paid_on_time_share == 0.0


def test_paying_none_of_them_reads_as_zero_not_as_no_figure():
    """Dividing by the paid deals would have let this brand show nothing."""
    result = build([never_paid(), never_paid(), never_paid()])

    assert result.paid_on_time_share == 0.0
    assert result.paid_on_time_share is not None


def test_never_paying_leaves_the_speed_figure_undefined():
    """ "Pays in 0 days" would be a lie in the brand's favour."""
    result = build([never_paid(), never_paid(), never_paid()])

    assert result.median_days_to_pay is None


def test_one_unpaid_deal_drags_the_share_down():
    result = build([paid_on(5), paid_on(6), paid_on(7), never_paid()])

    assert result.deals_completed == 4
    assert result.paid_on_time_share == 0.75


# --- "new brand" must not be a hiding place -------------------------------


def test_a_brand_owing_money_right_now_never_simply_reads_as_new():
    """Reputation systems get gamed by starting again. A brand with nothing
    completed but two creators waiting must not look like a clean slate."""
    result = build([record(due_on=date(2026, 9, 15)), record(due_on=date(2026, 9, 16))])

    assert result.status == reliability.NO_HISTORY_YET
    assert result.currently_overdue == 2


def test_overdue_is_reported_above_the_floor_too():
    result = build([paid_on(5), paid_on(6), paid_on(7), record(due_on=date(2026, 9, 15))])

    assert result.status == reliability.HAS_HISTORY
    assert result.currently_overdue == 1


def test_a_payment_still_inside_its_deadline_is_not_overdue():
    result = build([record(due_on=date(2026, 9, 30))])

    assert result.currently_overdue == 0
    assert result.deals_completed == 0


def test_a_settled_record_is_not_counted_as_overdue():
    result = build([paid_on(5), paid_on(6), paid_on(7)])

    assert result.currently_overdue == 0


# --- what counts as settled -----------------------------------------------


def test_a_payment_that_is_merely_late_is_not_yet_a_failure():
    """Four days overdue is not the same as never paying. It shows in
    `currently_overdue`, and waits to be settled."""
    result = build([record(due_on=date(2026, 9, 18))])

    assert result.deals_completed == 0
    assert result.deals_unpaid == 0
    assert result.currently_overdue == 1


def test_a_payment_the_creator_never_confirmed_still_counts_for_the_brand():
    """D-033: the creator's silence is not the brand's fault. The brand did
    the thing being measured."""
    unconfirmed = paid_on(5)  # marked long ago, never confirmed

    result = build([unconfirmed, paid_on(6), paid_on(7)], today=date(2026, 10, 30))

    assert result.deals_completed == 3
    assert result.deals_paid == 3
    assert result.paid_on_time_share == 1.0


def test_a_confirmed_payment_counts(db=None):
    confirmed = paid_on(5, confirmed_at=datetime(2026, 9, 6, 9, 0, tzinfo=UTC))

    result = build([confirmed, paid_on(6), paid_on(7)])

    assert result.deals_paid == 3


# --- being on time --------------------------------------------------------


def test_paying_on_the_due_date_is_on_time():
    result = build([paid_on(8), paid_on(8), paid_on(8)])

    assert result.paid_on_time_share == 1.0


def test_paying_the_day_after_is_not():
    result = build([paid_on(9), paid_on(8), paid_on(8)])

    assert result.paid_on_time_share == pytest.approx(2 / 3)


def test_the_median_is_the_usual_wait_not_the_worst_one():
    """One slow payment among three should not read as though every payment
    is slow."""
    result = build([paid_on(3), paid_on(4), paid_on(30)])

    assert result.median_days_to_pay == 3  # 2, 3 and 29 days


def test_days_are_counted_from_approval():
    """The question a creator asks is "how long after I finished?"."""
    result = build([paid_on(5), paid_on(5), paid_on(5)])

    assert result.median_days_to_pay == 4  # approved 1 Sep, paid 5 Sep


def test_the_indian_calendar_decides_whether_a_payment_was_on_time():
    """The deadline is a date in Tamil Nadu, so that is where it is read.

    19:00 UTC on the due date is already 00:30 the next morning in India:
    the brand missed the day. Reading the server's clock instead would have
    recorded it as on time, quietly crediting the brand with a day it did
    not have and telling creators something untrue.
    """
    just_past_midnight_in_india = datetime(2026, 9, 8, 19, 0, tzinfo=UTC)
    missed_it = record(
        method="upi", reference=RRN, marked_paid_at=just_past_midnight_in_india
    )

    result = build([missed_it, paid_on(8), paid_on(8)])

    assert result.paid_on_time_share == pytest.approx(2 / 3)


# --- nothing is smoothed --------------------------------------------------


def test_the_figure_is_what_happened_not_a_number_pulled_toward_average():
    """Shrinkage is right for opinions and wrong for records. Three out of
    four is reported as three out of four."""
    result = build([paid_on(5), paid_on(6), paid_on(7), never_paid()])

    assert result.paid_on_time_share == 0.75
    assert result.deals_completed == 4


def test_the_count_always_travels_with_the_figures():
    """People ignore sample size unless it is in front of them, so it is."""
    result = build([paid_on(5), paid_on(6), paid_on(7)])

    assert result.deals_completed == 3
    assert result.deals_paid == 3
    assert result.has_history is True
