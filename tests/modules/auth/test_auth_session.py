import secrets
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession, refresh_token_ttl
from tests.factories import (
    FIXED_NOW,
    build_auth_session,
    create_account,
    fake_token_hash,
)


def assert_rejected_by(db, session: AuthSession, constraint_name: str) -> None:
    db.add(session)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_valid_session_is_saved_unused_and_active(db):
    auth_session = build_auth_session(db)
    db.add(auth_session)
    db.flush()
    db.refresh(auth_session)

    assert auth_session.id is not None
    assert auth_session.expires_at == FIXED_NOW + refresh_token_ttl()
    assert auth_session.used_at is None
    assert auth_session.revoked_at is None
    assert auth_session.created_at is not None
    assert auth_session.updated_at is not None


def test_used_and_revoked_times_are_kept(db):
    auth_session = build_auth_session(db, used_at=FIXED_NOW, revoked_at=FIXED_NOW)
    db.add(auth_session)
    db.flush()
    db.refresh(auth_session)

    assert auth_session.used_at == FIXED_NOW
    assert auth_session.revoked_at == FIXED_NOW


def test_rotated_sessions_share_one_family(db):
    account = create_account(db, "creator")
    family_id = uuid.uuid4()
    db.add(build_auth_session(db, account_id=account.id, family_id=family_id, used_at=FIXED_NOW))
    db.add(build_auth_session(db, account_id=account.id, family_id=family_id))
    db.flush()

    assert db.query(AuthSession).filter_by(family_id=family_id).count() == 2


def test_duplicate_token_hash_is_rejected(db):
    token_hash = fake_token_hash()
    db.add(build_auth_session(db, token_hash=token_hash))
    db.flush()

    assert_rejected_by(
        db, build_auth_session(db, token_hash=token_hash), "uq_auth_session_token_hash"
    )


@pytest.mark.parametrize(
    "token_hash",
    [
        secrets.token_urlsafe(32),  # raw token instead of a hash
        fake_token_hash().upper(),  # uppercase hex
        fake_token_hash()[:63],  # too short
    ],
)
def test_value_that_is_not_a_token_hash_is_rejected(db, token_hash):
    assert_rejected_by(
        db, build_auth_session(db, token_hash=token_hash), "ck_auth_session_token_hash_format"
    )


def test_session_for_unknown_account_is_rejected(db):
    assert_rejected_by(
        db,
        build_auth_session(db, account_id=uuid.uuid4()),
        "fk_auth_session_account_id_account",
    )


@pytest.mark.parametrize("missing", ["account_id", "family_id", "expires_at"])
def test_session_missing_a_required_field_is_rejected(db, missing):
    assert_rejected_by(db, build_auth_session(db, **{missing: None}), missing)


def test_deleting_an_account_deletes_its_sessions(db):
    account = create_account(db, "creator")
    db.add(build_auth_session(db, account_id=account.id))
    db.add(build_auth_session(db, account_id=account.id))
    db.flush()

    db.delete(account)
    db.flush()
    db.expire_all()

    assert db.get(Account, account.id) is None
    assert db.query(AuthSession).filter_by(account_id=account.id).count() == 0
