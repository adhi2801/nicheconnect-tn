"""The pre-deal check's answer (item 133, D-182), built field by field.

Facts only: counts with the number they rest on, dates, and figures null
below their floor. No field names a quality of a person or business, and
nothing is combined into a score (`legal.md` sections 1 and 3.12).
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.clock import india_date
from app.modules.auth.schemas import ChannelRead
from app.modules.deal_memo.check_service import (
    BetweenThem,
    BrandFacts,
    CreatorFacts,
    DealCheck,
    DisputeHistory,
)
from app.modules.deal_memo.schemas import (
    CreatorDeliveryRead,
    ResponseTimeRead,
    to_delivery_read,
    to_response_time_read,
)
from app.modules.disputes.service import DISPUTE_STATES
from app.modules.payment_status.schemas import BrandReliabilityRead, to_reliability_read
from app.modules.profiles.connection_models import ConnectedAccount
from app.modules.profiles.schemas import ConnectedPlatform


class DisputeOutcomesRead(BaseModel):
    """How each dispute ended, or where it stands. A fact about the dispute,
    never a finding about either side (D-028)."""

    open: int = Field(ge=0, description="Raised, inside its 30 days, no outcome yet")
    unresolved: int = Field(
        ge=0,
        description=(
            "Thirty days passed with no outcome agreed: a fact about the "
            "dispute, not a finding about either of you"
        ),
    )
    resolved_paid: int = Field(ge=0, description="Ended with the money arriving")
    resolved_withdrawn: int = Field(ge=0, description="Withdrawn by whoever raised it")
    resolved_informally: int = Field(ge=0, description="Settled between the two of them")


# A dispute state added later must be added here too: checked at import, so
# the app refuses to start rather than answer 500 on every check.
if set(DisputeOutcomesRead.model_fields) != set(DISPUTE_STATES):
    raise RuntimeError("DisputeOutcomesRead must name exactly the dispute states")


class DisputeHistoryRead(BaseModel):
    """The deals this side agreed, and how many of them went to a dispute.

    Counts, reported always, beside the number they rest on. Who raised a
    dispute is never shown.
    """

    deals_agreed: int = Field(
        ge=0,
        description="Deals this side agreed (a memo accepted): the count below rests on it",
    )
    went_to_dispute: int = Field(
        ge=0, description="Of those, how many went to a dispute about the payment"
    )
    outcomes: DisputeOutcomesRead


class CheckConnectionRead(BaseModel):
    """A connected account (D-134), with the count the platform itself reported.

    `connected_since` is a Tamil Nadu date, as every date in the check is.
    """

    platform: ConnectedPlatform
    handle: str
    connected_since: date
    verified_followers: int | None = Field(
        description="The platform's own count; null when the platform hides it, never 0"
    )
    verified_as_of: datetime | None


class BrandCheckRead(BaseModel):
    """What a creator reads about the brand before agreeing."""

    brand_id: uuid.UUID
    account_created_on: date = Field(
        description=(
            "The Tamil Nadu date the account that owns the brand was created; "
            "after a hand-over (D-151), the new owner's account"
        )
    )
    payment_record: BrandReliabilityRead = Field(
        description=(
            "How the brand pays, with its verified domain (the registry's date "
            "for it in `registered_on`) and the look-alike name flag, as "
            "`GET /brands/{brand_id}/reliability` answers"
        )
    )
    work_reviewed: ResponseTimeRead = Field(
        description="How long the brand takes to decide on submitted work"
    )
    disputes: DisputeHistoryRead


class CreatorCheckRead(BaseModel):
    """What a brand reads about the creator before agreeing."""

    creator_id: uuid.UUID
    account_created_on: date = Field(
        description="The Tamil Nadu date the creator's account was created"
    )
    delivery_record: CreatorDeliveryRead
    memo_answered: ResponseTimeRead = Field(
        description="How long the creator takes to answer a memo"
    )
    payment_confirmed: ResponseTimeRead = Field(
        description="How long the creator takes to confirm a payment arrived"
    )
    disputes: DisputeHistoryRead
    profile_withheld: bool = Field(
        description=(
            "True while the creator's profile is withheld for legal reasons "
            "(item 52): its channels and connected accounts are then left out"
        )
    )
    channels: list[ChannelRead] = Field(
        description=(
            "The creator's own claim, each dated by `figures_as_of`, and shown "
            "as self-reported"
        )
    )
    connected_accounts: list[CheckConnectionRead] = Field(
        description=(
            "Accounts the creator connected, with the platform's own count: "
            "shown beside the channel's stated count, never instead"
        )
    )


class BetweenYouRead(BaseModel):
    """The same brand and creator's deals agreed before this one."""

    first_deal_together: bool = Field(
        description="True when the two of you agreed no deal before this one"
    )
    earlier_deals_agreed: int = Field(
        ge=0,
        description=(
            "Deals the two of you agreed before this one was agreed (or before "
            "now, while it is not)"
        ),
    )
    earlier_deals_finished: int = Field(
        ge=0,
        description="Of those, how many finished: paid and confirmed, or barter work approved",
    )


class DealCheckRead(BaseModel):
    """Facts about the other side of a deal, from our records, as of a Tamil Nadu date.

    Exactly one of `about_brand` (for the creator) and `about_creator` (for
    the brand) is set. Every share and median is null below its floor,
    meaning **not enough to say**, and must never be shown as 0. Nothing here
    is a score, and nothing stops either side agreeing.
    """

    deal_memo_id: uuid.UUID
    as_of: date = Field(description="The Tamil Nadu date these facts were read")
    about_brand: BrandCheckRead | None = Field(
        description="Set when the creator reads; null for the brand"
    )
    about_creator: CreatorCheckRead | None = Field(
        description="Set when the brand reads; null for the creator"
    )
    between_you: BetweenYouRead


def _disputes_read(found: DisputeHistory) -> DisputeHistoryRead:
    return DisputeHistoryRead(
        deals_agreed=found.deals_agreed,
        went_to_dispute=found.went_to_dispute,
        outcomes=DisputeOutcomesRead(**found.outcomes),
    )


def _connection_read(row: ConnectedAccount) -> CheckConnectionRead:
    return CheckConnectionRead(
        platform=row.platform,
        handle=row.handle,
        connected_since=india_date(row.connected_at),
        verified_followers=row.verified_followers,
        verified_as_of=row.verified_as_of,
    )


def _brand_read(facts: BrandFacts) -> BrandCheckRead:
    return BrandCheckRead(
        brand_id=facts.brand_id,
        account_created_on=facts.account_created_on,
        payment_record=to_reliability_read(
            facts.payment_record, facts.verified_domain, facts.name_flag
        ),
        work_reviewed=to_response_time_read(facts.work_reviewed),
        disputes=_disputes_read(facts.disputes),
    )


def _creator_read(facts: CreatorFacts) -> CreatorCheckRead:
    return CreatorCheckRead(
        creator_id=facts.creator_id,
        account_created_on=facts.account_created_on,
        delivery_record=to_delivery_read(facts.delivery),
        memo_answered=to_response_time_read(facts.memo_answered),
        payment_confirmed=to_response_time_read(facts.payment_confirmed),
        disputes=_disputes_read(facts.disputes),
        profile_withheld=facts.profile_withheld,
        channels=[ChannelRead.model_validate(c) for c in facts.channels],
        connected_accounts=[_connection_read(c) for c in facts.connections],
    )


def _between_read(found: BetweenThem) -> BetweenYouRead:
    return BetweenYouRead(
        first_deal_together=found.first_deal_together,
        earlier_deals_agreed=found.earlier_deals_agreed,
        earlier_deals_finished=found.earlier_deals_finished,
    )


def to_check_read(found: DealCheck) -> DealCheckRead:
    return DealCheckRead(
        deal_memo_id=found.deal_memo_id,
        as_of=found.as_of,
        about_brand=None if found.about_brand is None else _brand_read(found.about_brand),
        about_creator=(
            None if found.about_creator is None else _creator_read(found.about_creator)
        ),
        between_you=_between_read(found.between),
    )
