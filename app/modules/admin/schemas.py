"""Request and response shapes for the admin API, the founders' numbers and user reports (D-099)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.modules.admin.models.admin_action import ADMIN_ACTIONS
from app.modules.admin.models.report import REPORT_SUBJECTS
from app.modules.auth.models.account import REPORT_CATEGORIES
from app.modules.auth.schemas import DEVICE_FIELD, DeviceIn, IndianMobile, OtpCode, Role
from app.modules.safety.takedown_models import (
    ORDER_TEXT_MAX_LENGTH,
    TAKEDOWN_BASES,
    TAKEDOWN_SUBJECTS,
)

ReportSubject = Literal["creator", "brand", "campaign"]
ReportCategory = Literal[
    "fake_profile",
    "spam",
    "abuse",
    "non_payment",
    "other",
    "impersonation",
    "intimate_content",
]
AdminNote = Annotated[str, Field(min_length=3, max_length=1000)]

# The API's lists must be exactly the database's, or startup fails.
ensure_same_values("ReportCategory", ReportCategory, REPORT_CATEGORIES)
ensure_same_values("ReportSubject", ReportSubject, REPORT_SUBJECTS)
# A takedown names what a report can name (item 52).
ensure_same_values("TakedownSubject", ReportSubject, TAKEDOWN_SUBJECTS)


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject_kind: ReportSubject
    subject_id: uuid.UUID
    category: ReportCategory = Field(
        description=(
            "What is wrong. `impersonation`: someone is pretending to be you. "
            "`intimate_content`: something shows you undressed or sexually, "
            "real or made up. Both are answered within 2 hours; `abuse`, "
            "`fake_profile`, `spam` and `other` within 36 hours; `non_payment` "
            "within 7 days (item 51). Clients tolerate values they do not know"
        )
    )
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
    due_at: datetime = Field(
        description=(
            "When it will be answered by: the deadline the IT Rules set for its "
            "category, fixed when it was filed (item 51)"
        )
    )
    resolved_at: datetime | None = Field(
        description="When an admin resolved it; null while it is open (item 102)"
    )


class AdminReportRead(ReportRead):
    reporter_account_id: uuid.UUID
    resolution_note: str | None
    late: bool = Field(description="Answered after `due_at`, or still open past it")


class ReportClockRead(BaseModel):
    category: ReportCategory
    answer_within_hours: int = Field(description="The IT Rules' clock for it")


class ReportClocksRead(BaseModel):
    """The report queue against its legal clocks (item 51). Totals only."""

    as_of: datetime
    open: int
    open_late: int = Field(description="Open, and past their deadline now")
    next_due_at: datetime | None = Field(
        description="The earliest deadline among open reports; null when none is open"
    )
    days: int = Field(description="How far back the answered figures look")
    answered: int = Field(description="Resolved in the last `days` days")
    answered_in_time: int = Field(description="Of those, resolved by their deadline")
    answered_in_time_share: float | None = Field(
        description="answered_in_time / answered; null below 5 answered (D-056)"
    )
    clocks: list[ReportClockRead] = Field(
        description="Every category's clock, shortest first: at most 7"
    )


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
    action: Literal[
        "view_account",
        "suspend",
        "restore",
        "resolve_report",
        "withhold",
        "lift_withhold",
        "clear_brand_name",
        "withdraw_brand_name_clearance",
    ]
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


OrderText = Annotated[str, Field(min_length=3, max_length=ORDER_TEXT_MAX_LENGTH)]
TakedownBasis = Literal["court_order", "government_notice", "report"]


class TakedownCreate(BaseModel):
    """Withhold one item (item 52): on an order, or on a report.

    An order (`court_order`, `government_notice`) gives `issued_by`,
    `order_reference` and `received_at`, and may give `legal_provision`,
    `reference_sealed` and a `report_id`. A report gives `report_id`, about
    this same item, and none of the order's fields.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject_kind: ReportSubject = Field(
        description=(
            "`creator`: their profile and Passport. `brand`: the brand and every "
            "campaign it posts, now and later. `campaign`: that one campaign"
        )
    )
    subject_id: uuid.UUID
    basis: TakedownBasis = Field(
        description=(
            "`court_order`, or `government_notice` from an authorised officer: "
            "rule 3(1)(d), 3 hours from `received_at`. `report`: withheld while "
            "an admin looks into a report, which keeps its own deadline (item 51)"
        )
    )
    issued_by: OrderText | None = Field(
        default=None,
        description="The court, or the authority and its officer's designation",
        examples=["Deputy Inspector General of Police, Cyber Crime, Chennai"],
    )
    order_reference: Annotated[
        str | None, Field(min_length=1, max_length=ORDER_TEXT_MAX_LENGTH)
    ] = Field(default=None, description="The order's or notice's number")
    legal_provision: OrderText | None = Field(
        default=None,
        description="The law it cites, where it cites one",
        examples=["IT Act 2000, section 79(3)(b)"],
    )
    reference_sealed: bool = Field(
        default=False,
        description="The order may not be shown to the owner: they see only that it exists",
    )
    received_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "When the order reached us, as the order or its email shows: the "
            "3-hour clock runs from here. In the last 30 days, not in the future"
        ),
    )
    report_id: uuid.UUID | None = Field(
        default=None,
        description="The report about this item: required for `report`, optional for an order",
    )
    note: AdminNote = Field(description="Why, for the admin log. The owner never sees it")

    @model_validator(mode="after")
    def fields_match_basis(self) -> TakedownCreate:
        order_fields = (self.issued_by, self.order_reference, self.received_at)
        if self.basis == "report":
            given = (*order_fields, self.legal_provision)
            if (
                self.report_id is None
                or any(value is not None for value in given)
                or self.reference_sealed
            ):
                raise PydanticCustomError(
                    "takedown_report_fields",
                    "A takedown on a report gives report_id, and no order details",
                )
        elif any(value is None for value in order_fields):
            raise PydanticCustomError(
                "takedown_order_fields",
                "An order gives issued_by, order_reference and received_at",
            )
        return self

    def order_essentials(self) -> tuple[str, str, datetime]:
        """An order's issued_by, order_reference and received_at, typed.

        The validator above guarantees them for an order; this says so to the
        type checker without an `assert`, which `-O` would remove.
        """
        if (
            self.issued_by is None
            or self.order_reference is None
            or self.received_at is None
        ):
            raise ValueError("Not an order: it has no order details")
        return self.issued_by, self.order_reference, self.received_at


class LiftTakedownIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: AdminNote = Field(
        description="Why: the order withdrawn or set aside, or the report dismissed"
    )


class AdminTakedownRead(BaseModel):
    """A takedown as an admin sees it: the order, the clock and the preserved text."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_kind: ReportSubject
    subject_id: uuid.UUID
    owner_account_id: uuid.UUID
    basis: TakedownBasis
    issued_by: str | None
    order_reference: str | None
    legal_provision: str | None
    reference_sealed: bool
    report_id: uuid.UUID | None
    received_at: datetime = Field(
        description="When the order reached us, or the report was filed"
    )
    due_at: datetime = Field(
        description=(
            "3 hours after `received_at` for an order; the report's own deadline "
            "for a report"
        )
    )
    withheld_at: datetime = Field(description="When it was withheld: the server's clock")
    late: bool = Field(description="Withheld after `due_at`")
    withheld_by_account_id: uuid.UUID
    lifted_at: datetime | None
    lifted_by_account_id: uuid.UUID | None
    preserved: dict[str, Any] = Field(
        description=(
            "The item's visible text when it was withheld, kept as the IT Rules "
            "ask (rule 3(1)(g)): later edits cannot change it"
        )
    )


ensure_same_values("TakedownBasis", TakedownBasis, TAKEDOWN_BASES)

# The admin log's action names must match the database allow-list.
ensure_same_values(
    "AdminActionKind", AdminActionRead.model_fields["action"].annotation, ADMIN_ACTIONS
)


# --- the admins' login, with two factors (item 101, D-105) ------------------------------

AuthenticatorCode = Annotated[
    str,
    Field(
        pattern=r"^[0-9]{6}$",
        description="The 6-digit code the authenticator app shows now",
        examples=["492039"],
    ),
]
SetupTicket = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9_-]{32}$",
        description="The setup ticket a founder issued with scripts/make_admin.py",
        examples=["example_ticket_not_a_real_one_01"],
    ),
]


class AdminLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile
    code: OtpCode
    authenticator_code: AuthenticatorCode
    device: DeviceIn | None = DEVICE_FIELD


class SecondFactorSetupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile
    code: OtpCode
    ticket: SetupTicket


class SecondFactorSetupRead(BaseModel):
    """Shown once. Nothing here can be read again, by anyone."""

    secret: str = Field(
        description="The secret, base32, for typing into an authenticator app",
        examples=["JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"],
    )
    setup_link: str = Field(
        description="The same secret as an otpauth:// link, for a QR code",
        examples=[
            "otpauth://totp/NicheConnect%20TN:admin-1f0c2a9b"
            "?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=NicheConnect%20TN"
        ],
    )
    digits: Literal[6] = 6
    period_seconds: Literal[30] = 30
    algorithm: Literal["SHA1"] = "SHA1"


# --- look-alike brand names (item 75, D-118) ---------------------------------------------


class LookAlikeBrandRead(BaseModel):
    """A brand whose name looks like a protected brand's, as an admin sees it."""

    brand_id: uuid.UUID
    account_id: uuid.UUID = Field(
        description="To open the account at /api/v1/admin/accounts/{id}"
    )
    name: str
    created_at: datetime
    resembles_name: str | None
    resembles_domain: str | None
    mixed_script: bool


class LookAlikeListRead(BaseModel):
    items: list[LookAlikeBrandRead]
    truncated: bool = Field(description="True when more than the 100 listed are flagged")


class NameClearanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: str = Field(
        min_length=3,
        max_length=1000,
        description="What you checked and why the name is genuine. Written to the admin log",
        examples=[
            "Spoke to the owner; a Coimbatore bakery since 2011, no relation to Nykaa."
        ],
    )


class NameClearanceRead(BaseModel):
    """A brand's name, and whether an admin cleared it as it stands now."""

    brand_id: uuid.UUID
    name: str
    name_cleared: bool = Field(
        description="True while the brand keeps the name that was cleared"
    )
    name_cleared_at: datetime | None
