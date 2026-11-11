import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.models.account import Account
from app.modules.auth.models.account_phone_change import AccountPhoneChange
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
    # Never past 30 days from the login, however late the refresh (D-174).
    assert refreshed.refresh_token_expires_at == FIXED_NOW + timedelta(days=30)
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


def test_a_login_ends_thirty_days_after_it_was_proven_however_often_refreshed(db):
    """Item 144 (D-174): refreshing daily used to keep a login forever."""
    login = log_in(db)
    token = login.refresh_token
    for day in range(1, 30):
        refreshed = refresh_session(db, token, FIXED_NOW + timedelta(days=day))
        assert refreshed.refresh_token_expires_at == FIXED_NOW + timedelta(days=30)
        token = refreshed.refresh_token

    with pytest.raises(InvalidToken):
        refresh_session(db, token, FIXED_NOW + timedelta(days=30))


def test_the_last_access_token_ends_with_the_login(db):
    login = log_in(db)

    refreshed = refresh_session(
        db, login.refresh_token, FIXED_NOW + timedelta(days=30) - timedelta(minutes=5)
    )

    assert refreshed.access_token_expires_at == FIXED_NOW + timedelta(days=30)


def test_a_session_issued_before_the_limit_is_refused_and_its_login_ended(db):
    """Rows from before D-174 carry an expiry past the login's limit."""
    login = log_in(db)
    row = session_by_token(db, login.refresh_token)
    row.expires_at = FIXED_NOW + timedelta(days=59)
    db.commit()

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=30))

    assert all(s.revoked_at is not None for s in sessions_for(db, login.account_id))


def test_a_waiting_deletion_keeps_the_login_until_it_is_done(db):
    """D-176: the owner cancels a SIM swapper's deletion from a session they
    already have; a login ending at its 30 days would leave them none. Once
    the deletion is done, nothing holds the login."""
    login = log_in(db)
    account = db.get_one(Account, login.account_id)
    account.deletion_requested_at = FIXED_NOW + timedelta(days=25)
    account.deletion_takes_effect_at = FIXED_NOW + timedelta(days=55)
    db.commit()

    kept = refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=29))
    later = refresh_session(db, kept.refresh_token, FIXED_NOW + timedelta(days=40))

    assert kept.refresh_token_expires_at == FIXED_NOW + timedelta(days=55)
    assert later.refresh_token_expires_at == FIXED_NOW + timedelta(days=55)
    account = db.get_one(Account, login.account_id)
    account.deleted_at, account.phone = FIXED_NOW + timedelta(days=55), None
    db.commit()
    with pytest.raises(InvalidToken):
        refresh_session(db, later.refresh_token, FIXED_NOW + timedelta(days=55))


@pytest.mark.parametrize("without_current_number", [False, True])
def test_a_waiting_phone_change_keeps_the_login_until_it_takes_effect(
    db, without_current_number
):
    login = log_in(db)
    requested = FIXED_NOW + timedelta(days=29, hours=12)
    wait = timedelta(days=7) if without_current_number else timedelta(hours=72)
    db.add(
        AccountPhoneChange(
            account_id=login.account_id,
            new_phone=fake_phone(),
            requested_at=requested,
            takes_effect_at=requested + wait,
            without_current_number=without_current_number,
            created_at=requested,
            updated_at=requested,
        )
    )
    db.commit()

    kept = refresh_session(
        db, login.refresh_token, FIXED_NOW + timedelta(days=30, hours=1)
    )

    assert kept.refresh_token_expires_at == requested + wait


def test_a_change_already_made_or_past_keeps_nothing(db):
    login = log_in(db)
    account = db.get_one(Account, login.account_id)
    account.deletion_requested_at = FIXED_NOW - timedelta(days=1)
    account.deletion_takes_effect_at = FIXED_NOW + timedelta(days=29)
    db.commit()

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=30))


def owners_two_logins(db):
    """The same account logged in twice, on day 0: (first, second)."""
    phone = fake_phone()
    first = verify_otp(
        db, phone, request_otp(db, phone, FIXED_NOW).code, "creator", FIXED_NOW
    )
    later = FIXED_NOW + timedelta(minutes=1)
    second = verify_otp(db, phone, request_otp(db, phone, later).code, "creator", later)
    return first, second


def family_of(db, login) -> uuid.UUID:
    return session_by_token(db, login.refresh_token).family_id


def ask_for_deletion(db, account_id, asked_at, asked_by=None) -> None:
    account = db.get_one(Account, account_id)
    account.deletion_requested_at = asked_at
    account.deletion_takes_effect_at = asked_at + timedelta(days=30)
    account.deletion_requested_by_session = asked_by
    db.commit()


def test_the_login_that_asked_is_never_kept_alive(db):
    """A thief holding a stolen session gains nothing by asking (the review of D-176)."""
    owner, thief = owners_two_logins(db)
    ask_for_deletion(
        db, owner.account_id, FIXED_NOW + timedelta(days=25), family_of(db, thief)
    )
    kept = refresh_session(db, owner.refresh_token, FIXED_NOW + timedelta(days=29))
    thiefs = refresh_session(db, thief.refresh_token, FIXED_NOW + timedelta(days=29))

    later = FIXED_NOW + timedelta(days=31)
    assert refresh_session(db, kept.refresh_token, later).refresh_token_expires_at == (
        FIXED_NOW + timedelta(days=55)
    )
    with pytest.raises(InvalidToken):
        refresh_session(db, thiefs.refresh_token, later)


def test_asking_again_to_restart_the_wait_keeps_the_asker_nothing(db):
    owner, thief = owners_two_logins(db)
    asker = family_of(db, thief)
    for day in (20, 26):  # a new 7-day wait before the last one ends
        requested = FIXED_NOW + timedelta(days=day)
        db.execute(
            delete(AccountPhoneChange).where(
                AccountPhoneChange.account_id == owner.account_id
            )
        )
        db.add(
            AccountPhoneChange(
                account_id=owner.account_id,
                new_phone=fake_phone(),
                requested_at=requested,
                takes_effect_at=requested + timedelta(days=7),
                without_current_number=True,
                requested_by_session=asker,
                created_at=requested,
                updated_at=requested,
            )
        )
        db.commit()

    with pytest.raises(InvalidToken):
        refresh_session(db, thief.refresh_token, FIXED_NOW + timedelta(days=30, hours=1))


def test_a_token_already_run_out_is_never_brought_back(db):
    """Only a login alive when the change was asked for is held."""
    login = log_in(db)
    ask_for_deletion(db, login.account_id, FIXED_NOW + timedelta(days=31))

    with pytest.raises(InvalidToken):
        refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=32))


def test_a_login_made_after_the_request_is_not_held(db):
    owner, _ = owners_two_logins(db)
    ask_for_deletion(db, owner.account_id, FIXED_NOW - timedelta(days=1))

    with pytest.raises(InvalidToken):
        refresh_session(db, owner.refresh_token, FIXED_NOW + timedelta(days=30))


def test_a_phone_change_cancelled_by_a_login_with_the_number_holds_nothing(db):
    owner, _ = owners_two_logins(db)
    requested = FIXED_NOW + timedelta(days=25)
    db.add(
        AccountPhoneChange(
            account_id=owner.account_id,
            new_phone=fake_phone(),
            requested_at=requested,
            takes_effect_at=requested + timedelta(days=7),
            without_current_number=True,
            created_at=requested,
            updated_at=requested,
        )
    )
    db.commit()
    phone = db.get_one(Account, owner.account_id).phone
    at = requested + timedelta(hours=1)
    verify_otp(
        db, phone, request_otp(db, phone, at).code, "creator", at
    )  # the number logs in

    with pytest.raises(InvalidToken):
        refresh_session(db, owner.refresh_token, FIXED_NOW + timedelta(days=30, hours=1))


def test_a_deletion_held_past_its_date_by_a_deal_keeps_the_login_a_day_at_a_time(db):
    login = log_in(db)
    ask_for_deletion(db, login.account_id, FIXED_NOW + timedelta(days=1))  # due day 31
    kept = refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=29))
    now = FIXED_NOW + timedelta(days=32)  # past its date, still waiting on a deal

    held = refresh_session(db, kept.refresh_token, now)

    assert held.refresh_token_expires_at == now + timedelta(days=1)


def test_cancelling_the_change_ends_the_hold_and_the_login(db):
    """D-176 consequence 3: once cancelled, the 30 days apply at the next refresh."""
    login = log_in(db)
    ask_for_deletion(db, login.account_id, FIXED_NOW + timedelta(days=25))
    kept = refresh_session(db, login.refresh_token, FIXED_NOW + timedelta(days=29))
    account = db.get_one(Account, login.account_id)
    account.deletion_requested_at = account.deletion_takes_effect_at = None
    db.commit()

    with pytest.raises(InvalidToken):
        refresh_session(db, kept.refresh_token, FIXED_NOW + timedelta(days=31))
    assert all(s.revoked_at is not None for s in sessions_for(db, login.account_id))


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
