"""Request and response shapes for OTP login (backend.md section 4)."""

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.attention import BRAND_KINDS, CREATOR_KINDS, AttentionList
from app.core.literals import ensure_same_values
from app.core.taxonomy import CURRENCY, LANGUAGES, MAX_NICHES, Language, Niche
from app.modules.auth.models.account import (
    ACCOUNT_ROLES,
    PHONE_PATTERN,
    REPORT_CATEGORIES,
)
from app.modules.auth.models.admin_action import ADMIN_ACTIONS
from app.modules.auth.models.attribution import ARRIVAL_SOURCES
from app.modules.auth.models.creator import BIO_MAX_LENGTH, HANDLE_PATTERN
from app.modules.auth.models.report import REPORT_SUBJECTS

# The media kit nests the delivery record as its own module defines it, so
# the two can never describe the same numbers differently.
from app.modules.deal_memo.schemas import CreatorDeliveryRead

# Separators people commonly type: "+91 98765 43210", "98765-43210", "(98765) 43210".
_PHONE_SEPARATORS = re.compile(r"[\s\-()]")
_TEN_DIGIT_MOBILE = re.compile(r"^[6-9][0-9]{9}$")


def normalize_indian_mobile(value: object) -> str:
    """Turn common ways of typing an Indian mobile into E.164 (+91XXXXXXXXXX)."""
    if not isinstance(value, str):
        raise PydanticCustomError("phone_type", "Enter the mobile number as text")
    digits = _PHONE_SEPARATORS.sub("", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _TEN_DIGIT_MOBILE.fullmatch(digits):
        raise PydanticCustomError(
            "phone_invalid", "Enter a valid 10-digit Indian mobile number"
        )
    return f"+91{digits}"


def _check_e164(value: str) -> str:
    # Same rule the database enforces (ck_account_phone_format).
    if not re.fullmatch(PHONE_PATTERN, value):
        raise PydanticCustomError(
            "phone_invalid", "Enter a valid 10-digit Indian mobile number"
        )
    return value


# Published on the schema as well as enforced here, so a client generating
# requests from our OpenAPI document cannot produce a code we always refuse.
OTP_CODE_PATTERN = r"^[0-9]{6}$"


def _check_code(value: object) -> str:
    code = value.strip() if isinstance(value, str) else value
    if not isinstance(code, str) or not re.fullmatch(OTP_CODE_PATTERN, code):
        raise PydanticCustomError("code_invalid", "Enter the 6-digit code we sent you")
    return code


# The pattern is published through json_schema_extra rather than Field's own
# `pattern`. A BeforeValidator makes the accepted input wider than the stored
# form, so Pydantic correctly refuses to publish a constraint on it and drops
# `pattern` from the validation schema, where the request body is described.
# Publishing nothing told a generated client that any string would do, and it
# earned a 422 on data our own document called valid.
#
# What is published is the canonical form, the one the database enforces too:
# what a client should send. The wider input the description lists keeps
# working, so the document is stricter than the code, never looser.
IndianMobile = Annotated[
    str,
    BeforeValidator(normalize_indian_mobile),
    AfterValidator(_check_e164),
    Field(
        description=(
            "Indian mobile number, stored as +91XXXXXXXXXX. Send it in that "
            "form. Spaces, dashes and brackets, and a leading +91, 91 or 0, "
            "are also accepted and normalised away."
        ),
        json_schema_extra={"pattern": PHONE_PATTERN},
        examples=["+919876543210"],
    ),
]
OtpCode = Annotated[
    str,
    BeforeValidator(_check_code),
    Field(
        description="The 6-digit code sent to the phone",
        json_schema_extra={"pattern": OTP_CODE_PATTERN},
        examples=["042917"],
    ),
]
# "admin" logs in like everyone else but is never created by login (D-061).
Role = Literal["brand", "creator", "admin"]


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile


class OtpRequestAccepted(BaseModel):
    expires_in_seconds: int = Field(examples=[300])


ArrivalSource = Literal[
    "passport_link", "instagram", "whatsapp", "event", "search", "other"
]

# The sources a person may name. `invite` comes only from a valid code, and
# `not_given` only from silence.
ensure_same_values(
    "ArrivalSource",
    ArrivalSource,
    tuple(s for s in ARRIVAL_SOURCES if s not in ("invite", "not_given")),
)


class ArrivalIn(BaseModel):
    """How a new person found us (D-080). Read only when the login creates the
    account; a returning login ignores it, so nobody can rewrite how they came."""

    model_config = ConfigDict(extra="forbid")

    invite_code: str | None = Field(
        default=None,
        max_length=16,
        pattern=r"^[A-Za-z0-9 -]+$",
        description=(
            "Someone's invite code, as typed. An unknown code is ignored, never "
            "refused: a typo must not block sign-up"
        ),
        examples=["K7PQ2XMA"],
    )
    source: ArrivalSource | None = Field(
        default=None, description="Where the person says they heard of us"
    )
    campaign_tag: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9-]{1,40}$",
        description="The label on the link or poster they came from",
        examples=["codissia-oct"],
    )


class OtpVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile
    code: OtpCode
    role: Role = Field(
        description=(
            "Which app is logging in. `admin` logs in only to an admin account "
            "that already exists; it never creates one"
        ),
        examples=["creator"],
    )
    arrival: ArrivalIn | None = Field(
        default=None,
        description="Optional, and read only when this login creates the account",
    )


class AccountSummary(BaseModel):
    id: uuid.UUID
    role: Role
    is_new: bool = Field(description="True when this login created the account")


class LoginTokens(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth scheme name, not a secret
    expires_in: int = Field(
        description="Access token lifetime in seconds", examples=[900]
    )
    refresh_token: str
    refresh_expires_in: int = Field(
        description="Refresh token lifetime in seconds", examples=[2592000]
    )
    account: AccountSummary


# A refresh token is secrets.token_urlsafe(32), i.e. 43 URL-safe characters.
RefreshToken = Annotated[
    str,
    Field(
        min_length=20,
        max_length=512,
        description="The refresh token from a login or an earlier refresh",
    ),
]


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: RefreshToken


class LogoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: RefreshToken


class AccountRead(BaseModel):
    """The signed-in account, returned to its owner only."""

    id: uuid.UUID
    role: Role
    phone: IndianMobile
    created_at: datetime


class LoggedOutAll(BaseModel):
    sessions_ended: int = Field(
        description="How many sessions were still active", examples=[3]
    )


# --- profiles ------------------------------------------------------------

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def _normalize_email(value: object) -> str:
    """Trim and lowercase; the database stores lowercase only (D-006)."""
    if not isinstance(value, str):
        raise PydanticCustomError("email_type", "Enter the email address as text")
    email = value.strip().lower()
    if not _EMAIL_PATTERN.fullmatch(email) or len(email) > 320:
        raise PydanticCustomError("email_invalid", "Enter a valid email address")
    return email


def _normalize_handle(value: object) -> str:
    """Trim, drop a leading @, lowercase; handles are stored lowercase."""
    if not isinstance(value, str):
        raise PydanticCustomError("handle_type", "Enter the handle as text")
    handle = value.strip().lstrip("@").lower()
    if not re.fullmatch(HANDLE_PATTERN, handle):
        raise PydanticCustomError(
            "handle_invalid",
            "Use 3 to 30 characters: lowercase letters, numbers, dots or underscores",
        )
    return handle


BrandName = Annotated[str, Field(min_length=1, max_length=150, examples=["Amma Sweets"])]
BrandEmail = Annotated[
    str, BeforeValidator(_normalize_email), Field(examples=["hello@ammasweets.in"])
]
CreatorName = Annotated[str, Field(min_length=1, max_length=100, examples=["Priya Eats"])]
Handle = Annotated[
    str, BeforeValidator(_normalize_handle), Field(examples=["priya.eats"])
]
CreatorCity = Annotated[str, Field(min_length=2, max_length=60, examples=["Coimbatore"])]
CreatorNiches = Annotated[list[Niche], Field(min_length=1, max_length=MAX_NICHES)]
CreatorLanguages = Annotated[list[Language], Field(min_length=1)]
Bio = Annotated[str, Field(max_length=BIO_MAX_LENGTH)]


DateOfBirth = Annotated[
    date,
    Field(
        description=(
            "Used once, to confirm you are 18 or over, and never stored: we "
            "keep only when you confirmed it"
        ),
        examples=["1999-04-14"],
    ),
]


class BrandProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: BrandName
    email: BrandEmail
    date_of_birth: DateOfBirth


class BrandProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: BrandName | None = None
    email: BrandEmail | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> BrandProfileUpdate:
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class BrandProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    email: str
    created_at: datetime
    updated_at: datetime


class CreatorProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: CreatorName
    handle: Handle
    city: CreatorCity
    niches: CreatorNiches
    languages: CreatorLanguages = list(LANGUAGES)
    bio: Bio | None = None
    date_of_birth: DateOfBirth


class CreatorProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: CreatorName | None = None
    handle: Handle | None = None
    city: CreatorCity | None = None
    niches: CreatorNiches | None = None
    languages: CreatorLanguages | None = None
    bio: Bio | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> CreatorProfileUpdate:
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class CreatorProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    display_name: str
    handle: str
    city: str
    niches: list[str]
    languages: list[str]
    bio: str | None
    # NULL means the public Passport is off: this profile is not findable by
    # anyone who is not signed in. Set means the creator turned it on, and
    # when (D-036).
    passport_published_at: datetime | None
    # The other consent, and a separate one (D-055): whether prices appear on
    # the public page. NULL means signed-in brands see them and the open
    # internet does not.
    rate_card_public_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- the public Creator Passport -----------------------------------------


class PublicCreatorSummary(BaseModel):
    """A creator's public profile facts, and nothing else.

    Deliberately narrow: it carries only what a creator would put on a public
    page. Contact details are not merely omitted here, they are not in this
    table at all (D-011), and the account id stays private so a public page
    cannot be linked to a login. Matching lists creators in this shape; the
    Passport below adds channels and prices.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    handle: str
    display_name: str
    city: str
    niches: list[str]
    languages: list[str]
    bio: str | None
    member_since: str = Field(
        description="Month the creator joined, e.g. 2026-09", examples=["2026-09"]
    )


class PublicCreatorRead(PublicCreatorSummary):
    """The public Creator Passport: the profile, links, and published prices."""

    channels: list[PublicChannelRead] = Field(
        description="Links to the creator's channels. Never a follower count (D-042)"
    )
    packages: list[PublicPackageRead] = Field(
        description=(
            "Prices, only when the creator has chosen to publish them (D-055). "
            "Empty otherwise, which looks the same as having none"
        )
    )


class ExportManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    records: int
    purpose: str = Field(description="Why we hold this data")
    truncated: bool | None = Field(
        default=None, description="Present, and true, only when rows were left out"
    )
    note: str | None = None


class ExportNotIncluded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: str
    reason: str


class ExportFile(BaseModel):
    """The file `GET /api/v1/me/export` returns, for the API documentation.

    The route builds the file itself so it can offer it as a download, so
    FastAPI cannot see this shape on its own. A test checks every real
    export against this model, so the two cannot drift apart.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    generated_at: str = Field(description="UTC, ISO 8601")
    account_id: uuid.UUID
    about: str
    manifest: list[ExportManifestEntry]
    not_included: list[ExportNotIncluded] = Field(
        description="What we hold but deliberately leave out, and why"
    )
    data: dict[str, list[dict[str, Any]]] = Field(
        description="One list of records per manifest section"
    )


AttentionKind = Literal[
    "respond_to_dispute",
    "pay_creator",
    "review_proof",
    "revise_memo",
    "draft_memo",
    "review_applications",
    "confirm_payment",
    "payment_overdue",
    "resubmit_work",
    "deliver_work",
    "answer_memo",
    "answer_invitation",
]

ensure_same_values("AttentionKind", AttentionKind, (*BRAND_KINDS, *CREATOR_KINDS))


class AttentionItemRead(BaseModel):
    """One thing waiting on the caller. The words belong to the frontend."""

    kind: AttentionKind
    due_on: date | None = Field(
        description="The Tamil Nadu date it is due by; null when nothing sets a date"
    )
    days_left: int | None = Field(
        description="Days until due_on; negative when overdue, 0 on the day itself"
    )
    campaign_id: uuid.UUID
    campaign_title: str
    counterparty: str | None = Field(
        description="A creator's handle for a brand, a brand's name for a creator"
    )
    application_id: uuid.UUID | None
    memo_id: uuid.UUID | None
    proof_id: uuid.UUID | None
    amount_paise: int | None
    currency: Literal["INR"] | None
    count: int | None = Field(
        description="For an item that stands for several things, such as applications"
    )


class AttentionRead(BaseModel):
    """What is waiting on the signed-in account, the most urgent first."""

    role: Literal["brand", "creator"]
    as_of: date = Field(description="The Tamil Nadu date the list was worked out for")
    total: int
    truncated: bool = Field(description="True when more items exist than are listed")
    counts: dict[AttentionKind, int] = Field(
        description="Items per kind, every kind for the role present, zeros included"
    )
    items: list[AttentionItemRead]


def to_attention_read(result: AttentionList) -> AttentionRead:
    return AttentionRead(
        role=result.role,
        as_of=result.as_of,
        total=result.total,
        truncated=result.truncated,
        counts=result.counts,
        items=[
            AttentionItemRead(
                kind=item.kind,
                due_on=item.due_on,
                days_left=(
                    None if item.due_on is None else (item.due_on - result.as_of).days
                ),
                campaign_id=item.campaign_id,
                campaign_title=item.campaign_title,
                counterparty=item.counterparty,
                application_id=item.application_id,
                memo_id=item.memo_id,
                proof_id=item.proof_id,
                amount_paise=item.amount_paise,
                currency=None if item.amount_paise is None else CURRENCY,
                count=item.count,
            )
            for item in result.items
        ],
    )


# --- rate card (D-055) ----------------------------------------------------

ChannelPlatform = Literal["instagram", "youtube"]
PackageFormat = Literal["post", "reel", "story", "short", "video", "live", "other"]


class ChannelUpsert(BaseModel):
    """What a creator states about one of their channels."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile_url: Annotated[
        str,
        Field(
            min_length=12,
            max_length=300,
            pattern=r"^https://",
            description="A link to the channel itself; the domain must match the platform",
            examples=["https://instagram.com/priya.eats"],
        ),
    ]
    followers: Annotated[
        int, Field(ge=0, le=1_000_000_000, description="As the creator states it")
    ]
    average_views: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            le=1_000_000_000,
            description="Optional: plenty of creators do not know it",
        ),
    ]


class ChannelRead(BaseModel):
    """A channel as its owner and signed-in brands see it.

    `followers` and `average_views` are the creator's own claim. We have never
    checked them, the word "verified" is never used, and `figures_as_of` says
    when they were stated — a follower count without a date is not a fact.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: ChannelPlatform
    profile_url: str
    followers: int
    average_views: int | None
    figures_as_of: date
    self_reported: Literal[True] = Field(
        default=True,
        description="Always true. These numbers are the creator's, not ours",
    )


class PublicChannelRead(BaseModel):
    """A channel on the open internet: the link, and nothing else.

    D-042 decided this after research. Follower counts are the easiest number
    to fake and about two in three Indian creators inflate them, so
    republishing our copy under our name would lend it our credibility.
    Anyone can follow the link and read the real number at the source.
    """

    model_config = ConfigDict(from_attributes=True)

    platform: ChannelPlatform
    profile_url: str


class PackageCreate(BaseModel):
    """One offer a creator sells."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: ChannelPlatform
    format: PackageFormat
    title: Annotated[
        str, Field(min_length=1, max_length=80, examples=["1 Instagram Reel"])
    ]
    description: Annotated[str | None, Field(default=None, max_length=500)]
    price_paise: Annotated[
        int,
        Field(gt=0, le=100_000_000_000, description="Whole paise: 800000 is Rs 8,000"),
    ]
    delivery_days: Annotated[int, Field(ge=1, le=90)]
    usage_rights_days: Annotated[int | None, Field(default=None, ge=0, le=3650)]
    position: Annotated[int, Field(default=0, ge=0, le=19, description="Display order")]


class PackageUpdate(BaseModel):
    """Any subset of a package's fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: ChannelPlatform | None = None
    format: PackageFormat | None = None
    title: Annotated[str | None, Field(default=None, min_length=1, max_length=80)]
    description: Annotated[str | None, Field(default=None, max_length=500)]
    price_paise: Annotated[int | None, Field(default=None, gt=0, le=100_000_000_000)]
    delivery_days: Annotated[int | None, Field(default=None, ge=1, le=90)]
    usage_rights_days: Annotated[int | None, Field(default=None, ge=0, le=3650)]
    position: Annotated[int | None, Field(default=None, ge=0, le=19)]

    @model_validator(mode="after")
    def at_least_one_field(self) -> PackageUpdate:
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Send at least one field to change")
        return self


class PackageRead(BaseModel):
    """A package, priced in paise so the frontend decides the formatting."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: ChannelPlatform
    format: PackageFormat
    title: str
    description: str | None
    price_paise: int
    currency: str
    delivery_days: int
    usage_rights_days: int | None
    position: int


class PublicPackageRead(BaseModel):
    """A package on the open internet, once its owner has published prices.

    No id and no position: the list is already in the creator's order, and an
    id is only useful to someone who can edit it.
    """

    model_config = ConfigDict(from_attributes=True)

    platform: ChannelPlatform
    format: PackageFormat
    title: str
    description: str | None
    price_paise: int
    currency: str
    delivery_days: int
    usage_rights_days: int | None


# PublicCreatorRead is defined above the channel and package shapes it lists.
PublicCreatorRead.model_rebuild()


# --- the media kit (D-055) -------------------------------------------------


class MediaKitRead(BaseModel):
    """Everything a brand weighs on one screen, behind a login.

    Unlike the public Passport it carries the self-reported numbers, each
    dated, and every price whether or not the creator published them: those
    switches decide what strangers see, not signed-in brands. Contact details
    are not here either (D-011); a brand reaches a creator through a campaign.
    """

    creator_id: uuid.UUID
    handle: str
    display_name: str
    city: str
    niches: list[str]
    languages: list[str]
    bio: str | None
    member_since: str = Field(
        description="Month the creator joined, e.g. 2026-09", examples=["2026-09"]
    )
    channels: list[ChannelRead] = Field(
        description="Self-reported, each with the date it was stated. Never verified"
    )
    packages: list[PackageRead] = Field(description="In the creator's order")
    delivery_record: CreatorDeliveryRead


# --- fair-rate guidance (D-056) ------------------------------------------

AudienceBand = Literal["under_10k", "10k_50k", "50k_100k", "100k_500k", "500k_plus"]


class NarrowedTo(BaseModel):
    """Which filters the figures actually used. Null means "all of them"."""

    niche: Niche | None
    city: str | None


class RateGuidanceRead(BaseModel):
    """What creators like this charge: a range, never a verdict.

    **Null figures mean "not enough to say"**, fewer than five creators, and
    must never be shown as zero. There is deliberately no minimum or maximum:
    each would be one person's price.
    """

    platform: ChannelPlatform
    format: PackageFormat
    audience_band: AudienceBand
    narrowed_to: NarrowedTo = Field(
        description=(
            "The niche and city the figures are for. If one you asked for is "
            "null here, there were too few creators with it and the answer "
            "is wider"
        )
    )
    source: Literal["published_asking_prices"] = Field(
        description="Prices creators ask and have chosen to publish, not agreed fees"
    )
    creators_counted: int = Field(
        description="Creators behind the figures, each counted once"
    )
    lower_quarter_paise: int | None
    median_paise: int | None
    upper_quarter_paise: int | None
    currency: str
    audience_self_reported: Literal[True] = Field(
        default=True,
        description="Bands come from follower counts creators stated; we never checked",
    )
    audience_figures_from: date | None = Field(
        description="Date of the oldest follower count behind the figures"
    )
    as_of: date = Field(description="The day these figures were worked out")


# --- brands searching for creators -------------------------------------------


class SearchChannelRead(BaseModel):
    """A channel's size, as the creator stated it and when."""

    platform: ChannelPlatform
    followers: int
    figures_as_of: date
    self_reported: Literal[True] = Field(
        default=True,
        description="Always true. The creator's number, never verified by us",
    )


class CreatorSearchResultRead(BaseModel):
    """One creator in a brand's search: enough to decide whether to open the media kit."""

    creator_id: uuid.UUID
    handle: str
    display_name: str
    city: str
    niches: list[str]
    bio: str | None
    member_since: str = Field(examples=["2026-09"])
    channels: list[SearchChannelRead]
    from_price_paise: int | None = Field(
        description=(
            "The cheapest package that answers the search (of the format and "
            "platform asked for, if any). Null when the creator lists none"
        )
    )
    currency: str
    booked_until: date | None = Field(
        description="The last day the creator is not taking new work; null if taking work today"
    )


# --- reports and the admin side (D-061) ------------------------------------------

ReportSubject = Literal["creator", "brand", "campaign"]
ReportCategory = Literal["fake_profile", "spam", "abuse", "non_payment", "other"]
AdminNote = Annotated[str, Field(min_length=3, max_length=1000)]


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
    status: Literal["open", "actioned", "dismissed"]
    created_at: datetime


class AdminReportRead(ReportRead):
    reporter_account_id: uuid.UUID
    resolved_at: datetime | None
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


# The API's lists must be exactly the database's, or startup fails.
ensure_same_values("Role", Role, ACCOUNT_ROLES)
ensure_same_values("ReportCategory", ReportCategory, REPORT_CATEGORIES)
ensure_same_values("ReportSubject", ReportSubject, REPORT_SUBJECTS)
ensure_same_values(
    "AdminActionKind", AdminActionRead.model_fields["action"].annotation, ADMIN_ACTIONS
)


# --- city figures for public pages (D-078) -------------------------------------------------


class CityCountRead(BaseModel):
    city: str = Field(description="As most of its creators spell it")
    published_creators: int


class AskingPriceRead(BaseModel):
    """The median asking price for one platform and format in a city.

    Each creator counts once; only groups of five creators or more appear.
    """

    platform: ChannelPlatform
    format: PackageFormat
    creators: int
    median_paise: int
    currency: str = CURRENCY


class NicheCountRead(BaseModel):
    niche: Niche
    creators: int | None = Field(description="Null below five: not enough to say")


class CityFiguresRead(BaseModel):
    """One city's public figures: counts and medians, five or nothing.

    Every count rests on creators who published their Passport, or on open
    campaigns; nothing comes from a deal. **Null means "not enough to say"
    and must never be shown as zero.**
    """

    city: str
    min_count: int = Field(description="The smallest count any figure is shown for")
    published_creators: int | None
    creators_by_niche: list[NicheCountRead]
    open_campaigns: int | None
    asking_prices: list[AskingPriceRead]


# --- invitations and arrival (D-080) ---------------------------------------------------------


class InviteCodeRead(BaseModel):
    code: str = Field(description="Eight characters; no 0, O, 1 or I")
    created_at: datetime


class InviteCountsRead(BaseModel):
    """How many joined with my code. Counts only, never who (D-080)."""

    brands: int
    creators: int


class SignupCountRead(BaseModel):
    week_starting: date = Field(description="A Monday, Tamil Nadu time")
    source: str
    role: Literal["brand", "creator", "admin"]
    accounts: int


# --- availability (D-083) -----------------------------------------------------


class AvailabilityUpdate(BaseModel):
    """The whole setting, replaced: a date, or null for taking work."""

    model_config = ConfigDict(extra="forbid")

    booked_until: date | None = Field(
        description=(
            "The last Tamil Nadu day you are not taking new work, from today "
            "to a year ahead. Null if you are taking work."
        ),
        examples=["2026-11-20"],
    )


class AvailabilityRead(BaseModel):
    booked_until: date | None = Field(
        description="Null when taking work today; a date already past reads as null"
    )
    available_from: date = Field(
        description="The first Tamil Nadu day the creator is taking work"
    )
