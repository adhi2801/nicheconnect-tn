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
from app.modules.auth.models.account import PHONE_PATTERN
from app.modules.auth.models.creator import BIO_MAX_LENGTH, HANDLE_PATTERN

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


def _check_code(value: object) -> str:
    code = value.strip() if isinstance(value, str) else value
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise PydanticCustomError("code_invalid", "Enter the 6-digit code we sent you")
    return code


IndianMobile = Annotated[
    str,
    BeforeValidator(normalize_indian_mobile),
    AfterValidator(_check_e164),
    Field(
        description="Indian mobile number; stored as +91XXXXXXXXXX",
        examples=["+919876543210"],
    ),
]
OtpCode = Annotated[
    str,
    BeforeValidator(_check_code),
    Field(description="The 6-digit code sent to the phone", examples=["042917"]),
]
Role = Literal["brand", "creator"]


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile


class OtpRequestAccepted(BaseModel):
    expires_in_seconds: int = Field(examples=[300])


class OtpVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: IndianMobile
    code: OtpCode
    role: Role = Field(description="Which app is logging in", examples=["creator"])


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


class BrandProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: BrandName
    email: BrandEmail


class BrandProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: BrandName | None = None
    email: BrandEmail | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "BrandProfileUpdate":
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


class CreatorProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: CreatorName | None = None
    handle: Handle | None = None
    city: CreatorCity | None = None
    niches: CreatorNiches | None = None
    languages: CreatorLanguages | None = None
    bio: Bio | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "CreatorProfileUpdate":
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
    created_at: datetime
    updated_at: datetime


# --- the public Creator Passport -----------------------------------------


class PublicCreatorRead(BaseModel):
    """A creator profile as the open internet sees it.

    Deliberately narrow: this response is readable by anyone, so it carries
    only what a creator would put on a public page. Contact details are not
    merely omitted here, they are not in this table at all (D-011), and the
    account id stays private so a public page cannot be linked to a login.
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
