"""Connected Instagram and YouTube accounts (item 29, D-134): the rules.

**Connecting is two steps, both from the creator's own session.**
`start` makes a `state` (32 random bytes, kept only as its hash) and, for
Google, a PKCE verifier (kept sealed), valid 10 minutes, and returns the
platform's sign-in link. The platform sends the creator back to our website
or app with a code, which posts it with the state to `complete`, signed in
as the same account: a state works once, for its own account and platform,
so nobody can bind their channel to someone else's account, or someone
else's to theirs (RFC 9700 section 4.7). The attempt is marked used before
the platform is asked, so a replay racing the first loses.

**The platform is asked outside any transaction**, once for the code and
once for the account it reaches; the connection is then written in a
transaction of its own under the creator's row lock. One platform account
belongs to one creator (`uq_connected_account_platform_user`): a second
creator trying it is refused, and the tokens they got are revoked.

**Tokens never leave.** Sealed under PLATFORM_TOKEN_KEY, bound to their
creator and platform (`connection_secrets`); never logged, exported or
answered. Disconnecting deletes them, then revokes at the platform where it
offers that. Meta's data deletion and deauthorize callbacks, verified by
their signature, delete the connection they name.

Off (`ConnectionsOff`, 503) until PLATFORM_CONNECTIONS_ENABLED.
"""

import base64
import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.export import ExportedSection, allow, build_section
from app.modules.auth.models.creator import Creator
from app.modules.profiles import connection_secrets as vault
from app.modules.profiles import meta_signed_request
from app.modules.profiles.connection_models import (
    CONFIRMATION_CODE_LENGTH,
    ConnectedAccount,
    ConnectionAttempt,
    PlatformDeletionRequest,
)
from app.modules.profiles.exceptions import (
    ChannelAlreadyConnected,
    ConnectionAttemptInvalid,
    ConnectionNotFound,
    ConnectionsOff,
    DeletionRequestNotFound,
    PlatformDown,
    PlatformRefusedConnection,
    SignedRequestInvalid,
)
from app.modules.profiles.platform_clients import (
    PlatformProfile,
    PlatformRefused,
    PlatformUnavailable,
    Tokens,
    get_platform_client,
)

logger = logging.getLogger(__name__)

ATTEMPT_LIFETIME = timedelta(minutes=10)

EXPORTED_TABLES = frozenset({"connected_account"})
# Never the tokens: they are the platform's keys to the account, not data
# about the person.
EXPORT_FIELDS = allow(
    "id",
    "platform",
    "platform_user_id",
    "handle",
    "status",
    "notice_version",
    "connected_at",
    "verified_followers",
    "verified_as_of",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class Started:
    authorize_url: str
    expires_at: datetime


def _ensure_on() -> None:
    if not settings.platform_connections_enabled:
        raise ConnectionsOff()


def redirect_uri(platform: str) -> str:
    """Where the platform sends the creator back: our website or app, exactly."""
    return f"{str(settings.platform_redirect_base).rstrip('/')}/{platform}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _attempt_context(account_id: uuid.UUID, platform: str, state_sha256: str) -> bytes:
    return b"attempt:" + account_id.bytes + platform.encode() + state_sha256.encode()


def _token_context(creator_id: uuid.UUID, platform: str, kind: bytes) -> bytes:
    return kind + creator_id.bytes + platform.encode()


def start(db: Session, account_id: uuid.UUID, platform: str, now: datetime) -> Started:
    """Begin connecting: the platform's sign-in link, good for 10 minutes. Commits."""
    _ensure_on()
    client = get_platform_client(platform)
    state = secrets.token_urlsafe(32)
    state_sha256 = _sha256(state)
    verifier = secrets.token_urlsafe(64) if client.uses_pkce else None
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
        if verifier is not None
        else None
    )
    attempt = ConnectionAttempt(
        account_id=account_id,
        platform=platform,
        state_sha256=state_sha256,
        code_verifier_sealed=(
            vault.seal(verifier, _attempt_context(account_id, platform, state_sha256))
            if verifier is not None
            else None
        ),
        created_at=now,
        expires_at=now + ATTEMPT_LIFETIME,
        updated_at=now,
    )
    db.add(attempt)
    db.commit()
    return Started(
        authorize_url=client.authorize_url(
            redirect_uri=redirect_uri(platform), state=state, code_challenge=challenge
        ),
        expires_at=attempt.expires_at,
    )


def complete(
    db: Session,
    account_id: uuid.UUID,
    creator: Creator,
    platform: str,
    *,
    code: str,
    state: str,
    now: datetime,
) -> ConnectedAccount:
    """Finish connecting with the platform's code. Commits.

    Raises ConnectionAttemptInvalid, PlatformRefusedConnection, PlatformDown
    and ChannelAlreadyConnected.
    """
    _ensure_on()
    state_sha256 = _sha256(state)
    attempt = db.scalars(
        select(ConnectionAttempt)
        .where(ConnectionAttempt.state_sha256 == state_sha256)
        .with_for_update()
    ).first()
    if (
        attempt is None
        or attempt.account_id != account_id
        or attempt.platform != platform
        or attempt.used_at is not None
        or attempt.expires_at <= now
    ):
        db.rollback()
        raise ConnectionAttemptInvalid()
    attempt.used_at = now
    attempt.updated_at = now
    verifier = (
        vault.unseal(
            attempt.code_verifier_sealed,
            _attempt_context(account_id, platform, state_sha256),
        )
        if attempt.code_verifier_sealed is not None
        else None
    )
    db.commit()

    client = get_platform_client(platform)
    try:
        tokens = client.exchange(
            code=code,
            redirect_uri=redirect_uri(platform),
            code_verifier=verifier,
            now=now,
        )
        profile = client.profile(tokens)
    except PlatformRefused:
        raise PlatformRefusedConnection() from None
    except PlatformUnavailable:
        raise PlatformDown() from None
    return _save(db, creator, platform, tokens, profile, now)


def _save(
    db: Session,
    creator: Creator,
    platform: str,
    tokens: Tokens,
    profile: PlatformProfile,
    now: datetime,
) -> ConnectedAccount:
    db.scalars(select(Creator.id).where(Creator.id == creator.id).with_for_update()).one()
    connection = db.scalars(
        select(ConnectedAccount).where(
            ConnectedAccount.creator_id == creator.id,
            ConnectedAccount.platform == platform,
        )
    ).first()
    if connection is None:
        connection = ConnectedAccount(creator_id=creator.id, platform=platform)
        db.add(connection)
    connection.platform_user_id = profile.platform_user_id
    connection.handle = profile.handle
    connection.access_token_sealed = vault.seal(
        tokens.access_token, _token_context(creator.id, platform, b"access:")
    )
    connection.refresh_token_sealed = (
        vault.seal(
            tokens.refresh_token, _token_context(creator.id, platform, b"refresh:")
        )
        if tokens.refresh_token is not None
        else None
    )
    connection.token_expires_at = tokens.expires_at
    connection.status = "active"
    connection.notice_version = str(settings.connect_notice_version)
    connection.connected_at = now
    connection.verified_followers = profile.followers
    connection.verified_as_of = now if profile.followers is not None else None
    connection.updated_at = now
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        if "uq_connected_account_platform_user" not in str(error):
            raise
        # Never kept: the tokens this creator got for someone else's channel.
        get_platform_client(platform).revoke(tokens)
        raise ChannelAlreadyConnected() from None
    db.commit()
    db.refresh(connection)
    logger.info("connection.made creator_id=%s platform=%s", creator.id, platform)
    return connection


def connections_of(db: Session, creator: Creator) -> list[ConnectedAccount]:
    """The creator's connections, by platform. Whole: at most one each."""
    return list(
        db.scalars(
            select(ConnectedAccount)
            .where(ConnectedAccount.creator_id == creator.id)
            .order_by(ConnectedAccount.platform)
        ).all()
    )


def disconnect(db: Session, creator: Creator, platform: str) -> None:
    """Delete the connection and its tokens, then revoke at the platform. Commits.

    Allowed with the switch off too: leaving is never blocked. Raises
    ConnectionNotFound.
    """
    connection = db.scalars(
        select(ConnectedAccount).where(
            ConnectedAccount.creator_id == creator.id,
            ConnectedAccount.platform == platform,
        )
    ).first()
    if connection is None:
        raise ConnectionNotFound()
    tokens = _tokens_of(connection)
    db.delete(connection)
    db.commit()
    logger.info("connection.removed creator_id=%s platform=%s", creator.id, platform)
    if tokens is not None and settings.platform_connections_enabled:
        get_platform_client(platform).revoke(tokens)


def _tokens_of(connection: ConnectedAccount) -> Tokens | None:
    access = (
        vault.unseal(
            connection.access_token_sealed,
            _token_context(connection.creator_id, connection.platform, b"access:"),
        )
        if settings.platform_token_key is not None
        else None
    )
    if access is None:
        return None
    refresh = (
        vault.unseal(
            connection.refresh_token_sealed,
            _token_context(connection.creator_id, connection.platform, b"refresh:"),
        )
        if connection.refresh_token_sealed is not None
        else None
    )
    return Tokens(
        access_token=access, refresh_token=refresh, expires_at=connection.token_expires_at
    )


# --- Meta's callbacks -----------------------------------------------------------


def _meta_user(signed_request: str) -> str:
    if settings.meta_app_secret is None:
        raise ConnectionsOff()
    user_id = meta_signed_request.user_id_from(
        signed_request, settings.meta_app_secret.get_secret_value()
    )
    if user_id is None:
        raise SignedRequestInvalid()
    return user_id


def _remove_instagram(db: Session, user_id: str) -> int:
    return len(
        db.execute(
            delete(ConnectedAccount)
            .where(
                ConnectedAccount.platform == "instagram",
                ConnectedAccount.platform_user_id == user_id,
            )
            .returning(ConnectedAccount.id)
        ).all()
    )


def meta_data_deletion(
    db: Session, signed_request: str, now: datetime
) -> PlatformDeletionRequest:
    """Meta asked us to delete what we hold about one of its users. Commits.

    Raises SignedRequestInvalid, and ConnectionsOff while there is no app secret.
    """
    user_id = _meta_user(signed_request)
    request = PlatformDeletionRequest(
        platform="instagram",
        confirmation_code=secrets.token_urlsafe(18)[:CONFIRMATION_CODE_LENGTH],
        removed=_remove_instagram(db, user_id),
        received_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    logger.info("connection.meta_deletion removed=%d", request.removed)
    return request


def meta_deauthorize(db: Session, signed_request: str) -> int:
    """The person removed our app in Instagram: their connection goes. Commits."""
    removed = _remove_instagram(db, _meta_user(signed_request))
    db.commit()
    logger.info("connection.meta_deauthorize removed=%d", removed)
    return removed


def deletion_status(db: Session, confirmation_code: str) -> PlatformDeletionRequest:
    """Raises DeletionRequestNotFound."""
    request = db.scalars(
        select(PlatformDeletionRequest).where(
            PlatformDeletionRequest.confirmation_code == confirmation_code
        )
    ).first()
    if request is None:
        raise DeletionRequestNotFound()
    return request


# --- the export and deletion ---------------------------------------------------


def erase_for_creator(db: Session, creator_id: uuid.UUID) -> None:
    """On deleting the account (D-122): the creator's connections. Never commits.

    The platforms' own copies are ended by the creator removing our app
    there; the tokens that reached them are gone with these rows.
    """
    db.execute(delete(ConnectedAccount).where(ConnectedAccount.creator_id == creator_id))


def erase_attempts_for_account(db: Session, account_id: uuid.UUID) -> None:
    """On deleting the account (D-122): sign-ins in flight. Never commits."""
    db.execute(
        delete(ConnectionAttempt).where(ConnectionAttempt.account_id == account_id)
    )


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """A creator's connections, without their tokens."""
    connections = list(
        db.scalars(
            select(ConnectedAccount)
            .join(Creator, Creator.id == ConnectedAccount.creator_id)
            .where(Creator.account_id == account_id)
            .order_by(ConnectedAccount.platform)
        ).all()
    )
    return [
        build_section(
            "connected_accounts",
            table="connected_account",
            purpose=(
                "The Instagram or YouTube accounts you connected, and the counts "
                "they reported, with your consent. The keys the platforms gave us "
                "to read them are not included: they unlock your account there."
            ),
            objects=connections,
            fields=EXPORT_FIELDS,
        )
    ]
