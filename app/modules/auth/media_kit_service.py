"""A creator's media kit: everything a brand needs on one screen (D-055).

The profile, the channels with their self-reported numbers, every package
with its price, and the delivery record. It is the signed-in counterpart of
the public Passport, and it differs from it on purpose:

- **Brands see the numbers.** Follower counts appear here, each with the date
  the creator stated it, because a brand deciding whom to pay needs a figure
  to weigh. The public page carries only the links (D-042).
- **Brands see the prices whether or not they are published.** That switch
  decides what the open internet sees, not what a signed-in brand sees
  (D-055 point 2).
- **The Passport switch does not apply either.** It is about strangers; a
  brand on the platform can already find this creator through matching.

Who may read it is the delivery record's rule, because the delivery record is
in it: any brand, or the creator themself, never another creator (D-038
point 7).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.rate_card import CreatorChannel, CreatorPackage
from app.modules.auth.rate_card_service import list_channels, list_packages
from app.modules.deal_memo import delivery_record
from app.modules.deal_memo.delivery_record import DeliveryRecord


@dataclass(frozen=True)
class MediaKit:
    creator: Creator
    channels: list[CreatorChannel]
    packages: list[CreatorPackage]
    delivery: DeliveryRecord


def may_read(db: Session, account: Account, creator_id: uuid.UUID) -> bool:
    """Any brand, or the creator themself.

    Answered without looking the id up, so another creator learns nothing,
    not even whether the id belongs to anybody.
    """
    if account.role == "brand":
        return True
    return delivery_record.creator_id_for_account(db, account.id) == creator_id


def for_creator(db: Session, creator_id: uuid.UUID, now: datetime) -> MediaKit | None:
    """The media kit as of `now`, or None if there is no such creator.

    Five queries, however many channels, packages or deals there are.
    """
    creator = db.get(Creator, creator_id)
    if creator is None:
        return None
    return MediaKit(
        creator=creator,
        channels=list_channels(db, creator),
        packages=list_packages(db, creator),
        delivery=delivery_record.for_creator(db, creator_id, now),
    )
