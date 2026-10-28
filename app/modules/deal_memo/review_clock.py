"""When a submission the brand has not answered approves itself (D-025). Pure.

The same clock for proof (D-024) and for a draft (item 27): the brand has
the memo's agreed window to answer, and silence approves. Anything with a
`created_at` and an `id` is a submission here, so one rule serves both.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Protocol

from app.core.clock import IST, india_date
from app.modules.deal_memo.models import DealMemo


class Submission(Protocol):
    """One proof or one draft, as the clock reads it."""

    @property
    def id(self) -> uuid.UUID: ...

    @property
    def created_at(self) -> datetime: ...


def review_clock_start(submission: Submission, history: Sequence[Submission]) -> datetime:
    """When this submission's review clock started (D-025).

    The first submission starts a clock, and so does the one that follows
    the brand's first request for changes. Any later resubmission runs on
    the clock that first request restarted: asking again does not buy the
    brand more time. `history` is every submission of its kind on the memo,
    in any order.
    """
    key = (submission.created_at, submission.id)
    earlier = sorted(
        (s for s in history if (s.created_at, s.id) < key),
        key=lambda s: (s.created_at, s.id),
    )
    if len(earlier) <= 1:
        return submission.created_at
    return earlier[1].created_at


def approval_deadline(
    memo: DealMemo, submission: Submission, history: Sequence[Submission]
) -> datetime:
    """When an unanswered submission approves itself (D-025).

    Counted in whole Tamil Nadu calendar days, as D-025 says: the window
    ends at midnight IST after its last full day, so something sent at 23:00
    loses nothing to something sent at 00:30 the same day. `history` is
    required on purpose: without it a resubmission cannot be told from a
    first one.
    """
    last_day = approval_last_day(memo, submission, history)
    return datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=IST)


def approval_last_day(
    memo: DealMemo, submission: Submission, history: Sequence[Submission]
) -> date:
    """The last whole day the brand has to decide, in Tamil Nadu (D-025).

    What a person is told ("decide by 24 Sep"): the deadline itself is the
    midnight that ends this day, which would read as the day after.
    """
    first_day = india_date(review_clock_start(submission, history))
    return first_day + timedelta(days=memo.approval_window_days)
