"""Passkeys: what a challenge is, and what makes an answer good (item 79, D-113).

The checks themselves are WebAuthn's, done by Yubico's `fido2` (D-113): the
answer is for our domain (the RP ID's hash), from one of our origins, to a
challenge we made, with the person present and verified by the phone's own
lock, and signed by the key we hold the public half of. Around them, here:

- **Each challenge works once, for 5 minutes**, and only for what it was
  made for: signing up a key, logging in, or one exact change. A change's
  challenge carries the change's action and an HMAC of its value, as a
  step-up code does (D-107), so a passkey answer for one change cannot be
  spent on another.
- **A counter gone backwards refuses the key**: a key whose counter moves
  (security keys) and then repeats or falls has been copied. Synced
  passkeys keep it at 0, and are not judged by it.
- **Off until the domain exists** (`settings.passkey_rp_id`): a passkey is
  bound to its domain, so one made for a stand-in would never work on ours.

What uses these, and tells the owner, is in `me.passkey_service`
(notifications sit a layer above auth, D-099); logging in is here.
"""

import hmac
import logging
import secrets
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from fido2 import cbor
from fido2.cose import CoseKey
from fido2.server import Fido2Server
from fido2.utils import websafe_encode
from fido2.webauthn import (
    AttestedCredentialData,
    AuthenticationResponse,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialType,
    PublicKeyCredentialUserEntity,
    RegistrationResponse,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from sqlalchemy import delete, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.auth import service as login
from app.modules.auth.exceptions import (
    AccountSuspended,
    PasskeyInvalid,
    PasskeysNotOpen,
    TooManyPasskeys,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.passkey import (
    CHALLENGE_BYTES,
    MAX_PASSKEYS,
    PASSKEY_CHALLENGE_TTL,
    Passkey,
    PasskeyChallenge,
)
from app.modules.auth.service import LoginResult

logger = logging.getLogger(__name__)

# Challenges are kept a day past expiry, for looking into a complaint, then
# deleted by the job.
CHALLENGES_KEPT_FOR = timedelta(days=1)
# Errors fido2 and its parsers raise for an answer that is wrong or malformed.
BAD_ANSWER = (ValueError, KeyError, TypeError, IndexError)


def is_open() -> bool:
    """Whether passkeys are switched on: the domain is set."""
    return settings.passkey_rp_id is not None


def _server() -> Fido2Server:
    """WebAuthn's checks for our domain and origins. Raises PasskeysNotOpen."""
    if settings.passkey_rp_id is None:
        raise PasskeysNotOpen(
            "They are switched on once the website's own domain exists."
        )
    origins = frozenset(settings.passkey_origin_list)
    return Fido2Server(
        PublicKeyCredentialRpEntity(
            id=settings.passkey_rp_id, name=settings.passkey_rp_name
        ),
        # A consumer service has no use for the maker's attestation, and
        # asking for it only adds a privacy prompt (WebAuthn L3, section 13.4).
        attestation=None,
        verify_origin=lambda origin: origin in origins,
    )


def has_any(db: Session, account_id: uuid.UUID) -> bool:
    """Whether the account has a passkey: then only a passkey proves a change."""
    return bool(db.scalar(select(exists().where(Passkey.account_id == account_id))))


def for_account(db: Session, account_id: uuid.UUID) -> list[Passkey]:
    """The account's passkeys, oldest first; at most MAX_PASSKEYS."""
    return list(
        db.scalars(
            select(Passkey)
            .where(Passkey.account_id == account_id)
            .order_by(Passkey.created_at, Passkey.id)
        ).all()
    )


def registration_options(db: Session, account: Account, now: datetime) -> dict[str, Any]:
    """What the phone needs to make a passkey for this account. Commits.

    The key must be discoverable, so it can log in with no number typed,
    and unlocked by the phone's own lock (user verification). Keys the
    account already has are excluded, so one device is never added twice.
    """
    server = _server()
    challenge = _new_challenge(db, purpose="register", account_id=account.id, now=now)
    options, _state = server.register_begin(
        PublicKeyCredentialUserEntity(
            # The person's own number, shown by their own phone in its list
            # of passkeys, so they can tell their accounts apart.
            name=login.phone_of(account),
            id=account.id.bytes,
            display_name=login.phone_of(account),
        ),
        credentials=[_descriptor(passkey) for passkey in for_account(db, account.id)],
        resident_key_requirement=ResidentKeyRequirement.REQUIRED,
        user_verification=UserVerificationRequirement.REQUIRED,
        challenge=challenge,
    )
    db.commit()
    return dict(options)


def add(
    db: Session,
    account: Account,
    credential: Mapping[str, Any],
    name: str,
    now: datetime,
) -> Passkey:
    """Check the phone's answer to a sign-up challenge and keep the key.

    The account's row is locked first, so two sign-ups at once count each
    other against MAX_PASSKEYS. The caller commits. Raises PasskeysNotOpen,
    PasskeyInvalid and TooManyPasskeys.
    """
    server = _server()
    try:
        challenge = RegistrationResponse.from_dict(
            credential
        ).response.client_data.challenge
    except BAD_ANSWER:
        raise PasskeyInvalid() from None
    row = _take(db, challenge, purpose="register", account_id=account.id, now=now)
    try:
        auth_data = server.register_complete(_state(challenge), credential)
    except BAD_ANSWER:
        db.rollback()
        raise PasskeyInvalid() from None
    attested = auth_data.credential_data
    if attested is None:
        db.rollback()
        raise PasskeyInvalid()

    # FOR NO KEY UPDATE: two sign-ups at once still count each other, while a
    # sign-in's new session, which only needs the account to exist, never waits.
    db.execute(
        select(Account.id).where(Account.id == account.id).with_for_update(key_share=True)
    )
    held = db.scalar(select(func.count()).where(Passkey.account_id == account.id))
    if held is not None and held >= MAX_PASSKEYS:
        db.rollback()
        raise TooManyPasskeys()
    passkey = Passkey(
        account_id=account.id,
        credential_id=attested.credential_id,
        public_key=cbor.encode(dict(attested.public_key)),
        sign_count=auth_data.counter,
        aaguid=uuid.UUID(bytes=bytes(attested.aaguid)),
        backup_eligible=auth_data.is_backup_eligible(),
        backup_state=auth_data.is_backed_up(),
        name=name,
        created_at=now,
        updated_at=now,
    )
    row.consumed_at = now
    row.updated_at = now
    db.add(passkey)
    try:
        db.flush()
    except IntegrityError:
        # The same key added to another account: refused, as any bad answer.
        db.rollback()
        raise PasskeyInvalid() from None
    return passkey


def login_options(db: Session, now: datetime) -> dict[str, Any]:
    """A challenge to log in with any of the person's passkeys. Commits.

    No number is asked for: the phone offers the passkeys it holds for our
    domain, and the answer says which.
    """
    server = _server()
    challenge = _new_challenge(db, purpose="login", account_id=None, now=now)
    options, _state = server.authenticate_begin(
        user_verification=UserVerificationRequirement.REQUIRED, challenge=challenge
    )
    db.commit()
    return dict(options)


def log_in(
    db: Session,
    credential: Mapping[str, Any],
    now: datetime,
    device: login.ClientDevice | None = None,
) -> LoginResult:
    """Log in with a passkey's answer. Commits.

    A new session family, proven by a passkey (`passkey_at`), so its tokens
    say so through every refresh; `device` is what the app said it is
    (D-114). Raises PasskeysNotOpen, PasskeyInvalid and AccountSuspended.
    """
    passkey = verify(db, credential, purpose="login", account_id=None, now=now)
    account = db.get_one(Account, passkey.account_id)
    if account.suspended_at is not None:
        db.rollback()
        raise AccountSuspended.because(account.suspension_reason)
    result = login.issue_session(
        db, account, uuid.uuid4(), now, passkey_at=now, device=device
    )
    db.commit()
    return result


def step_up_options(
    db: Session,
    account: Account,
    action: str,
    value_hash: str,
    now: datetime,
) -> dict[str, Any]:
    """A challenge for one exact change, answerable by the account's own keys. Commits."""
    server = _server()
    challenge = _new_challenge(
        db,
        purpose="step_up",
        account_id=account.id,
        now=now,
        action=action,
        value_hash=value_hash,
    )
    options, _state = server.authenticate_begin(
        credentials=[_descriptor(passkey) for passkey in for_account(db, account.id)],
        user_verification=UserVerificationRequirement.REQUIRED,
        challenge=challenge,
    )
    db.commit()
    return dict(options)


def verify(
    db: Session,
    credential: Mapping[str, Any],
    *,
    purpose: str,
    account_id: uuid.UUID | None,
    now: datetime,
    action: str | None = None,
    value_hash: str | None = None,
) -> Passkey:
    """Check a passkey's answer to one of our challenges. The caller commits.

    For `account_id`, the key must be that account's; for a change, the
    challenge must have been made for exactly `action` and `value_hash`.
    The challenge is spent and the key's counter and last use updated, in
    the caller's transaction. A refusal rolls back. Raises PasskeysNotOpen
    and PasskeyInvalid.
    """
    server = _server()
    try:
        answer = AuthenticationResponse.from_dict(credential)
        challenge = answer.response.client_data.challenge
    except BAD_ANSWER:
        raise PasskeyInvalid() from None
    row = _take(db, challenge, purpose=purpose, account_id=account_id, now=now)
    if purpose == "step_up" and not (
        row.action == action
        and row.value_hash is not None
        and value_hash is not None
        and hmac.compare_digest(row.value_hash, value_hash)
    ):
        db.rollback()
        raise PasskeyInvalid()
    passkey = db.scalars(
        select(Passkey)
        .where(Passkey.credential_id == answer.raw_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if passkey is None or (account_id is not None and passkey.account_id != account_id):
        db.rollback()
        raise PasskeyInvalid()
    try:
        server.authenticate_complete(_state(challenge), [_attested(passkey)], credential)
    except BAD_ANSWER:
        db.rollback()
        raise PasskeyInvalid() from None

    auth_data = answer.response.authenticator_data
    counter = auth_data.counter
    if not counter_is_fresh(passkey.sign_count, counter):
        logger.warning("passkey.counter_went_back passkey_id=%s", passkey.id)
        db.rollback()
        raise PasskeyInvalid()
    passkey.sign_count = counter
    passkey.backup_state = passkey.backup_eligible and auth_data.is_backed_up()
    passkey.last_used_at = now
    passkey.updated_at = now
    row.consumed_at = now
    row.updated_at = now
    return passkey


def counter_is_fresh(stored: int, answered: int) -> bool:
    """Whether a key's counter shows it has not been copied (WebAuthn L3, 6.1.1).

    A key that counts must count up, past what we last saw: a repeat or a
    fall means a second copy signed meanwhile. One that keeps 0 throughout
    (synced passkeys) is not judged by it.
    """
    if stored == 0 and answered == 0:
        return True
    return answered > stored


def tidy_challenges(db: Session, now: datetime) -> int:
    """Delete challenges expired a day or more. Commits. Returns how many."""
    removed = db.execute(
        delete(PasskeyChallenge).where(
            PasskeyChallenge.expires_at < now - CHALLENGES_KEPT_FOR
        )
    ).rowcount  # type: ignore[attr-defined]
    db.commit()
    return int(removed or 0)


def _new_challenge(
    db: Session,
    *,
    purpose: str,
    account_id: uuid.UUID | None,
    now: datetime,
    action: str | None = None,
    value_hash: str | None = None,
) -> bytes:
    challenge = secrets.token_bytes(CHALLENGE_BYTES)
    db.add(
        PasskeyChallenge(
            account_id=account_id,
            purpose=purpose,
            challenge=challenge,
            action=action,
            value_hash=value_hash,
            expires_at=now + PASSKEY_CHALLENGE_TTL,
            created_at=now,
            updated_at=now,
        )
    )
    return challenge


def _take(
    db: Session,
    challenge: bytes,
    *,
    purpose: str,
    account_id: uuid.UUID | None,
    now: datetime,
) -> PasskeyChallenge:
    """The unspent, unexpired challenge, made for this, locked. Raises PasskeyInvalid."""
    row = db.scalars(
        select(PasskeyChallenge)
        .where(PasskeyChallenge.challenge == challenge)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if (
        row is None
        or row.purpose != purpose
        or row.account_id != account_id
        or row.consumed_at is not None
        or now >= row.expires_at
    ):
        db.rollback()
        raise PasskeyInvalid()
    return row


def _state(challenge: bytes) -> dict[str, Any]:
    """fido2's own record of a challenge, rebuilt from ours."""
    return {
        "challenge": websafe_encode(challenge),
        "user_verification": UserVerificationRequirement.REQUIRED,
    }


def _attested(passkey: Passkey) -> AttestedCredentialData:
    key = cbor.decode(passkey.public_key)
    if not isinstance(key, Mapping):
        raise PasskeyInvalid()
    return AttestedCredentialData.create(
        passkey.aaguid.bytes, passkey.credential_id, CoseKey.parse(key)
    )


def _descriptor(passkey: Passkey) -> PublicKeyCredentialDescriptor:
    return PublicKeyCredentialDescriptor(
        type=PublicKeyCredentialType.PUBLIC_KEY, id=passkey.credential_id
    )
