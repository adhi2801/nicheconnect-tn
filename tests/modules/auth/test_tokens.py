import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.modules.auth.exceptions import InvalidToken
from app.modules.auth.tokens import (
    ALGORITHM,
    CURRENT_KEY_ID,
    create_access_token,
    decode_access_token,
    generate_otp_code,
    hash_otp_code,
    hash_refresh_token,
    new_refresh_token,
    otp_code_matches,
)
from tests.factories import FIXED_NOW

SECRET = settings.secret_key.get_secret_value()


def signed(claims: dict, key: str = SECRET, kid: str | None = CURRENT_KEY_ID) -> str:
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(claims, key, algorithm=ALGORITHM, headers=headers)


def valid_claims(**overrides) -> dict:
    claims = {
        "sub": str(uuid.uuid4()),
        "role": "creator",
        "typ": "access",
        "iat": int(FIXED_NOW.timestamp()),
        "exp": int((FIXED_NOW + timedelta(minutes=15)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    claims.update(overrides)
    return claims


def test_access_token_round_trip():
    account_id = uuid.uuid4()

    token, expires_at = create_access_token(account_id, "brand", FIXED_NOW)
    claims = decode_access_token(token, FIXED_NOW)

    assert expires_at == FIXED_NOW + timedelta(minutes=15)
    assert claims.account_id == account_id
    assert claims.role == "brand"
    assert claims.expires_at == expires_at


def test_access_token_carries_key_id_and_unique_jti():
    account_id = uuid.uuid4()
    first, _ = create_access_token(account_id, "creator", FIXED_NOW)
    second, _ = create_access_token(account_id, "creator", FIXED_NOW)

    assert jwt.get_unverified_header(first)["kid"] == CURRENT_KEY_ID
    first_jti = jwt.decode(
        first, SECRET, algorithms=[ALGORITHM], options={"verify_exp": False}
    )["jti"]
    second_jti = jwt.decode(
        second, SECRET, algorithms=[ALGORITHM], options={"verify_exp": False}
    )["jti"]
    assert first_jti != second_jti


def test_token_is_valid_until_just_before_expiry():
    token, expires_at = create_access_token(uuid.uuid4(), "creator", FIXED_NOW)

    decode_access_token(token, expires_at - timedelta(seconds=1))
    with pytest.raises(InvalidToken):
        decode_access_token(token, expires_at)


def test_token_signed_with_another_key_is_rejected():
    with pytest.raises(InvalidToken):
        decode_access_token(signed(valid_claims(), key="x" * 43), FIXED_NOW)


def test_tampered_token_is_rejected():
    token, _ = create_access_token(uuid.uuid4(), "creator", FIXED_NOW)
    header, payload, signature = token.split(".")
    tampered = ".".join(
        [header, payload, signature[:-2] + ("AA" if signature[-2:] != "AA" else "BB")]
    )

    with pytest.raises(InvalidToken):
        decode_access_token(tampered, FIXED_NOW)


def test_unsigned_token_is_rejected():
    unsigned = jwt.encode(
        valid_claims(), key=None, algorithm="none", headers={"kid": CURRENT_KEY_ID}
    )

    with pytest.raises(InvalidToken):
        decode_access_token(unsigned, FIXED_NOW)


@pytest.mark.parametrize("kid", ["k0", None])
def test_unknown_or_missing_key_id_is_rejected(kid):
    with pytest.raises(InvalidToken):
        decode_access_token(signed(valid_claims(), kid=kid), FIXED_NOW)


@pytest.mark.parametrize(
    "overrides",
    [
        {"typ": "refresh"},
        {"role": "admin"},
        {"sub": "not-a-uuid"},
        {"exp": "soon"},
    ],
)
def test_token_with_bad_claims_is_rejected(overrides):
    with pytest.raises(InvalidToken):
        decode_access_token(signed(valid_claims(**overrides)), FIXED_NOW)


@pytest.mark.parametrize("missing", ["sub", "role", "typ", "iat", "exp", "jti"])
def test_token_missing_a_claim_is_rejected(missing):
    claims = valid_claims()
    del claims[missing]

    with pytest.raises(InvalidToken):
        decode_access_token(signed(claims), FIXED_NOW)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c"])
def test_garbage_token_is_rejected(garbage):
    with pytest.raises(InvalidToken):
        decode_access_token(garbage, FIXED_NOW)


def test_refresh_tokens_are_random_and_hash_to_64_hex_characters():
    first, second = new_refresh_token(), new_refresh_token()

    assert first != second
    assert len(first) >= 43
    assert len(hash_refresh_token(first)) == 64
    assert hash_refresh_token(first) == hash_refresh_token(first)
    assert first not in hash_refresh_token(first)


def test_otp_codes_are_six_digits_and_vary():
    codes = {generate_otp_code() for _ in range(200)}

    assert all(len(code) == 6 and code.isdigit() for code in codes)
    assert len(codes) > 150


def test_otp_hash_is_keyed_and_matches_only_the_right_code():
    code_hash = hash_otp_code("042917")

    assert len(code_hash) == 64
    assert "042917" not in code_hash
    assert otp_code_matches("042917", code_hash)
    assert not otp_code_matches("042918", code_hash)
    assert not otp_code_matches("42917", code_hash)


def test_otp_hash_depends_on_the_secret_key(monkeypatch):
    original = hash_otp_code("123456")
    monkeypatch.setattr(settings, "otp_hash_key", type(settings.otp_hash_key)("y" * 43))

    assert hash_otp_code("123456") != original


def test_token_issued_ahead_of_the_machine_clock_still_works():
    """Our injectable clock decides validity, not the machine clock.

    PyJWT would refuse a token whose "issued at" is in the machine's future
    (clock skew between servers, or a test clock). Expiry is checked against
    the clock we pass in, so that check stays off.
    """
    far_future = FIXED_NOW + timedelta(days=365)
    token, expires_at = create_access_token(uuid.uuid4(), "creator", far_future)

    claims = decode_access_token(token, far_future)

    assert claims.expires_at == expires_at
    with pytest.raises(InvalidToken):
        decode_access_token(token, expires_at)
