"""Request and response shapes for the public Creator Passport and the media kit (D-099)."""

import uuid

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


# PublicCreatorRead is defined above the channel and package shapes it lists.
PublicCreatorRead.model_rebuild()
