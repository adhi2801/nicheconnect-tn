"""Request and response shapes for the public Creator Passport and the media kit (D-099)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.modules.auth.schemas import (
    ChannelPlatform,
    ChannelRead,
    PackageFormat,
    PackageRead,
    PublicCreatorSummary,
)
from app.modules.deal_memo.schemas import CreatorDeliveryRead
from app.modules.profiles.schemas import ConnectedPlatform


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
    connected_accounts: list[PublicConnectionRead] = Field(
        default_factory=list,
        description=(
            "The accounts the creator proved they control by signing in to them "
            "(D-134): the platform, the handle and since when. Never a count "
            "(D-135, keeping D-042)"
        ),
    )
    structured_data: dict[str, Any] | None = Field(
        default=None,
        description=(
            "schema.org ProfilePage JSON-LD for the website to embed in this "
            "Passport's page, so search engines read it (item 85): the published "
            "name, handle, bio, channel links and dates, nothing else. The website "
            "adds the page's URL. Null while indexing is switched off"
        ),
    )


class IndexablePassportRead(BaseModel):
    """One Passport for the website's sitemap.xml (item 85)."""

    handle: str = Field(examples=["priya.eats"])
    last_modified: datetime = Field(
        description="When what its readers see last changed: the sitemap's lastmod"
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
    connected_accounts: list[VerifiedConnectionRead] = Field(
        default_factory=list,
        description=(
            "Accounts the creator connected (D-134), with the count the platform "
            "itself reported. Show it beside the channel's stated count, never "
            "instead: bought followers inflate both"
        ),
    )


class PublicConnectionRead(BaseModel):
    """A connected account on the open internet: proof of control, no count (D-135)."""

    platform: ConnectedPlatform
    handle: str
    connected_since: date


class VerifiedConnectionRead(BaseModel):
    """A connected account as brands see it: what the platform itself reported."""

    platform: ConnectedPlatform
    handle: str
    connected_since: date
    verified_followers: int | None = Field(
        description="Null when the platform hides it; never shown as zero"
    )
    verified_as_of: datetime | None


# PublicCreatorRead and MediaKitRead are defined above the shapes they list.
PublicCreatorRead.model_rebuild()
MediaKitRead.model_rebuild()
