"""Application feedback: the pattern behind a creator's rejections (C4).

Pure tests of how the figures are worked out. What they guard against is the
feedback inventing a pattern: naming a "most common reason" from one
rejection, or picking a winner out of a tie.
"""

import uuid
from datetime import UTC, date, datetime

from app.modules.auth.models.creator import Creator
from app.modules.campaigns import feedback
from app.modules.campaigns.feedback import ApplicationRow
from app.modules.campaigns.models import APPLICATION_STATUSES, REJECTION_REASONS

TODAY = date(2026, 9, 21)


def creator(**overrides) -> Creator:
    fields = {
        "id": uuid.uuid4(),
        "city": "Coimbatore",
        "niches": ["food"],
        "bio": "Street food across Tamil Nadu.",
        "passport_published_at": None,
    }
    fields.update(overrides)
    return Creator(**fields)


def rejected(reason: str | None) -> ApplicationRow:
    return ApplicationRow("rejected", reason, None, None)


def quoted(quote: int | None, budget_max: int | None) -> ApplicationRow:
    return ApplicationRow("submitted", None, quote, budget_max)


def build(rows, who=None, *, in_niches=0, in_city=0):
    return feedback.build_feedback(
        who or creator(),
        rows,
        open_in_niches=in_niches,
        open_in_niches_and_city=in_city,
        today=TODAY,
    )


def test_no_applications_reads_as_zeros_with_every_key_present():
    result = build([])

    assert result.applications == 0
    assert set(result.by_status) == set(APPLICATION_STATUSES)
    assert set(result.rejections_by_reason) == set(REJECTION_REASONS)
    assert all(count == 0 for count in result.by_status.values())
    assert result.most_common_reason is None
    assert result.as_of == TODAY


def test_one_rejection_is_not_a_pattern():
    result = build([rejected("budget_mismatch"), rejected("budget_mismatch")])

    assert result.rejections == 2
    assert result.rejections_by_reason["budget_mismatch"] == 2
    assert result.most_common_reason is None


def test_three_rejections_name_the_most_common_reason():
    result = build(
        [rejected("budget_mismatch"), rejected("budget_mismatch"), rejected("timing")]
    )

    assert result.most_common_reason == "budget_mismatch"


def test_a_tie_names_no_reason_rather_than_picking_one():
    result = build(
        [
            rejected("budget_mismatch"),
            rejected("timing"),
            rejected("budget_mismatch"),
            rejected("timing"),
        ]
    )

    assert result.most_common_reason is None


def test_a_rejection_without_a_reason_still_counts_as_a_rejection():
    result = build([rejected(None), rejected("timing")])

    assert result.rejections == 2
    assert sum(result.rejections_by_reason.values()) == 1


def test_quotes_above_the_campaigns_own_maximum_are_counted():
    result = build([quoted(900_000, 800_000), quoted(700_000, 800_000)])

    assert result.quotes_compared == 2
    assert result.quotes_above_budget == 1


def test_a_quote_equal_to_the_maximum_is_not_above_it():
    assert build([quoted(800_000, 800_000)]).quotes_above_budget == 0


def test_nothing_to_compare_is_left_out_not_counted_as_fine():
    # No quote, or a campaign with no stated maximum (barter): not comparable.
    result = build([quoted(None, 800_000), quoted(900_000, None)])

    assert result.quotes_compared == 0
    assert result.quotes_above_budget == 0


def test_a_blank_bio_is_no_bio():
    assert build([], creator(bio="   ")).has_bio is False
    assert build([], creator(bio=None)).has_bio is False


def test_passport_published_is_reported_as_a_fact():
    published = creator(passport_published_at=datetime(2026, 9, 1, tzinfo=UTC))

    assert build([], published).passport_published is True
    assert build([], creator()).passport_published is False


def test_open_campaign_counts_are_passed_through():
    result = build([], in_niches=5, in_city=2)

    assert result.open_campaigns_in_your_niches == 5
    assert result.open_campaigns_in_your_niches_and_city == 2
