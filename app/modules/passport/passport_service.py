"""Who appears on the public Creator Passport, and when (D-036, D-055).

The rules behind the one page anyone on the internet can read. They lived in
its router until 12 October 2026, against `backend.md` section 1: a router
parses, calls and returns, and the rules live here.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.auth import suspension
from app.modules.auth.exceptions import ProfileNotFound
from app.modules.auth.models.creator import Creator
from app.modules.safety.exceptions import ContentWithheld
from app.modules.safety.takedowns import is_withheld


def passport_is_public(creator: Creator) -> bool:
    """Whether this profile may be shown to the open internet.

    Only if its owner said so. `passport_published_at` is both the switch
    and the record of when they chose it.
    """
    return creator.passport_published_at is not None


def prices_are_public(creator: Creator) -> bool:
    """Whether this creator's packages may be shown to the open internet.

    A second consent, separate from the Passport: a creator may want to be
    findable without publishing what they charge (D-055).
    """
    return creator.rate_card_public_at is not None


def public_creator(db: Session, handle: str) -> Creator:
    """The creator behind a public Passport link, if it may be shown.

    Raises ProfileNotFound when there is no such handle, the Passport is not
    published, or the account is suspended: all three look the same from
    outside (D-061), so a stranger learns nothing by trying handles. Raises
    ContentWithheld (451) for a published Passport withheld by a takedown
    (item 52): it was public, and saying why it is gone is the honest answer.
    """
    creator = db.scalars(select(Creator).where(Creator.handle == handle)).first()
    if (
        creator is None
        or not passport_is_public(creator)
        or suspension.is_suspended(db, creator.account_id)
    ):
        raise ProfileNotFound()
    if is_withheld(db, "creator", creator.id):
        raise ContentWithheld()
    return creator
