"""Team seats for brands: inviting, joining, roles and leaving (item 13, D-148).

The rules (docs/PROPOSAL_TEAM_SEATS.md):

- the owner and admins invite; only the owner invites or makes an admin,
  with a step-up code bound to that exact change;
- an invite keeps only a keyed hash of the number, and no message is sent
  to it; a brand account already holding the number is told in the app;
- only the invited number accepts, within 7 days; at most 20 live members
  a brand, counted under the brand's lock, so two accepting at once cannot
  pass it together;
- removing anyone needs a step-up code; an admin never removes an admin;
- a member may leave at any time, with no code;
- the team is read by everyone in it, with first names and roles, never a
  phone number.

Every change takes the brand's row lock first, the order every team path
takes, so two changes to one team run one at a time. A refusal raises
without writing anything; the request's end releases the lock.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.auth import step_up_service as step_ups
from app.modules.auth.brand_access import BrandAccess
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import (
    INVITE_LIFETIME,
    MAX_TEAM_MEMBERS,
    BrandInvite,
    BrandMember,
)
from app.modules.auth.team_invites import hash_invited_phone
from app.modules.me.exceptions import (
    AlreadyOnTeam,
    TeamChangeNotAllowed,
    TeamFull,
    TeamInviteExists,
    TeamInviteNotFound,
    TeamMemberNotFound,
)
from app.modules.notifications import service as notifications


@dataclass(frozen=True)
class Team:
    """A brand's owner, live members and open invites."""

    brand: Brand
    members: list[BrandMember]
    invites: list[BrandInvite]


def _lock_brand(db: Session, brand_id: uuid.UUID) -> Brand:
    return db.scalars(
        select(Brand)
        .where(Brand.id == brand_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _live(db: Session, brand_id: uuid.UUID) -> list[BrandMember]:
    return list(
        db.scalars(
            select(BrandMember)
            .where(BrandMember.brand_id == brand_id, BrandMember.removed_at.is_(None))
            .order_by(BrandMember.created_at, BrandMember.id)
        )
    )


def _is_open(invite: BrandInvite, now: datetime) -> bool:
    return (
        invite.accepted_at is None
        and invite.declined_at is None
        and invite.revoked_at is None
        and invite.expires_at > now
    )


def team(db: Session, access: BrandAccess, now: datetime) -> Team:
    """The brand's team as anyone in it sees it. Two queries."""
    invites = [
        i
        for i in db.scalars(
            select(BrandInvite)
            .where(
                BrandInvite.brand_id == access.brand.id,
                BrandInvite.accepted_at.is_(None),
                BrandInvite.declined_at.is_(None),
                BrandInvite.revoked_at.is_(None),
            )
            .order_by(BrandInvite.created_at, BrandInvite.id)
        )
        if i.expires_at > now
    ]
    return Team(access.brand, _live(db, access.brand.id), invites)


def invite(
    db: Session,
    access: BrandAccess,
    inviter: Account,
    phone: str,
    role: str,
    first_name: str,
    step_up_code: str | None,
    now: datetime,
) -> BrandInvite:
    """Invite a number to the team in `role`. Commits.

    An admin invite is the owner's alone, with a code bound to it. Raises
    TeamChangeNotAllowed, TeamInviteExists, AlreadyOnTeam, and what
    step_up_service.consume raises.
    """
    phone_hash = hash_invited_phone(phone)
    if role == "admin":
        if access.role != "owner":
            raise TeamChangeNotAllowed()
        step_ups.consume(
            db, inviter, "change_team", f"invite:{phone}:admin", step_up_code, now
        )
    brand = _lock_brand(db, access.brand.id)
    owner = db.get(Account, brand.account_id)
    holders = list(
        db.scalars(select(Account).where(Account.phone == phone, Account.role == "brand"))
    )
    if owner is not None and owner.phone == phone:
        raise AlreadyOnTeam()
    holder_ids = {a.id for a in holders}
    if any(m.account_id in holder_ids for m in _live(db, brand.id)):
        raise AlreadyOnTeam()
    for earlier in db.scalars(
        select(BrandInvite).where(
            BrandInvite.brand_id == brand.id,
            BrandInvite.phone_hash == phone_hash,
            BrandInvite.accepted_at.is_(None),
            BrandInvite.declined_at.is_(None),
            BrandInvite.revoked_at.is_(None),
        )
    ):
        if earlier.expires_at > now:
            raise TeamInviteExists()
        # a lapsed one makes room for the new one
        earlier.revoked_at = now
        earlier.updated_at = now
    db.flush()
    made = BrandInvite(
        brand_id=brand.id,
        role=role,
        first_name=first_name,
        phone_hash=phone_hash,
        invited_by_account_id=inviter.id,
        expires_at=now + INVITE_LIFETIME,
        created_at=now,
        updated_at=now,
    )
    db.add(made)
    db.flush()
    for holder in holders:
        notifications.record(
            db,
            account_id=holder.id,
            notification_type="team_invite_received",
            now=now,
            details={"invite_id": str(made.id), "brand_name": brand.name, "role": role},
        )
    db.commit()
    return made


def revoke_invite(
    db: Session, access: BrandAccess, invite_id: uuid.UUID, now: datetime
) -> None:
    """Take back an open invite. Commits. Raises TeamInviteNotFound."""
    _lock_brand(db, access.brand.id)
    found = db.scalars(
        select(BrandInvite)
        .where(BrandInvite.id == invite_id, BrandInvite.brand_id == access.brand.id)
        .with_for_update()
    ).first()
    if found is None or not _is_open(found, now):
        raise TeamInviteNotFound()
    found.revoked_at = now
    found.updated_at = now
    db.commit()


def invites_for(
    db: Session, account: Account, now: datetime
) -> list[tuple[BrandInvite, Brand]]:
    """The open invites to the signed-in brand account's own number. One query."""
    if account.role != "brand" or account.phone is None:
        return []
    rows = db.execute(
        select(BrandInvite, Brand)
        .join(Brand, Brand.id == BrandInvite.brand_id)
        .where(
            BrandInvite.phone_hash == hash_invited_phone(account.phone),
            BrandInvite.accepted_at.is_(None),
            BrandInvite.declined_at.is_(None),
            BrandInvite.revoked_at.is_(None),
        )
        .order_by(BrandInvite.created_at, BrandInvite.id)
    ).all()
    return [(i, b) for i, b in rows if i.expires_at > now]


def _my_open_invite(
    db: Session, account: Account, invite_id: uuid.UUID, now: datetime
) -> BrandInvite:
    if account.role != "brand" or account.phone is None:
        raise TeamInviteNotFound()
    found = db.scalars(
        select(BrandInvite)
        .where(
            BrandInvite.id == invite_id,
            BrandInvite.phone_hash == hash_invited_phone(account.phone),
        )
        .with_for_update()
    ).first()
    if found is None or not _is_open(found, now):
        raise TeamInviteNotFound()
    return found


def accept(
    db: Session,
    account: Account,
    invite_id: uuid.UUID,
    first_name: str | None,
    now: datetime,
) -> BrandMember:
    """Join the brand the invite is for. Commits.

    Raises TeamInviteNotFound, AlreadyOnTeam, TeamFull.
    """
    # The brand first, then the invite: the order every team path takes.
    peek = db.scalar(select(BrandInvite.brand_id).where(BrandInvite.id == invite_id))
    if peek is None:
        raise TeamInviteNotFound()
    brand = _lock_brand(db, peek)
    found = _my_open_invite(db, account, invite_id, now)
    live = _live(db, brand.id)
    if brand.account_id == account.id or any(m.account_id == account.id for m in live):
        raise AlreadyOnTeam()
    if len(live) >= MAX_TEAM_MEMBERS:
        raise TeamFull()
    member = BrandMember(
        brand_id=brand.id,
        account_id=account.id,
        role=found.role,
        first_name=first_name or found.first_name,
        invited_by_account_id=found.invited_by_account_id,
        created_at=now,
        updated_at=now,
    )
    db.add(member)
    found.accepted_at = now
    found.accepted_by_account_id = account.id
    found.updated_at = now
    db.flush()
    told = {brand.account_id} | {m.account_id for m in live if m.role == "admin"}
    for account_id in told:
        notifications.record(
            db,
            account_id=account_id,
            notification_type="team_joined",
            now=now,
            details={
                "member_id": str(member.id),
                "first_name": member.first_name,
                "role": member.role,
            },
        )
    db.commit()
    return member


def decline(db: Session, account: Account, invite_id: uuid.UUID, now: datetime) -> None:
    """Say no to an invite. Commits. Raises TeamInviteNotFound."""
    peek = db.scalar(select(BrandInvite.brand_id).where(BrandInvite.id == invite_id))
    if peek is None:
        raise TeamInviteNotFound()
    _lock_brand(db, peek)
    found = _my_open_invite(db, account, invite_id, now)
    found.declined_at = now
    found.updated_at = now
    db.commit()


def _member(db: Session, brand_id: uuid.UUID, member_id: uuid.UUID) -> BrandMember:
    found = db.scalars(
        select(BrandMember).where(
            BrandMember.id == member_id,
            BrandMember.brand_id == brand_id,
            BrandMember.removed_at.is_(None),
        )
    ).first()
    if found is None:
        raise TeamMemberNotFound()
    return found


def change_role(
    db: Session,
    access: BrandAccess,
    actor: Account,
    member_id: uuid.UUID,
    role: str,
    step_up_code: str | None,
    now: datetime,
) -> BrandMember:
    """Give a member another role. Commits.

    Making someone an admin, or changing an admin, is the owner's alone and
    needs a code bound to exactly this change. Raises TeamMemberNotFound,
    TeamChangeNotAllowed, and what step_up_service.consume raises.
    """
    _lock_brand(db, access.brand.id)
    member = _member(db, access.brand.id, member_id)
    if member.role == role:
        return member
    if "admin" in (role, member.role):
        if access.role != "owner":
            raise TeamChangeNotAllowed()
        step_ups.consume(
            db, actor, "change_team", f"role:{member_id}:{role}", step_up_code, now
        )
        member = _member(db, access.brand.id, member_id)
    member.role = role
    member.updated_at = now
    notifications.record(
        db,
        account_id=member.account_id,
        notification_type="team_role_changed",
        now=now,
        details={"brand_name": access.brand.name, "role": role},
    )
    db.commit()
    return member


def remove(
    db: Session,
    access: BrandAccess,
    actor: Account,
    member_id: uuid.UUID,
    step_up_code: str | None,
    now: datetime,
) -> None:
    """Remove a member: they can no longer act for the brand. Commits.

    Needs a code bound to exactly this removal. An admin never removes an
    admin. Raises TeamMemberNotFound, TeamChangeNotAllowed, and what
    step_up_service.consume raises.
    """
    _lock_brand(db, access.brand.id)
    member = _member(db, access.brand.id, member_id)
    if member.role == "admin" and access.role != "owner":
        raise TeamChangeNotAllowed()
    step_ups.consume(db, actor, "change_team", f"remove:{member_id}", step_up_code, now)
    member = _member(db, access.brand.id, member_id)
    member.removed_at = now
    member.updated_at = now
    notifications.record(
        db,
        account_id=member.account_id,
        notification_type="team_removed",
        now=now,
        details={"brand_name": access.brand.name},
    )
    db.commit()


def leave(db: Session, account: Account, brand_id: uuid.UUID, now: datetime) -> None:
    """Stop acting for a brand you belong to. Commits. Raises TeamMemberNotFound."""
    exists = db.scalar(
        select(func.count()).select_from(Brand).where(Brand.id == brand_id)
    )
    if not exists:
        raise TeamMemberNotFound()
    _lock_brand(db, brand_id)
    member = db.scalars(
        select(BrandMember).where(
            BrandMember.brand_id == brand_id,
            BrandMember.account_id == account.id,
            BrandMember.removed_at.is_(None),
        )
    ).first()
    if member is None:
        raise TeamMemberNotFound()
    member.removed_at = now
    member.updated_at = now
    db.commit()
