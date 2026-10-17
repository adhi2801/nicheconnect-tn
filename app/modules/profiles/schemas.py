"""Request and response shapes for brand and creator profiles, rate cards and availability (D-099)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.core.literals import ensure_same_values
from app.core.taxonomy import LANGUAGES
from app.modules.auth.schemas import (
    Bio,
    BrandEmail,
    BrandName,
    ChannelPlatform,
    CreatorCity,
    CreatorLanguages,
    CreatorName,
    CreatorNiches,
    DateOfBirth,
    Handle,
    PackageFormat,
)
from app.modules.profiles.brand_domain_models import (
    CHECK_RESULTS,
    DOMAIN_STATUSES,
    BrandDomain,
)
from app.modules.profiles.brand_domains import record_name, record_value


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


# --- a brand's domain (item 74, D-106) -----------------------------------------------------

DomainStatus = Literal["pending", "verified", "lapsed"]
CheckResult = Literal["found", "absent", "unknown", "taken"]
ensure_same_values("DomainStatus", DomainStatus, DOMAIN_STATUSES)
ensure_same_values("CheckResult", CheckResult, CHECK_RESULTS)


class BrandDomainClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(
        min_length=1,
        max_length=260,
        description=(
            "The website's own domain, such as smallshop.in. A leading www. is "
            "dropped; a name under the domain, a shared suffix (co.in) or a "
            "domain in another script is refused, saying what to claim instead"
        ),
        examples=["smallshop.in"],
    )


class BrandDomainRead(BaseModel):
    """The brand's own claim, with what to publish. Only the brand sees this."""

    domain: str
    status: DomainStatus = Field(
        description=(
            "pending until a check finds the record; verified after; lapsed once "
            "three daily checks in a row find it gone, after which the domain is "
            "claimed again for a new token"
        )
    )
    record_type: Literal["TXT"] = "TXT"
    record_name: str = Field(
        description="Where to add the TXT record, at your DNS host",
        examples=["_nicheconnect-challenge.smallshop.in"],
    )
    record_value: str = Field(
        description="What the TXT record says. Keep it there: it is checked daily",
        examples=["nicheconnect-domain-verification=mfrggzdfmztwq2lknnwg23tpoa"],
    )
    token_expires_at: datetime = Field(
        description="A pending claim must be found by then, or claimed again"
    )
    check_waiting: bool = Field(description="A check was asked for and has not run yet")
    last_checked_at: datetime | None
    last_result: CheckResult | None = Field(
        description=(
            "found: both resolvers saw the record. absent: they answered without "
            "it. unknown: a resolver could not be asked, which never counts "
            "against you. taken: another brand already holds the domain"
        )
    )
    consecutive_absent: int = Field(
        description="Daily checks in a row that found the record gone; at 3 it lapses"
    )
    verified_at: datetime | None
    lapsed_at: datetime | None
    registered_on: date | None = Field(
        description="When the registry says the domain was registered; null if it did not say"
    )
    dnssec_validated: bool | None


class VerifiedDomainRead(BaseModel):
    """What a creator sees: facts about one domain, never a verdict on the brand.

    The brand controls the DNS of `domain`, as checked daily. It does not
    say the brand is who its name claims: a look-alike domain can be
    verified too, which is why the domain itself, and when it was
    registered, are shown (legal.md rule 3).
    """

    domain: str = Field(examples=["smallshop.in"])
    verified_since: datetime
    last_checked_at: datetime
    registered_on: date | None = Field(
        description=(
            "When the registry says the domain was registered: a domain a few "
            "days old is what scams use. Null when the registry did not say"
        )
    )
    dnssec_validated: bool | None = Field(
        description="Whether the domain's DNS answers were signed and checked (DNSSEC)"
    )


def to_verified_domain_read(row: BrandDomain) -> VerifiedDomainRead:
    # Only verified rows reach here, so both times are set.
    return VerifiedDomainRead(
        domain=row.domain,
        verified_since=row.verified_at or row.claimed_at,
        last_checked_at=row.last_checked_at or row.claimed_at,
        registered_on=row.registered_on,
        dnssec_validated=row.dnssec_validated,
    )


def to_brand_domain_read(row: BrandDomain) -> BrandDomainRead:
    return BrandDomainRead(
        domain=row.domain,
        status=row.status,
        record_name=record_name(row.domain),
        record_value=record_value(row.token),
        token_expires_at=row.token_expires_at,
        check_waiting=row.check_requested_at is not None,
        last_checked_at=row.last_checked_at,
        last_result=row.last_result,
        consecutive_absent=row.consecutive_absent,
        verified_at=row.verified_at,
        lapsed_at=row.lapsed_at,
        registered_on=row.registered_on,
        dnssec_validated=row.dnssec_validated,
    )
