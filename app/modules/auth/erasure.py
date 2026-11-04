"""What auth erases when an account is deleted (item 6, D-122).

Auth owns the login and the identity tables, so it erases its own rows here
and empties the account, brand and creator rows, which stay: deals and
payment records point at them, and the other side keeps the facts of each
deal, shown as "a creator (or brand) who left" (D-122, choice 3A).

Gone: every session, assistant's token, push token, passkey and its challenges and reset, every
step-up and login code, a waiting phone change, an admin's authenticator,
how the account arrived and its invite code (other people's sign-ups keep
"came by invite", with the code's link emptied by its own foreign key), and
the phone number itself, which is free for whoever holds it next.

Emptied: a brand's name and email, its clearance of a look-alike name; a
creator's name, handle, bio, Passport and rate card consents, and "booked
until". The placeholders are random, never worked out from an id, since ids
are visible in the API: a handle or email made from one could be taken in
advance, and that person's deletion would then fail.

Kept on the emptied rows: the role, the dates the account was made,
suspended or deleted and why, and the adult confirmation's time, the
evidence that each deal was made with an adult (legal.md section 3.10); a
creator's city, niches and languages, which deals are described by and
which leave search and the figures with the account (`suspension`).

Callers hold the account's row lock for update before emptying it.
Nothing here commits.
"""

import secrets
from datetime import datetime

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import AccountPhoneChange
from app.modules.auth.models.agent_token import AgentToken
from app.modules.auth.models.attribution import AccountAttribution, InviteCode
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.brand_team import BrandInvite, BrandMember
from app.modules.auth.models.creator import Creator
from app.modules.auth.models.device_token import DeviceToken
from app.modules.auth.models.otp_challenge import OtpChallenge
from app.modules.auth.models.passkey import Passkey, PasskeyChallenge, PasskeyReset
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.auth.models.totp_factor import TotpFactor

LEFT_BRAND_NAME = "A brand that left"
LEFT_CREATOR_NAME = "A creator who left"
# RFC 6761 reserves .invalid: no address under it can ever receive mail.
LEFT_EMAIL_DOMAIN = "deleted.invalid"
LEFT_HANDLE_PREFIX = "left."

# Tables whose rows for the account are deleted here, in this order.
ERASED_TABLES = frozenset(
    {
        "auth_session",
        "agent_token",
        "device_token",
        "passkey",
        "passkey_challenge",
        "passkey_reset",
        "step_up_challenge",
        "otp_challenge",
        "account_phone_change",
        "totp_factor",
        "account_attribution",
        "invite_code",
    }
)
# Tables whose row stays, emptied of what identifies the person.
EMPTIED_TABLES = frozenset({"account", "brand", "creator"})


def left_email() -> str:
    """A brand email nobody owns, unique by its 128 random bits."""
    return f"left-{secrets.token_hex(16)}@{LEFT_EMAIL_DOMAIN}"


def left_handle() -> str:
    """A creator handle in the handle format, unique by its 100 random bits."""
    return LEFT_HANDLE_PREFIX + secrets.token_hex(13)[:25]


def erase_for_account(db: Session, account: Account) -> None:
    """Delete auth's rows for the account, its login codes included. Never commits.

    Called while the account still has its phone: login codes are kept by
    number, not by account.
    """
    account_id = account.id
    db.execute(delete(DeviceToken).where(DeviceToken.account_id == account_id))
    db.execute(delete(AuthSession).where(AuthSession.account_id == account_id))
    db.execute(delete(AgentToken).where(AgentToken.account_id == account_id))
    db.execute(delete(PasskeyChallenge).where(PasskeyChallenge.account_id == account_id))
    db.execute(delete(PasskeyReset).where(PasskeyReset.account_id == account_id))
    db.execute(delete(Passkey).where(Passkey.account_id == account_id))
    db.execute(delete(StepUpChallenge).where(StepUpChallenge.account_id == account_id))
    # The number's login codes go with it, unless its other side stays
    # (D-126): they are the number's, and still serve that account.
    if account.phone is not None and not db.scalar(
        select(exists().where(Account.phone == account.phone, Account.id != account_id))
    ):
        db.execute(delete(OtpChallenge).where(OtpChallenge.phone == account.phone))
    db.execute(
        delete(AccountPhoneChange).where(AccountPhoneChange.account_id == account_id)
    )
    db.execute(delete(TotpFactor).where(TotpFactor.account_id == account_id))
    db.execute(
        delete(AccountAttribution).where(AccountAttribution.account_id == account_id)
    )
    db.execute(delete(InviteCode).where(InviteCode.account_id == account_id))
    # Teams (D-148): the person's own memberships, with the first name
    # creators saw; and, when an owner leaves, their brand's team and its
    # open invites, since nobody is left to act for it.
    owned = select(Brand.id).where(Brand.account_id == account_id)
    db.execute(
        delete(BrandMember).where(
            or_(BrandMember.account_id == account_id, BrandMember.brand_id.in_(owned))
        )
    )
    db.execute(delete(BrandInvite).where(BrandInvite.brand_id.in_(owned)))


def lock_profile(db: Session, account: Account) -> Brand | Creator | None:
    """Lock the account's brand or creator row for update.

    An invitation reads the creator under a shared lock
    (`campaigns.invitation_service`), so it lands wholly before the erasure
    or finds the creator gone. Taken before any campaign or application, and
    before the account's own row, the order every other path takes them in,
    so no erasure and request lock in a circle (`me.account_deletion_service`).
    """
    if account.role == "brand":
        return db.scalars(
            select(Brand)
            .where(Brand.account_id == account.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
    if account.role == "creator":
        return db.scalars(
            select(Creator)
            .where(Creator.account_id == account.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
    return None


def empty_identity(
    db: Session, account: Account, profile: Brand | Creator | None, now: datetime
) -> None:
    """Empty the profile and the account, and mark it deleted. Never commits."""
    if isinstance(profile, Brand):
        profile.name = LEFT_BRAND_NAME
        profile.email = left_email()
        profile.name_cleared = None
        profile.name_cleared_at = None
        profile.name_cleared_by_account_id = None
        profile.updated_at = now
    elif isinstance(profile, Creator):
        profile.display_name = LEFT_CREATOR_NAME
        profile.handle = left_handle()
        profile.bio = None
        profile.passport_published_at = None
        profile.rate_card_public_at = None
        profile.booked_until = None
        profile.updated_at = now
    account.phone = None
    account.passkey_only = False
    account.deleted_at = now
    account.updated_at = now
