"""The pre-deal check: what our records hold about the other side (item 133, D-182).

Before a deal is agreed, each side sees facts about the other that only
this platform's records hold, gathered on one screen. Every part is a fact
from the record, dated, with the number it rests on (`legal.md` sections 1
and 3.12):

- **a creator reads about the brand**: its payment record (deals paid,
  currently overdue, median days to pay, the on-time share, how many
  different creators), the deals that went to a dispute and how each ended,
  its verified domain and the date the registry gives for it, the look-alike
  name flag, when its account was created, and how long it takes to decide
  on work;
- **a brand reads about the creator**: the delivery record, how long the
  creator takes to answer a memo and to confirm a payment arrived, the deals
  that went to a dispute and how each ended, when the account was created,
  and each channel's figures, the creator's own claim, beside any count a
  connected platform reported;
- **both read** whether this is their first deal together, and how many of
  their earlier deals finished.

**Never a score, never a refusal.** Nothing here is combined into one
number or decides whether the deal may go ahead: the two people decide.
Disputes are counted as "went to a dispute", with how each ended, never who
opened one or who was at fault (D-028). The shares come from the records
they reuse, each null below its own floor (D-027, D-038, D-071), never 0;
the counts are reported always, as `currently_overdue` is, so a new account
is never a place to hide (D-027 rule 2).

**Blocks.** Across a block, either way, the check answers as for a memo
that does not exist, as every record of the other side read by id does
(D-175, D-177); the deal itself carries on. **Takedowns.** A creator's
profile withheld for legal reasons (item 52) keeps its channels out of the
check, which says so, so the check is never a way round a takedown. A
brand's takedown withholds its campaigns, not its records, so the brand's
facts here are the ones `GET /brands/{id}/reliability` still answers.

**The other side's account.** A side suspended or departed (D-122) is still
read, as the separate records read it: the deal stays on the record, and
what it says is a fact either way.

No query per row, however long either side's history: each part reads its
rows in one query per kind. The count is bounded, not constant: a pair with
no earlier deal skips the stage's queries, and a deal with a draft review
adds one each to the stage and the delivery record.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session, aliased

from app.core.clock import india_date
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from app.modules.campaigns.models import Application, Campaign
from app.modules.deal_memo import delivery_record, response_times, stage
from app.modules.deal_memo.delivery_record import DeliveryRecord
from app.modules.deal_memo.exceptions import MemoNotFound
from app.modules.deal_memo.models import DealMemo
from app.modules.deal_memo.response_times import ResponseTime
from app.modules.disputes import service as disputes
from app.modules.disputes.models import Dispute
from app.modules.payment_status import reliability
from app.modules.payment_status.models import PaymentStatus
from app.modules.payment_status.reliability import ReliabilityRecord
from app.modules.profiles import connection_service as connections
from app.modules.profiles.brand_domain_models import BrandDomain
from app.modules.profiles.brand_names import NameFlag
from app.modules.profiles.connection_models import ConnectedAccount
from app.modules.profiles.models import CreatorChannel
from app.modules.profiles.rate_card_service import list_channels
from app.modules.safety.blocks import not_blocked
from app.modules.safety.takedowns import not_withheld


@dataclass(frozen=True)
class DisputeHistory:
    """The deals one side agreed, and how many went to a dispute."""

    deals_agreed: int
    went_to_dispute: int
    # Every state in `disputes.DISPUTE_STATES`, 0 where none ended that way.
    outcomes: dict[str, int]


@dataclass(frozen=True)
class BrandFacts:
    brand_id: uuid.UUID
    account_created_on: date
    payment_record: ReliabilityRecord
    verified_domain: BrandDomain | None
    name_flag: NameFlag | None
    work_reviewed: ResponseTime
    disputes: DisputeHistory


@dataclass(frozen=True)
class CreatorFacts:
    creator_id: uuid.UUID
    account_created_on: date
    delivery: DeliveryRecord
    memo_answered: ResponseTime
    payment_confirmed: ResponseTime
    disputes: DisputeHistory
    # Empty while the profile is withheld for legal reasons (item 52).
    profile_withheld: bool
    channels: list[CreatorChannel]
    connections: list[ConnectedAccount]


@dataclass(frozen=True)
class BetweenThem:
    """The deals the same brand and creator agreed before this one."""

    earlier_deals_agreed: int
    earlier_deals_finished: int

    @property
    def first_deal_together(self) -> bool:
        return self.earlier_deals_agreed == 0


@dataclass(frozen=True)
class DealCheck:
    deal_memo_id: uuid.UUID
    as_of: date
    # One of the two, by who reads: a creator reads about the brand, a brand
    # (its owner or a member) about the creator.
    about_brand: BrandFacts | None
    about_creator: CreatorFacts | None
    between: BetweenThem


@dataclass(frozen=True)
class _Pair:
    brand_id: uuid.UUID
    creator: Creator
    brand_account_created_at: datetime
    creator_account_created_at: datetime
    creator_withheld: bool


def _pair_of(db: Session, memo: DealMemo) -> _Pair:
    """The memo's brand and creator, in one query; MemoNotFound across a block.

    A brand's blocks are its owner's (D-148), so the brand's side of the
    block is `Brand.account_id`, whoever on the team reads.
    """
    brand_account = aliased(Account)
    creator_account = aliased(Account)
    row = db.execute(
        select(
            Campaign.brand_id,
            Creator,
            brand_account.created_at,
            creator_account.created_at,
            not_withheld("creator", Creator.id),
        )
        .select_from(Application)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .join(Brand, Brand.id == Campaign.brand_id)
        .join(Creator, Creator.id == Application.creator_id)
        .join(brand_account, brand_account.id == Brand.account_id)
        .join(creator_account, creator_account.id == Creator.account_id)
        .where(
            Application.id == memo.application_id,
            not_blocked(Brand.account_id, Creator.account_id),
        )
    ).first()
    if row is None:
        raise MemoNotFound()
    brand_id, creator, brand_created, creator_created, creator_not_withheld = row
    return _Pair(
        brand_id=brand_id,
        creator=creator,
        brand_account_created_at=brand_created,
        creator_account_created_at=creator_created,
        creator_withheld=not creator_not_withheld,
    )


def dispute_history(
    db: Session, side: ColumnElement[bool], today: date
) -> DisputeHistory:
    """The agreed deals matching `side`, and how each dispute among them ended.

    One query: every agreed deal with its dispute, if any (one payment record
    a deal, one dispute a payment record). Who opened a dispute is not read:
    it is a fact about the deal, never a finding about either side (D-028).
    """
    rows = db.execute(
        select(DealMemo.id, Dispute)
        .join(Application, Application.id == DealMemo.application_id)
        .join(Campaign, Campaign.id == Application.campaign_id)
        .outerjoin(PaymentStatus, PaymentStatus.deal_memo_id == DealMemo.id)
        .outerjoin(Dispute, Dispute.payment_status_id == PaymentStatus.id)
        .where(side, DealMemo.accepted_at.is_not(None))
    ).all()
    outcomes = dict.fromkeys(disputes.DISPUTE_STATES, 0)
    agreed = 0
    for _, dispute in rows:
        agreed += 1
        if dispute is not None:
            outcomes[disputes.derive_state(dispute, today)] += 1
    return DisputeHistory(
        deals_agreed=agreed,
        went_to_dispute=sum(outcomes.values()),
        outcomes=outcomes,
    )


def between(
    db: Session, memo: DealMemo, brand_id: uuid.UUID, creator_id: uuid.UUID, now: datetime
) -> BetweenThem:
    """The same brand and creator's deals agreed before this one, and how many finished.

    "Before" is before this memo was agreed, or before now while it is not:
    a deal they agree later is never counted as earlier. Finished is the
    deal stage's own (`stage.FINISHED`): paid and confirmed, or barter work
    approved. One query for the deals, and the stage's three or four.
    """
    agreed_before = memo.accepted_at or now
    earlier = list(
        db.scalars(
            select(DealMemo)
            .join(Application, Application.id == DealMemo.application_id)
            .join(Campaign, Campaign.id == Application.campaign_id)
            .where(
                Campaign.brand_id == brand_id,
                Application.creator_id == creator_id,
                DealMemo.id != memo.id,
                DealMemo.accepted_at < agreed_before,
            )
        ).all()
    )
    stages = stage.stages_for(db, earlier, now)
    return BetweenThem(
        earlier_deals_agreed=len(earlier),
        earlier_deals_finished=sum(
            1 for found in stages.values() if found.stage == stage.FINISHED
        ),
    )


def _brand_facts(db: Session, pair: _Pair, now: datetime) -> BrandFacts:
    today = india_date(now)
    return BrandFacts(
        brand_id=pair.brand_id,
        account_created_on=india_date(pair.brand_account_created_at),
        payment_record=reliability.for_brand(db, pair.brand_id, today),
        verified_domain=reliability.verified_domain_of(db, pair.brand_id),
        name_flag=reliability.name_flag_of(db, pair.brand_id),
        work_reviewed=response_times.for_brand(db, pair.brand_id).work_reviewed,
        disputes=dispute_history(db, Campaign.brand_id == pair.brand_id, today),
    )


def _creator_facts(db: Session, pair: _Pair, now: datetime) -> CreatorFacts:
    creator_id = pair.creator.id
    times = response_times.for_creator(db, creator_id)
    withheld = pair.creator_withheld
    return CreatorFacts(
        creator_id=creator_id,
        account_created_on=india_date(pair.creator_account_created_at),
        delivery=delivery_record.for_creator(db, creator_id, now),
        memo_answered=times.memo_answered,
        payment_confirmed=times.payment_confirmed,
        disputes=dispute_history(
            db, Application.creator_id == creator_id, india_date(now)
        ),
        profile_withheld=withheld,
        channels=[] if withheld else list_channels(db, pair.creator),
        connections=[] if withheld else connections.active_for(db, creator_id),
    )


def check(db: Session, memo: DealMemo, reader_role: str, now: datetime) -> DealCheck:
    """The check on `memo` as its reader sees it, as of `now`.

    The caller has already proven the reader is one of the memo's two parties
    (`dependencies.party_memo`). `reader_role` is the reader's account role:
    a brand's owner or member reads about the creator, the creator about the
    brand. Raises MemoNotFound across a block, either way.
    """
    pair = _pair_of(db, memo)
    brand_reads = reader_role == "brand"
    return DealCheck(
        deal_memo_id=memo.id,
        as_of=india_date(now),
        about_brand=None if brand_reads else _brand_facts(db, pair, now),
        about_creator=_creator_facts(db, pair, now) if brand_reads else None,
        between=between(db, memo, pair.brand_id, pair.creator.id, now),
    )
