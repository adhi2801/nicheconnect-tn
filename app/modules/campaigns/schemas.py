"""Request and response shapes for campaigns (backend.md sections 2 and 4)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.core.taxonomy import CURRENCY, MAX_NICHES, Niche
from app.core.text_flags import FieldFlag, field_flags
from app.modules.campaigns.models import (
    APPLICATION_ORIGINS,
    APPLICATION_STATUSES,
    BUDGETED_TYPES,
    CAMPAIGN_TYPES,
    DECLINE_REASONS,
    DELIVERABLES_MAX_LENGTH,
    DESCRIPTION_MAX_LENGTH,
    INVITATION_NOTE_MAX_LENGTH,
    MAX_CITIES,
    PITCH_MAX_LENGTH,
    PITCH_MIN_LENGTH,
    REJECTION_NOTE_MAX_LENGTH,
    REJECTION_REASONS,
    TITLE_MAX_LENGTH,
)

CampaignType = Literal["paid", "barter", "commission", "local_business"]
CampaignStatus = Literal["draft", "open", "closed", "cancelled"]

# The Literal above must stay in step with the database's allow-list.
ensure_same_values("CampaignType", CampaignType, CAMPAIGN_TYPES)

Title = Annotated[
    str,
    Field(min_length=1, max_length=TITLE_MAX_LENGTH, examples=["Pongal sweets launch"]),
]
Description = Annotated[str, Field(min_length=1, max_length=DESCRIPTION_MAX_LENGTH)]
Deliverables = Annotated[
    str,
    Field(
        min_length=1,
        max_length=DELIVERABLES_MAX_LENGTH,
        examples=["3 Instagram reels, 1 story set"],
    ),
]
City = Annotated[str, Field(min_length=2, max_length=60, examples=["Madurai"])]
Cities = Annotated[list[City], Field(min_length=1, max_length=MAX_CITIES)]
Niches = Annotated[list[Niche], Field(min_length=1, max_length=MAX_NICHES)]
Paise = Annotated[
    int,
    Field(gt=0, le=10_000_000_000, description="Whole paise, e.g. 500000 is Rs 5,000"),
]


def _check_budget(campaign_type: str, minimum: int | None, maximum: int | None) -> None:
    """The same rules the database enforces, with friendlier messages."""
    if (minimum is None) != (maximum is None):
        raise PydanticCustomError(
            "budget_incomplete", "Give both a minimum and a maximum budget, or neither"
        )
    if minimum is not None and maximum is not None and maximum < minimum:
        raise PydanticCustomError(
            "budget_backwards", "The maximum budget cannot be lower than the minimum"
        )
    if campaign_type == "barter" and minimum is not None:
        raise PydanticCustomError(
            "budget_on_barter", "A barter campaign pays in goods, so it has no budget"
        )
    if campaign_type in BUDGETED_TYPES and minimum is None:
        raise PydanticCustomError(
            "budget_required", "Give a budget range for this campaign type"
        )


class CampaignCreate(BaseModel):
    """What a brand sends to create a campaign. It starts as a draft."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Title
    description: Description
    campaign_type: CampaignType
    budget_min_paise: Paise | None = None
    budget_max_paise: Paise | None = None
    cities: Cities
    niches: Niches
    deliverables: Deliverables
    applications_close_on: date | None = None

    @model_validator(mode="after")
    def check_budget(self) -> CampaignCreate:
        _check_budget(self.campaign_type, self.budget_min_paise, self.budget_max_paise)
        return self


class CampaignUpdate(BaseModel):
    """Fields a brand may change. Anything left out stays as it is."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Title | None = None
    description: Description | None = None
    campaign_type: CampaignType | None = None
    budget_min_paise: Paise | None = None
    budget_max_paise: Paise | None = None
    cities: Cities | None = None
    niches: Niches | None = None
    deliverables: Deliverables | None = None
    applications_close_on: date | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> CampaignUpdate:
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class CampaignRead(BaseModel):
    """A campaign as the API returns it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    description: str
    campaign_type: CampaignType
    budget_min_paise: int | None
    budget_max_paise: int | None
    currency: Literal["INR"] = CURRENCY
    cities: list[str]
    niches: list[str]
    deliverables: str
    applications_close_on: date | None
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime

    @computed_field(  # type: ignore[prop-decorator]  # pydantic documents this
        description=(
            "Warnings on the free text above, worked out on every read: a request "
            "for money from a creator, or contact details before a deal is agreed "
            "(item 60). Show each beside its field; never hide the text"
        )
    )
    @property
    def text_flags(self) -> list[FieldFlag]:
        # Creators read a brief before any deal: money and contact both count.
        return field_flags(
            {"description": self.description, "deliverables": self.deliverables},
            money=True,
            contact=True,
        )


# --- applications --------------------------------------------------------

ApplicationStatus = Literal[
    "submitted",
    "shortlisted",
    "accepted",
    "rejected",
    "withdrawn",
    "invited",
    "declined",
]
ApplicationOrigin = Literal["applied", "invited"]
DeclineReason = Literal["timing", "budget", "not_a_fit", "other"]
RejectionReason = Literal[
    "budget_mismatch",
    "audience_mismatch",
    "timing",
    "chose_another_creator",
    "incomplete_profile",
    "other",
]

ensure_same_values("ApplicationStatus", ApplicationStatus, APPLICATION_STATUSES)
ensure_same_values("RejectionReason", RejectionReason, REJECTION_REASONS)
ensure_same_values("ApplicationOrigin", ApplicationOrigin, APPLICATION_ORIGINS)
ensure_same_values("DeclineReason", DeclineReason, DECLINE_REASONS)

Pitch = Annotated[
    str,
    Field(
        min_length=PITCH_MIN_LENGTH,
        max_length=PITCH_MAX_LENGTH,
        description="Why you are a good fit for this campaign",
        examples=["I run a Madurai street-food page with 12k local followers..."],
    ),
]
RejectionNote = Annotated[str, Field(max_length=REJECTION_NOTE_MAX_LENGTH)]


class ApplicationCreate(BaseModel):
    """What a creator sends to apply."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pitch: Pitch
    quoted_amount_paise: Paise | None = None


class ApplicationReject(BaseModel):
    """Why a brand said no. The reason is a code so the creator sees it clearly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: RejectionReason
    note: RejectionNote | None = None


InvitationNote = Annotated[
    str,
    Field(
        min_length=1,
        max_length=INVITATION_NOTE_MAX_LENGTH,
        description="A few words from the brand, shown with the invitation",
        examples=["Loved your Madurai food walks. Our Pongal box would suit them."],
    ),
]


class InvitationCreate(BaseModel):
    """A brand invites one creator to one of its open campaigns (D-084)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    creator_id: uuid.UUID = Field(description="From search or a match")
    note: InvitationNote | None = None


class RepeatCreate(BaseModel):
    """Work together again: the same creator, invited to another open campaign."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campaign_id: uuid.UUID = Field(description="One of your open campaigns")
    note: InvitationNote | None = None


class InvitationDecline(BaseModel):
    """Why a creator said no. A code, so the brand sees it clearly."""

    model_config = ConfigDict(extra="forbid")

    reason: DeclineReason


class ApplicationRead(BaseModel):
    """A creator on a campaign, whether they applied or were invited.

    `origin` says which. An invitation has no `pitch`; it may carry the
    brand's `invitation_note`. `repeat_of_application_id` names the earlier
    deal a repeat invitation repeats. Clients must tolerate statuses they do
    not know: `invited` and `declined` were added on 10 October 2026.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    creator_id: uuid.UUID
    origin: ApplicationOrigin
    pitch: str | None = Field(description="Null for an invitation")
    invitation_note: str | None
    repeat_of_application_id: uuid.UUID | None
    quoted_amount_paise: int | None
    currency: Literal["INR"] = CURRENCY
    status: ApplicationStatus
    rejection_reason: RejectionReason | None
    rejection_note: str | None
    decline_reason: DeclineReason | None
    status_changed_at: datetime
    created_at: datetime
    updated_at: datetime

    @computed_field(  # type: ignore[prop-decorator]  # pydantic documents this
        description=(
            "Warnings on the free text above, worked out on every read: a request "
            "for money from a creator, or contact details before a deal is agreed "
            "(item 60). Show each beside its field; never hide the text"
        )
    )
    @property
    def text_flags(self) -> list[FieldFlag]:
        before_a_deal = self.status != "accepted"
        # The brand's words reach a creator: money and contact. A creator
        # naming their own price in a pitch is ordinary, so only contact.
        return [
            *field_flags(
                {
                    "invitation_note": self.invitation_note,
                    "rejection_note": self.rejection_note,
                },
                money=True,
                contact=before_a_deal,
            ),
            *field_flags({"pitch": self.pitch}, money=False, contact=before_a_deal),
        ]


class ApplicationFeedbackRead(BaseModel):
    """Why a creator's applications are not turning into deals (backlog C4).

    Facts with their sample sizes, never advice: the words belong to the
    frontend, in Tamil and English. `most_common_reason` is `null` below
    three rejections or on a tie, which means **no pattern yet**, not "no
    problem".
    """

    as_of: date = Field(description="The Tamil Nadu date these figures describe")
    applications: int
    by_status: dict[ApplicationStatus, int] = Field(
        description="Every status, zeros included"
    )
    rejections: int
    rejections_by_reason: dict[RejectionReason, int] = Field(
        description="Every reason a brand can give, zeros included"
    )
    most_common_reason: RejectionReason | None = Field(
        description="Null below three rejections, or when two reasons tie"
    )
    quotes_compared: int = Field(
        description="Applications where you quoted and the campaign stated a maximum budget"
    )
    quotes_above_budget: int = Field(
        description="Of those, how many quotes were above the campaign's own maximum"
    )
    open_campaigns_in_your_niches: int = Field(
        description="Open, still taking applications, and not yet applied to"
    )
    open_campaigns_in_your_niches_and_city: int
    has_bio: bool
    passport_published: bool = Field(
        description="A fact, not a to-do: publishing is the creator's choice (D-036)"
    )


# --- a campaign at a glance (D-076) --------------------------------------------------------


class ApplicationCountsRead(BaseModel):
    """How many applications are in each status. Every status, zeros included."""

    submitted: int
    shortlisted: int
    accepted: int
    rejected: int
    withdrawn: int
    invited: int = Field(description="Invitations still waiting for an answer")
    declined: int = Field(description="Invitations the creator said no to")


class DealStageCountsRead(BaseModel):
    """How many deals stand at each stage, worked out as of the request."""

    draft: int
    memo_sent: int
    agreed: int
    in_progress: int
    payment: int
    finished: int
    declined: int
    cancelled: int


class CampaignSummaryRead(BaseModel):
    """One campaign at a glance, for its board and the Campaigns list.

    `deals_agreed` counts deals agreed and not cancelled; "2 of 6 deals
    finished" is `deals_finished` of `deals_agreed`. `complete` is worked
    out, never stored: closed, at least one deal agreed, every agreed deal
    finished and no memo left unanswered.
    """

    campaign_id: uuid.UUID
    status: CampaignStatus
    applications: ApplicationCountsRead
    deals_by_stage: DealStageCountsRead
    deals_agreed: int
    deals_finished: int
    deals_waiting_on_brand: int
    complete: bool
