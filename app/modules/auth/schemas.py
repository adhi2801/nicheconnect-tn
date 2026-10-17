"""Request and response shapes for OTP login (backend.md section 4)."""

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
)
from pydantic_core import PydanticCustomError

from app.core.attention import BRAND_KINDS, CREATOR_KINDS
from app.core.literals import ensure_same_values
from app.core.taxonomy import MAX_NICHES, Language, Niche
from app.modules.auth.models.account import (
    ACCOUNT_ROLES,
    PHONE_PATTERN,
)
from app.modules.auth.models.attribution import ARRIVAL_SOURCES
from app.modules.auth.models.creator import BIO_MAX_LENGTH, HANDLE_PATTERN

# The media kit nests the delivery record as its own module defines it, so
# the two can never describe the same numbers differently.
from app.modules.auth.models.device_token import (
    TOKEN_MAX_LENGTH,
    TOKEN_MIN_LENGTH,
    TOKEN_PATTERN,
)

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
# "admin" is never created by login (D-061), and logs in only with two
# factors, at /auth/admin/login (D-105); /auth/otp/verify answers it as a
# wrong code.
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
            "Which app is logging in. `admin` is always answered as a wrong "
            "code: admins log in with two factors at /api/v1/auth/admin/login"
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
    # This phone's push token, so logging out also stops its notifications
    # (D-095). Optional: the website and older apps have none.
    device_token: Annotated[
        str | None,
        Field(
            min_length=TOKEN_MIN_LENGTH,
            max_length=TOKEN_MAX_LENGTH,
            pattern=TOKEN_PATTERN,
            description="This phone's push token, to stop its notifications too",
        ),
    ] = None


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


BrandName = Annotated[str, Field(min_length=1, max_length=150, examples=["Amma Sweets"])]
BrandEmail = Annotated[
    str, BeforeValidator(_normalize_email), Field(examples=["hello@ammasweets.in"])
]


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


AttentionKind = Literal[
    "respond_to_dispute",
    "pay_creator",
    "review_proof",
    "revise_memo",
    "draft_memo",
    "review_applications",
    "fix_domain_record",
    "domain_lapsed",
    "domain_claim_expired",
    "confirm_payment",
    "payment_overdue",
    "resubmit_work",
    "deliver_work",
    "answer_memo",
    "answer_invitation",
]

ensure_same_values("AttentionKind", AttentionKind, (*BRAND_KINDS, *CREATOR_KINDS))


# --- rate card (D-055) ----------------------------------------------------

ChannelPlatform = Literal["instagram", "youtube"]
PackageFormat = Literal["post", "reel", "story", "short", "video", "live", "other"]


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


# --- the media kit (D-055) -------------------------------------------------


# --- fair-rate guidance (D-056) ------------------------------------------


# The API's lists must be exactly the database's, or startup fails.
ensure_same_values("Role", Role, ACCOUNT_ROLES)


# --- city figures for public pages (D-078) -------------------------------------------------


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


# --- blocking (item 59) -----------------------------------------------------------------


# --- the founders' weekly numbers (item 63) ----------------------------------------------
