from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.modules.auth.exceptions import (
    OtpInvalid,
    OtpSendLimitReached,
    OtpVerifyLimitReached,
    RoleMismatch,
)
from app.modules.auth.models.account import Account
from app.modules.auth.models.auth_session import AuthSession
from app.modules.auth.models.otp_challenge import OTP_TTL, OtpChallenge
from app.modules.auth.service import request_otp, verify_otp
from app.modules.auth.tokens import decode_access_token, hash_refresh_token
from tests.factories import FIXED_NOW, create_account, fake_phone


def challenges_for(db, phone):
    return db.scalars(select(OtpChallenge).where(OtpChallenge.phone == phone)).all()


def wrong_code(code: str) -> str:
    return "000000" if code != "000000" else "111111"


# --- request_otp ---------------------------------------------------------


def test_request_stores_only_a_hash_and_returns_the_code(db):
    phone = fake_phone()

    pending = request_otp(db, phone, FIXED_NOW)

    [challenge] = challenges_for(db, phone)
    assert len(pending.code) == 6 and pending.code.isdigit()
    assert pending.code not in challenge.code_hash
    assert challenge.expires_at == FIXED_NOW + OTP_TTL
    assert pending.expires_at == challenge.expires_at
    assert challenge.attempts == 0
    assert challenge.consumed_at is None


def test_request_behaves_the_same_for_registered_and_unknown_numbers(db):
    registered = create_account(db, "creator").phone
    unknown = fake_phone()

    for phone in (registered, unknown):
        pending = request_otp(db, phone, FIXED_NOW)
        assert pending.phone == phone
        assert len(challenges_for(db, phone)) == 1


def test_fourth_code_within_ten_minutes_is_refused(db):
    phone = fake_phone()
    for minute in range(3):
        request_otp(db, phone, FIXED_NOW + timedelta(minutes=minute))

    with pytest.raises(OtpSendLimitReached):
        request_otp(db, phone, FIXED_NOW + timedelta(minutes=9))
    assert len(challenges_for(db, phone)) == 3


def test_ten_minute_limit_resets_after_the_window(db):
    phone = fake_phone()
    for _ in range(3):
        request_otp(db, phone, FIXED_NOW)

    request_otp(db, phone, FIXED_NOW + timedelta(minutes=10, seconds=1))

    assert len(challenges_for(db, phone)) == 4


def test_eleventh_code_in_a_day_is_refused(db):
    phone = fake_phone()
    for hour in range(10):
        request_otp(db, phone, FIXED_NOW + timedelta(hours=hour))

    with pytest.raises(OtpSendLimitReached):
        request_otp(db, phone, FIXED_NOW + timedelta(hours=23))
    request_otp(db, phone, FIXED_NOW + timedelta(hours=24, seconds=1))


def test_send_limit_is_per_phone(db):
    busy, other = fake_phone(), fake_phone()
    for _ in range(3):
        request_otp(db, busy, FIXED_NOW)

    request_otp(db, other, FIXED_NOW)

    assert len(challenges_for(db, other)) == 1


# --- verify_otp: success -------------------------------------------------


def test_new_number_gets_an_account_session_and_tokens(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)

    result = verify_otp(db, phone, pending.code, "creator", FIXED_NOW + timedelta(minutes=1))

    account = db.get(Account, result.account_id)
    assert account.phone == phone and account.role == "creator"
    assert result.is_new_account is True
    claims = decode_access_token(result.access_token, FIXED_NOW + timedelta(minutes=1))
    assert claims.account_id == account.id and claims.role == "creator"
    assert result.access_token_expires_at == FIXED_NOW + timedelta(minutes=16)

    session = db.scalars(select(AuthSession).where(AuthSession.account_id == account.id)).one()
    assert session.token_hash == hash_refresh_token(result.refresh_token)
    assert result.refresh_token not in session.token_hash
    assert session.expires_at == FIXED_NOW + timedelta(minutes=1, days=30)
    assert result.refresh_token_expires_at == session.expires_at
    assert session.used_at is None and session.revoked_at is None


def test_existing_account_logs_in_without_creating_another(db):
    account = create_account(db, "brand")
    pending = request_otp(db, account.phone, FIXED_NOW)

    result = verify_otp(db, account.phone, pending.code, "brand", FIXED_NOW)

    assert result.account_id == account.id
    assert result.is_new_account is False
    assert db.scalar(select(Account).where(Account.phone == account.phone)) is not None
    assert len(db.scalars(select(Account).where(Account.phone == account.phone)).all()) == 1


def test_code_is_consumed_after_success(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)

    verify_otp(db, phone, pending.code, "creator", FIXED_NOW)

    [challenge] = challenges_for(db, phone)
    assert challenge.consumed_at == FIXED_NOW


def test_each_login_starts_a_new_session_family(db):
    phone = fake_phone()
    first = verify_otp(db, phone, request_otp(db, phone, FIXED_NOW).code, "creator", FIXED_NOW)
    later = FIXED_NOW + timedelta(minutes=11)
    second = verify_otp(db, phone, request_otp(db, phone, later).code, "creator", later)

    sessions = db.scalars(select(AuthSession).where(AuthSession.account_id == first.account_id)).all()
    assert len(sessions) == 2
    assert sessions[0].family_id != sessions[1].family_id
    assert first.refresh_token != second.refresh_token


# --- verify_otp: failures ------------------------------------------------


def test_wrong_code_is_rejected_and_uses_an_attempt(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)

    with pytest.raises(OtpInvalid):
        verify_otp(db, phone, wrong_code(pending.code), "creator", FIXED_NOW)

    [challenge] = challenges_for(db, phone)
    assert challenge.attempts == 1
    assert challenge.consumed_at is None
    assert db.scalar(select(Account).where(Account.phone == phone)) is None


def test_code_dies_after_five_wrong_attempts(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)
    for _ in range(5):
        with pytest.raises(OtpInvalid):
            verify_otp(db, phone, wrong_code(pending.code), "creator", FIXED_NOW)

    with pytest.raises(OtpInvalid):
        verify_otp(db, phone, pending.code, "creator", FIXED_NOW)
    assert challenges_for(db, phone)[0].attempts == 5


def test_right_code_on_fifth_try_still_works(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)
    for _ in range(4):
        with pytest.raises(OtpInvalid):
            verify_otp(db, phone, wrong_code(pending.code), "creator", FIXED_NOW)

    result = verify_otp(db, phone, pending.code, "creator", FIXED_NOW)

    assert result.is_new_account is True


def test_code_is_valid_until_just_before_expiry(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)

    verify_otp(db, phone, pending.code, "creator", FIXED_NOW + OTP_TTL - timedelta(seconds=1))


def test_expired_code_is_rejected(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)

    with pytest.raises(OtpInvalid):
        verify_otp(db, phone, pending.code, "creator", FIXED_NOW + OTP_TTL)


def test_used_code_cannot_be_used_again(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)
    verify_otp(db, phone, pending.code, "creator", FIXED_NOW)

    with pytest.raises(OtpInvalid):
        verify_otp(db, phone, pending.code, "creator", FIXED_NOW)


def test_verify_without_any_code_is_rejected(db):
    with pytest.raises(OtpInvalid):
        verify_otp(db, fake_phone(), "123456", "creator", FIXED_NOW)


def test_only_the_latest_code_counts(db):
    phone = fake_phone()
    first = request_otp(db, phone, FIXED_NOW)
    second = request_otp(db, phone, FIXED_NOW + timedelta(minutes=1))
    if first.code == second.code:
        pytest.skip("both random codes happened to be equal (1 in a million)")

    with pytest.raises(OtpInvalid):
        verify_otp(db, phone, first.code, "creator", FIXED_NOW + timedelta(minutes=2))
    verify_otp(db, phone, second.code, "creator", FIXED_NOW + timedelta(minutes=2))


def test_code_for_another_phone_is_rejected(db):
    phone, other = fake_phone(), fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)
    other_pending = request_otp(db, other, FIXED_NOW)
    if pending.code == other_pending.code:
        pytest.skip("both random codes happened to be equal (1 in a million)")

    with pytest.raises(OtpInvalid):
        verify_otp(db, other, pending.code, "creator", FIXED_NOW)


def test_role_mismatch_is_refused_and_code_stays_usable(db):
    account = create_account(db, "brand")
    pending = request_otp(db, account.phone, FIXED_NOW)

    with pytest.raises(RoleMismatch):
        verify_otp(db, account.phone, pending.code, "creator", FIXED_NOW)

    [challenge] = challenges_for(db, account.phone)
    assert challenge.consumed_at is None and challenge.attempts == 0
    assert db.scalars(select(AuthSession).where(AuthSession.account_id == account.id)).all() == []
    result = verify_otp(db, account.phone, pending.code, "brand", FIXED_NOW)
    assert result.account_id == account.id


def test_failure_while_logging_in_leaves_no_partial_account(db):
    phone = fake_phone()
    pending = request_otp(db, phone, FIXED_NOW)

    with (
        patch("app.modules.auth.service.create_access_token", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError),
    ):
        verify_otp(db, phone, pending.code, "creator", FIXED_NOW)
    db.rollback()

    assert db.scalar(select(Account).where(Account.phone == phone)) is None
    assert challenges_for(db, phone)[0].consumed_at is None


# --- test isolation ------------------------------------------------------

ISOLATION_PHONE = "+919999900000"


@pytest.mark.parametrize("run", [1, 2])
def test_committed_rows_do_not_leak_between_tests(db, run):
    assert challenges_for(db, ISOLATION_PHONE) == []
    request_otp(db, ISOLATION_PHONE, FIXED_NOW)
    assert len(challenges_for(db, ISOLATION_PHONE)) == 1


# --- per-phone guess limit ------------------------------------------------


def wrong_guesses(db, phone: str, code: str, count: int, now) -> None:
    for _ in range(count):
        with pytest.raises(OtpInvalid):
            verify_otp(db, phone, wrong_code(code), "creator", now)


def test_guessing_is_capped_across_several_codes_for_one_phone(db):
    phone = fake_phone()
    first = request_otp(db, phone, FIXED_NOW)
    # 5 wrong guesses use up the first code.
    wrong_guesses(db, phone, first.code, 5, FIXED_NOW)
    second = request_otp(db, phone, FIXED_NOW + timedelta(minutes=1))
    # 5 more on the second code reach the 10-guess limit for this number.
    wrong_guesses(db, phone, second.code, 5, FIXED_NOW + timedelta(minutes=1))
    third = request_otp(db, phone, FIXED_NOW + timedelta(minutes=2))

    with pytest.raises(OtpVerifyLimitReached):
        verify_otp(db, phone, third.code, "creator", FIXED_NOW + timedelta(minutes=3))


def test_the_limit_frees_up_after_the_window(db):
    phone = fake_phone()
    first = request_otp(db, phone, FIXED_NOW)
    wrong_guesses(db, phone, first.code, 5, FIXED_NOW)
    second = request_otp(db, phone, FIXED_NOW + timedelta(minutes=1))
    wrong_guesses(db, phone, second.code, 5, FIXED_NOW + timedelta(minutes=1))

    later = FIXED_NOW + timedelta(minutes=12)
    third = request_otp(db, phone, later)
    result = verify_otp(db, phone, third.code, "creator", later)

    assert result.is_new_account is True


def test_the_limit_is_per_phone(db):
    busy, other = fake_phone(), fake_phone()
    busy_code = request_otp(db, busy, FIXED_NOW)
    wrong_guesses(db, busy, busy_code.code, 5, FIXED_NOW)
    second = request_otp(db, busy, FIXED_NOW + timedelta(minutes=1))
    wrong_guesses(db, busy, second.code, 5, FIXED_NOW + timedelta(minutes=1))

    other_code = request_otp(db, other, FIXED_NOW + timedelta(minutes=2))
    result = verify_otp(db, other, other_code.code, "creator", FIXED_NOW + timedelta(minutes=2))

    assert result.is_new_account is True


def test_a_correct_code_still_works_below_the_limit(db):
    phone = fake_phone()
    first = request_otp(db, phone, FIXED_NOW)
    wrong_guesses(db, phone, first.code, 4, FIXED_NOW)
    second = request_otp(db, phone, FIXED_NOW + timedelta(minutes=1))

    result = verify_otp(db, phone, second.code, "creator", FIXED_NOW + timedelta(minutes=1))

    assert result.is_new_account is True
