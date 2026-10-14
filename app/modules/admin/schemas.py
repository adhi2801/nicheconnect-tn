"""Request and response shapes for the admin API, the founders' numbers and user reports (D-099)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.core.literals import ensure_same_values
from app.modules.admin.models.admin_action import ADMIN_ACTIONS
from app.modules.admin.models.report import REPORT_SUBJECTS
from app.modules.auth.models.account import REPORT_CATEGORIES
from app.modules.auth.schemas import Role

ReportSubject = Literal["creator", "brand", "campaign"]
ReportCategory = Literal["fake_profile", "spam", "abuse", "non_payment", "other"]
AdminNote = Annotated[str, Field(min_length=3, max_length=1000)]

# The API's lists must be exactly the database's, or startup fails.
ensure_same_values("ReportCategory", ReportCategory, REPORT_CATEGORIES)
ensure_same_values("ReportSubject", ReportSubject, REPORT_SUBJECTS)


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject_kind: ReportSubject
    subject_id: uuid.UUID
    category: ReportCategory
    note: Annotated[str | None, Field(default=None, max_length=1000)]


class ReportRead(BaseModel):
    """A report, as the person who made it sees it. Who handled it is not shown."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_kind: ReportSubject
    subject_id: uuid.UUID
    category: ReportCategory
    note: str | None
    status: Literal["open", "actioned", "dismissed"] = Field(
        description="`actioned`: an admin acted on it. `dismissed`: looked at, no action"
    )
    created_at: datetime
    resolved_at: datetime | None = Field(
        description="When an admin resolved it; null while it is open (item 102)"
    )


class AdminReportRead(ReportRead):
    reporter_account_id: uuid.UUID
    resolution_note: str | None


class AdminProfileRead(BaseModel):
    kind: Literal["brand", "creator"]
    id: uuid.UUID
    name: str = Field(description="The brand's name, or the creator's display name")
    handle: str | None = Field(description="A creator's handle")


class AdminAccountRead(BaseModel):
    """An account as an admin sees it. Viewing it is written to the admin log."""

    id: uuid.UUID
    role: Role
    phone: str
    created_at: datetime
    suspended_at: datetime | None
    suspension_reason: ReportCategory | None
    profile: AdminProfileRead | None
    deals: int = Field(description="Deal memos this account is a party to")
    reports_about_open: int
    reports_about_total: int
    reports_made: int


class SuspendIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: ReportCategory = Field(description="The category the person is told")
    note: AdminNote = Field(
        description="Why, for the admin log. The person never sees it"
    )


class RestoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: AdminNote


class ResolveReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    outcome: Literal["actioned", "dismissed"]
    note: AdminNote


class AdminActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_account_id: uuid.UUID
    action: Literal["view_account", "suspend", "restore", "resolve_report"]
    subject_account_id: uuid.UUID | None
    report_id: uuid.UUID | None
    note: str | None
    created_at: datetime


class PeriodNumbersRead(BaseModel):
    """One period's numbers. Every rate is null below five examples."""

    model_config = ConfigDict(from_attributes=True)

    from_on: date = Field(description="First Tamil Nadu day of the period")
    to_on: date = Field(description="Last Tamil Nadu day of the period")
    new_brands: int = Field(description="Brand profiles created (all cities)")
    new_creators: int
    active_brands: int = Field(
        description="Brands that posted a campaign or agreed a deal"
    )
    active_creators: int = Field(description="Creators who applied or agreed a deal")
    campaigns_posted: int = Field(description="Campaigns created and no longer in draft")
    campaigns_old_enough_to_judge: int = Field(
        description="Of those, posted at least 14 days before the period ended"
    )
    campaigns_filled_within_14_days: int
    campaign_fill_rate: float | None = Field(
        description="Filled of old enough to judge; the headline number for density"
    )
    median_hours_to_first_application: float | None
    applications_sent: int = Field(description="Applications creators chose to send")
    applications_accepted_so_far: int
    application_success_so_far: float | None = Field(
        description="Accepted so far; recent applications may still be decided"
    )
    invitations_sent: int
    deals_agreed: int = Field(description="Deal memos accepted by both sides")
    value_of_deals_agreed_paise: int = Field(
        description="The fees of those deals. Paid brand to creator, never through us"
    )
    repeat_deals: int = Field(
        description="Deals between a brand and a creator who had agreed one before"
    )
    repeat_share: float | None
    payments_confirmed: int = Field(description="Payments the creator confirmed arriving")
    paid_on_time: int = Field(description="Of those, marked paid by the due date")
    paid_on_time_share: float | None


class FounderNumbersRead(BaseModel):
    """The founders' weekly numbers, beside the period before them.

    `docs/SURVIVAL_PLAYBOOK.md` section 4 says what each tells you. Totals
    only: nothing here names or describes a person.
    """

    model_config = ConfigDict(from_attributes=True)

    as_of: date
    days: int
    city: str | None = Field(description="Lower-cased; null means every city")
    current: PeriodNumbersRead
    previous: PeriodNumbersRead


# The admin log's action names must match the database allow-list.
ensure_same_values(
    "AdminActionKind", AdminActionRead.model_fields["action"].annotation, ADMIN_ACTIONS
)
