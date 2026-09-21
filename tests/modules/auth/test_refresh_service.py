from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.service import logout, refresh_session, request_otp, verify_otp
from app.modules.auth.tokens import (
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from tests.factories import FIXED_NOW, fake_phone

LATER = FIXED_NOW + timedelta(minutes=5)


def log_in(db, role: str = "creator"):
    """A fresh login, returning its LoginResult."""
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)
    return verify_otp(db, phone, pending.code, role, FIXED_NOW)


def sessions_for(db, account_id):
    return db.scalars(
        select(AuthSession)
        .where(AuthSession.account_id == account_id)
        .order_by(AuthSession.created_at)
    ).all()


def session_by_token(db, refresh_token: str) -> AuthSession | None:
    return db.scalars(
        select(AuthSession).where(
            AuthSession.token_hash == hash_refresh_token(refresh_token)
        )
    ).first()


# --- refresh -------------------------------------------------------------


def test_refresh_returns_new_tokens_in_the_same_family(db):
    login = log_in(db)

    refreshed = refresh_session(db, login.refresh_token, LATER)

    assert refreshed.account_id == login.account_id
    assert refreshed.role == login.role
    assert refreshed.is_new_account is False
    assert refreshed.refresh_token != login.refresh_token
    assert refreshed.access_token != login.access_token
    assert refreshed.access_token_expires_at == LATER + timedelta(minutes=15)
    assert refreshed.refresh_token_expires_at == LATER + timedelta(days=30)
    old, new = sessions_for(db, login.account_id)
    assert old.family_id == new.family_id
    assert old.used_at == LATER
    assert new.used_at is None and new.revoked_at is None


def test_refreshed_access_token_still_identifies_the_account(db):
    login = log_in(db, "brand")

    refreshed = refresh_session(db, login.refresh_token, LATER)

    claims = decode_access_token(refreshed.access_token, LATER)
    assert claims.account_id == login.account_id
    assert claims.role == "brand"


def test_refresh_can_be_repeated(db):
    login = log_in(db)

    first = refresh_session(db, login.refresh_token, LATER)
    second = refresh_session(db, first.refresh_token, LATER + timedelta(minutes=1))

    assert len({login.refresh_token, first.refresh_token, second.refresh_token}) == 3
    assert len(sessions_for(db, login.account_id)) == 3


def test_old_token_stops_working_after_refresh(db):
    login = log_in(db)
    refresh_session(db, login.refresh_token, LATER)

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, LATER + timedelta(minutes=1))


def test_reusing_an_old_token_kills_the_whole_family(db):
    login = log_in(db)
    current = refresh_session(db, login.refresh_token, LATER)

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, LATER + timedelta(minutes=1))

    # The token the thief did not have is dead too.
    with pytest.raises(InvalidToken):
        refresh_session(db, current.refresh_token, LATER + timedelta(minutes=2))
    assert all(s.revoked_at is not None for s in sessions_for(db, login.account_id))


def test_unknown_token_is_rejected(db):
    with pytest.raises(InvalidToken):
        refresh_session(db, new_refresh_token(), LATER)


def test_expired_token_is_rejected(db):
    login = log_in(db)

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=30))


def test_token_works_until_just_before_expiry(db):
    login = log_in(db)

    refresh_session(
        db, login.refresh_token, FIXED_NOW + timedelta(days=30) - timedelta(seconds=1)
    )


def test_revoked_token_is_rejected(db):
    login = log_in(db)
    logout(db, login.refresh_token, LATER)

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, LATER + timedelta(minutes=1))


def test_refresh_does_not_touch_another_login(db):
    first = log_in(db)
    second = log_in(db)

    refresh_session(db, first.refresh_token, LATER)

    other = session_by_token(db, second.refresh_token)
    assert other.used_at is None and other.revoked_at is None


# --- logout --------------------------------------------------------------


def test_logout_revokes_the_login(db):
    login = log_in(db)

    logout(db, login.refresh_token, LATER)

    assert session_by_token(db, login.refresh_token).revoked_at == LATER


def test_logout_revokes_older_and_newer_tokens_of_the_login(db):
    login = log_in(db)
    refreshed = refresh_session(db, login.refresh_token, LATER)

    logout(db, refreshed.refresh_token, LATER + timedelta(minutes=1))

    assert all(s.revoked_at is not None for s in sessions_for(db, login.account_id))


def test_logout_with_an_unknown_token_is_silent(db):
    logout(db, new_refresh_token(), LATER)


def test_logout_twice_keeps_the_first_time(db):
    login = log_in(db)
    logout(db, login.refresh_token, LATER)

    logout(db, login.refresh_token, LATER + timedelta(minutes=1))

    assert session_by_token(db, login.refresh_token).revoked_at == LATER


def test_logout_does_not_touch_another_login(db):
    first = log_in(db)
    second = log_in(db)

    logout(db, first.refresh_token, LATER)

    assert session_by_token(db, second.refresh_token).revoked_at is None
