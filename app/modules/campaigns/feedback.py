"""Why a creator's applications are not turning into deals (backlog C4).

Answers "no campaigns, no idea why" with facts the creator can act on, each
carrying its sample size (PLAYBOOK_GAPS: every number shown to a user
carries its sample size and date):

1. Why they were turned down: rejections counted by the reason the brand
   chose. The single most common reason is named only from three
   rejections up, and not at all on a tie: one rejection is not a pattern.
2. Whether their price was the problem: how many of their quotes were above
   the campaign's own stated maximum budget.
3. Whether there is work for them at all: open campaigns they have not
   applied to yet, in their niches, and in their niches in their city.

Profile facts (a bio, a published Passport) are reported plainly, not as
"gaps". Publishing the Passport is the creator's choice (D-036), and this
must not become a way to nag them out of it. The words shown to a creator
belong to the frontend, in Tamil and English (ux.md); this returns facts.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import (
    APPLICATION_STATUSES,
    REJECTION_REASONS,
    Application,
    Campaign,
)

# Below this many rejections no reason is named as "most common" (the same
# floor as the reliability records, D-027).
MIN_REJECTIONS_FOR_A_PATTERN = 3


@dataclass(frozen=True)
class ApplicationRow:
    """One application, with the one campaign fact it is compared against."""

    status: str
    rejection_reason: str | None
    quoted_amount_paise: int | None
    campaign_budget_max_paise: int | None


@dataclass(frozen=True)
class ApplicationFeedback:
    creator_id: uuid.UUID
    as_of: date
    applications: int
    # Every status and every reason is present, zeros included, so a client
    # never has to guess whether a missing key means zero.
    by_status: dict[str, int]
    rejections: int
    rejections_by_reason: dict[str, int]
    # None below the floor, or when two reasons tie: no invented precision.
    most_common_reason: str | None
    # Applications where the creator quoted and the campaign stated a maximum.
    quotes_compared: int
    quotes_above_budget: int
    open_campaigns_in_your_niches: int
    open_campaigns_in_your_niches_and_city: int
    has_bio: bool
    passport_published: bool


def _most_common(reasons: Counter[str], total: int) -> str | None:
    if total < MIN_REJECTIONS_FOR_A_PATTERN:
        return None
    ranked = reasons.most_common(2)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def build_feedback(
    creator: Creator,
    rows: list[ApplicationRow],
    *,
    open_in_niches: int,
    open_in_niches_and_city: int,
    today: date,
) -> ApplicationFeedback:
    """Work the feedback out from rows. Pure, so it is easy to trust."""
    statuses = Counter(row.status for row in rows)
    reasons = Counter(
        row.rejection_reason
        for row in rows
        if row.status == "rejected" and row.rejection_reason is not None
    )
    rejections = statuses["rejected"]
    # (quote, campaign maximum) wherever both exist.
    compared = [
        (row.quoted_amount_paise, row.campaign_budget_max_paise)
        for row in rows
        if row.quoted_amount_paise is not None
        and row.campaign_budget_max_paise is not None
    ]
    return ApplicationFeedback(
        creator_id=creator.id,
        as_of=today,
        applications=len(rows),
        by_status={status: statuses[status] for status in APPLICATION_STATUSES},
        rejections=rejections,
        rejections_by_reason={reason: reasons[reason] for reason in REJECTION_REASONS},
        most_common_reason=_most_common(reasons, rejections),
        quotes_compared=len(compared),
        quotes_above_budget=sum(1 for quote, maximum in compared if quote > maximum),
        open_campaigns_in_your_niches=open_in_niches,
        open_campaigns_in_your_niches_and_city=open_in_niches_and_city,
        has_bio=bool(creator.bio and creator.bio.strip()),
        passport_published=creator.passport_published_at is not None,
    )


def for_creator(db: Session, creator: Creator, today: date) -> ApplicationFeedback:
    """This creator's feedback as of `today`, in two queries."""
    rows = [
        ApplicationRow(*row)
        for row in db.execute(
            select(
                Application.status,
                Application.rejection_reason,
                Application.quoted_amount_paise,
                Campaign.budget_max_paise,
            )
            .join(Campaign, Campaign.id == Application.campaign_id)
            .where(Application.creator_id == creator.id)
        ).tuples()
    ]

    already_applied = exists().where(
        Application.campaign_id == Campaign.id,
        Application.creator_id == creator.id,
    )
    in_city = Campaign.cities.any_() == creator.city
    in_niches, in_niches_and_city = db.execute(
        select(func.count(), func.count().filter(in_city)).where(
            Campaign.status == "open",
            # Still taking applications: a closing date in the past means
            # nobody can apply, whatever the status says.
            or_(
                Campaign.applications_close_on.is_(None),
                Campaign.applications_close_on >= today,
            ),
            Campaign.niches.overlap(creator.niches),
            ~already_applied,
        )
    ).one()

    return build_feedback(
        creator,
        rows,
        open_in_niches=in_niches,
        open_in_niches_and_city=in_niches_and_city,
        today=today,
    )
