"""Brand and creator profile rules.

The tables live in this module (D-005, D-006, D-014), so their rules do too.
An account has exactly one profile, and its role decides which kind.
"""

import uuid
from datetime import datetime
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.auth.exceptions import (
    EmailTaken,
    HandleTaken,
    ProfileAlreadyExists,
    ProfileNotFound,
)
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator

Profile = TypeVar("Profile", Brand, Creator)

# Which database rule broke, and the error a user should see.
CONFLICTS: tuple[tuple[str, type], ...] = (
    ("uq_creator_handle", HandleTaken),
    ("uq_brand_email", EmailTaken),
    ("uq_brand_account_id", ProfileAlreadyExists),
    ("uq_creator_account_id", ProfileAlreadyExists),
)


def _raise_for_conflict(error: IntegrityError) -> None:
    """Turn a broken unique rule into the matching domain error."""
    message = str(error)
    for constraint, domain_error in CONFLICTS:
        if constraint in message:
            raise domain_error() from error
    raise error


def find_profile(db: Session, model: type[Profile], account_id: uuid.UUID) -> Profile | None:
    return db.scalars(select(model).where(model.account_id == account_id)).first()


def get_profile(db: Session, model: type[Profile], account_id: uuid.UUID) -> Profile:
    """The account's profile, or ProfileNotFound."""
    profile = find_profile(db, model, account_id)
    if profile is None:
        raise ProfileNotFound()
    return profile


def create_profile(
    db: Session,
    model: type[Profile],
    account_id: uuid.UUID,
    fields: dict,
    now: datetime,
) -> Profile:
    """Create the account's one profile.

    Raises ProfileAlreadyExists, and HandleTaken or EmailTaken when someone
    else already uses that handle or email.
    """
    if find_profile(db, model, account_id) is not None:
        db.rollback()
        raise ProfileAlreadyExists()

    profile = model(account_id=account_id, created_at=now, updated_at=now, **fields)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        _raise_for_conflict(error)
    db.refresh(profile)
    return profile


def update_profile(
    db: Session, profile: Profile, changes: dict, now: datetime
) -> Profile:
    """Change the account's own profile."""
    for field, value in changes.items():
        setattr(profile, field, value)
    profile.updated_at = now
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        _raise_for_conflict(error)
    db.refresh(profile)
    return profile


def publish_passport(db: Session, creator: Creator, now: datetime) -> Creator:
    """Turn the public Creator Passport on.

    Publishing an already-published profile keeps the original date. The
    timestamp is the record of when the creator consented, and a second tap
    on a slow connection is not a second decision.
    """
    if creator.passport_published_at is None:
        creator.passport_published_at = now
        creator.updated_at = now
        db.commit()
        db.refresh(creator)
    else:
        db.rollback()
    return creator


def unpublish_passport(db: Session, creator: Creator, now: datetime) -> Creator:
    """Turn it off. The profile stops answering to the open internet at once.

    Withdrawing is never refused and never rate-limited into uselessness:
    somebody who wants to stop being findable should not have to argue with
    us about it.
    """
    if creator.passport_published_at is not None:
        creator.passport_published_at = None
        creator.updated_at = now
        db.commit()
        db.refresh(creator)
    else:
        db.rollback()
    return creator
