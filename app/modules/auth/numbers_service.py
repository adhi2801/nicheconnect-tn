"""The founders' weekly numbers (item 63, docs/SURVIVAL_PLAYBOOK.md section 4).

Whether the first city is dense enough, and whether the business is alive,
is a set of numbers read every week. Until now they could only be counted by
hand. Each is worked out from the records as they stand, never stored
(backend.md section 2), for any period of 1 to 90 Tamil Nadu days, beside
the period before it so the direction shows.

Rules that keep the numbers honest:

- **A rate is null below five examples** ("five or nothing", D-056, D-078),
  never a 0% or 100% that two campaigns would produce.
- **A campaign counts towards the fill rate only once it is 14 days old.**
  A campaign posted yesterday has had no chance to fill, and counting it
  would make a growing week look like a failing one. The young ones are
  counted separately.
- **Totals only.** Nothing here names or describes a person, so reading it
  needs no entry in the admin log, unlike opening an account (D-061).

A campaign's posting time is not stored; `created_at` stands in for it, and
a campaign still in draft is left out. A campaign kept in draft for days
before publishing therefore looks slower to fill than it was.
"""

import statistics
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, select, union
from sqlalchemy.orm import Session, aliased

from app.core.clock import IST
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo.models import DealMemo
from app.modules.payment_status.models import PaymentStatus

MIN_SAMPLE = 5
FILL_WINDOW = timedelta(days=14)
MAX_DAYS = 90


@dataclass(frozen=True)
class PeriodNumbers:
    from_on: date
    to_on: date
    new_brands: int
    new_creators: int
    active_brands: int
    active_creators: int
    campaigns_posted: int
    campaigns_old_enough_to_judge: int
    campaigns_filled_within_14_days: int
    campaign_fill_rate: float | None
    median_hours_to_first_application: float | None
    applications_sent: int
    applications_accepted_so_far: int
    application_success_so_far: float | None
    invitations_sent: int
    deals_agreed: int
    value_of_deals_agreed_paise: int
    repeat_deals: int
    repeat_share: float | None
    payments_confirmed: int
    paid_on_time: int
    paid_on_time_share: float | None


@dataclass(frozen=True)
class FounderNumbers:
    as_of: date
    days: int
    city: str | None
    current: PeriodNumbers
    previous: PeriodNumbers


def _share(part: int, whole: int) -> float | None:
    return part / whole if whole >= MIN_SAMPLE else None


def _start(day: date) -> datetime:
    """Midnight at the start of `day` in Tamil Nadu."""
    return datetime.combine(day, time(0), IST)


def _in(column: Any, start: datetime, end: datetime) -> ColumnElement[bool]:
    """The column's moment falls in [start, end)."""
    return and_(column >= start, column < end)


def _campaign_in_city(city: str | None) -> ColumnElement[bool]:
    if city is None:
        return and_(True)
    named = func.unnest(Campaign.cities).column_valued("named", joins_implicitly=True)
    return exists(select(named).where(func.lower(func.btrim(named)) == city))


def _deals(
    start: datetime, end: datetime, city: str | None
) -> Select[tuple[int, int | None, int]]:
    """Deals agreed in the period: how many, their value, how many repeats.

    A repeat is a deal between a brand and a creator who had agreed a deal
    before this one, whether or not it was sent as "work together again".
    """
    earlier_memo, earlier_app, earlier_campaign = (
        aliased(DealMemo),
        aliased(Application),
        aliased(Campaign),
    )
    agreed_before = exists(
        select(earlier_memo.id)
        .join(earlier_app, earlier_app.id == earlier_memo.application_id)
        .join(earlier_campaign, earlier_campaign.id == earlier_app.campaign_id)
        .where(
            earlier_app.creator_id == Application.creator_id,
            earlier_campaign.brand_id == Campaign.brand_id,
            earlier_memo.accepted_at < DealMemo.accepted_at,
        )
    )
    return (
        select(
            func.count(DealMemo.id),
            func.coalesce(func.sum(DealMemo.fee_amount_paise), 0),
            func.count(DealMemo.id).filter(agreed_before),
        )
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(_in(DealMemo.accepted_at, start, end), _campaign_in_city(city))
    )


def _period(db: Session, first: date, last: date, city: str | None) -> PeriodNumbers:
    """One period's numbers, in a fixed number of queries whatever its size."""
    start, end = _start(first), _start(last + timedelta(days=1))
    in_city = _campaign_in_city(city)
    creator_in_city = (
        func.lower(func.btrim(Creator.city)) == city if city is not None else and_(True)
    )

    new_brands = db.scalar(
        select(func.count(Brand.id)).where(_in(Brand.created_at, start, end))
    )
    new_creators = db.scalar(
        select(func.count(Creator.id)).where(
            _in(Creator.created_at, start, end), creator_in_city
        )
    )

    # Every campaign posted in the period, with its first application and its
    # first agreed deal: one row each, so the rates are worked out from facts.
    first_application = (
        select(func.min(Application.created_at))
        .where(Application.campaign_id == Campaign.id, Application.origin == "applied")
        .scalar_subquery()
    )
    first_deal = (
        select(func.min(DealMemo.accepted_at))
        .join(Application, Application.id == DealMemo.application_id)
        .where(Application.campaign_id == Campaign.id)
        .scalar_subquery()
    )
    campaigns = db.execute(
        select(
            Campaign.brand_id, Campaign.created_at, first_application, first_deal
        ).where(_in(Campaign.created_at, start, end), Campaign.status != "draft", in_city)
    ).all()
    judged = [row for row in campaigns if row[1] + FILL_WINDOW <= end]
    filled = [
        row for row in judged if row[3] is not None and row[3] - row[1] <= FILL_WINDOW
    ]
    waits = [
        (row[2] - row[1]).total_seconds() / 3600
        for row in campaigns
        if row[2] is not None
    ]

    applications = db.execute(
        select(
            func.count().filter(Application.origin == "applied"),
            func.count().filter(
                Application.origin == "applied", Application.status == "accepted"
            ),
            func.count().filter(Application.origin == "invited"),
        )
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(_in(Application.created_at, start, end), in_city)
    ).one()

    deals, value, repeats = db.execute(_deals(start, end, city)).one()

    paid = db.execute(
        select(
            func.count(PaymentStatus.id),
            func.count(PaymentStatus.id).filter(
                func.date(func.timezone("Asia/Kolkata", PaymentStatus.marked_paid_at))
                <= PaymentStatus.due_on
            ),
        )
        .join(DealMemo, DealMemo.id == PaymentStatus.deal_memo_id)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .where(_in(PaymentStatus.confirmed_at, start, end), in_city)
    ).one()

    # Active: did something that moves a deal. A brand posted a campaign or
    # agreed a deal; a creator applied or agreed a deal.
    agreed_in_period = and_(_in(DealMemo.accepted_at, start, end), in_city)
    active_brands = db.scalar(
        select(func.count()).select_from(
            union(
                select(Campaign.brand_id).where(
                    _in(Campaign.created_at, start, end),
                    Campaign.status != "draft",
                    in_city,
                ),
                select(Campaign.brand_id)
                .join(Application, Application.campaign_id == Campaign.id)
                .join(DealMemo, DealMemo.application_id == Application.id)
                .where(agreed_in_period),
            ).subquery()
        )
    )
    active_creators = db.scalar(
        select(func.count()).select_from(
            union(
                select(Application.creator_id)
                .join(Campaign, Campaign.id == Application.campaign_id)
                .where(
                    _in(Application.created_at, start, end),
                    Application.origin == "applied",
                    in_city,
                ),
                select(Application.creator_id)
                .join(Campaign, Campaign.id == Application.campaign_id)
                .join(DealMemo, DealMemo.application_id == Application.id)
                .where(agreed_in_period),
            ).subquery()
        )
    )

    sent, accepted, invited = applications
    confirmed, on_time = paid
    return PeriodNumbers(
        from_on=first,
        to_on=last,
        new_brands=new_brands or 0,
        new_creators=new_creators or 0,
        active_brands=active_brands or 0,
        active_creators=active_creators or 0,
        campaigns_posted=len(campaigns),
        campaigns_old_enough_to_judge=len(judged),
        campaigns_filled_within_14_days=len(filled),
        campaign_fill_rate=_share(len(filled), len(judged)),
        median_hours_to_first_application=(
            round(statistics.median(waits), 1) if len(waits) >= MIN_SAMPLE else None
        ),
        applications_sent=sent,
        applications_accepted_so_far=accepted,
        application_success_so_far=_share(accepted, sent),
        invitations_sent=invited,
        deals_agreed=deals,
        value_of_deals_agreed_paise=int(value),
        repeat_deals=repeats,
        repeat_share=_share(repeats, deals),
        payments_confirmed=confirmed,
        paid_on_time=on_time,
        paid_on_time_share=_share(on_time, confirmed),
    )


def founder_numbers(
    db: Session, *, ending_on: date, days: int, city: str | None
) -> FounderNumbers:
    """The period ending on `ending_on`, and the same length before it."""
    wanted = city.strip().lower() if city else None
    first = ending_on - timedelta(days=days - 1)
    before_last = first - timedelta(days=1)
    return FounderNumbers(
        as_of=ending_on,
        days=days,
        city=wanted,
        current=_period(db, first, ending_on, wanted),
        previous=_period(db, before_last - timedelta(days=days - 1), before_last, wanted),
    )
