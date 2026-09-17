import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models.otp_challenge import OTP_TTL, OtpChallenge
from tests.factories import FIXED_NOW, build_otp_challenge, fake_code_hash


def assert_rejected_by(db, challenge: OtpChallenge, constraint_name: str) -> None:
    db.add(challenge)
    with pytest.raises(IntegrityError) as exc_info:
        db.flush()
    assert constraint_name in str(exc_info.value)


def test_valid_challenge_is_saved_with_defaults(db):
    challenge = build_otp_challenge()
    db.add(challenge)
    db.flush()
    db.refresh(challenge)

    assert challenge.id is not None
    assert challenge.attempts == 0
    assert challenge.consumed_at is None
    assert challenge.expires_at == FIXED_NOW + OTP_TTL
    assert challenge.created_at is not None
    assert challenge.updated_at is not None


def test_stored_hash_is_not_the_plain_code(db):
    challenge = build_otp_challenge(code_hash=fake_code_hash("654321"))
    db.add(challenge)
    db.flush()

    assert "654321" not in challenge.code_hash
    assert len(challenge.code_hash) == 64


def test_consumed_time_is_kept(db):
    challenge = build_otp_challenge(consumed_at=FIXED_NOW)
    db.add(challenge)
    db.flush()
    db.refresh(challenge)

    assert challenge.consumed_at == FIXED_NOW


def test_several_challenges_for_one_phone_are_allowed(db):
    first = build_otp_challenge()
    db.add(first)
    db.add(build_otp_challenge(phone=first.phone))
    db.flush()

    assert db.query(OtpChallenge).filter_by(phone=first.phone).count() == 2


@pytest.mark.parametrize("phone", ["9876543210", "+14155550123", "+915876543210"])
def test_badly_formatted_phone_is_rejected(db, phone):
    assert_rejected_by(
        db, build_otp_challenge(phone=phone), "ck_otp_challenge_phone_format"
    )


@pytest.mark.parametrize(
    "code_hash",
    [
        "123456",  # plain code instead of a hash
        fake_code_hash().upper(),  # uppercase hex
        fake_code_hash()[:63] + "g",  # not hex
        fake_code_hash()[:63],  # too short
    ],
)
def test_value_that_is_not_a_code_hash_is_rejected(db, code_hash):
    assert_rejected_by(
        db, build_otp_challenge(code_hash=code_hash), "ck_otp_challenge_code_hash_format"
    )


@pytest.mark.parametrize("attempts", [-1, 6])
def test_attempts_outside_zero_to_five_are_rejected(db, attempts):
    assert_rejected_by(
        db, build_otp_challenge(attempts=attempts), "ck_otp_challenge_attempts_range"
    )


def test_five_attempts_is_allowed(db):
    db.add(build_otp_challenge(attempts=5))
    db.flush()


def test_challenge_without_expiry_is_rejected(db):
    assert_rejected_by(db, build_otp_challenge(expires_at=None), "expires_at")
