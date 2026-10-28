"""Authenticator codes and setup tickets, without a database (item 101, D-105)."""

import base64
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from app.modules.admin.schemas import SetupTicket
from app.modules.auth import second_factor
from app.modules.auth.models.totp_factor import SECRET_BYTES

# RFC 6238 Appendix B: the SHA-1 seed and its 8-digit codes. A 6-digit code
# is the same number cut to its last 6 digits (RFC 4226 section 5.3), so
# each vector checks our codes against the standard itself, not against the
# library that computes them.
RFC_SEED = b"12345678901234567890"
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]
NOW = datetime(2026, 10, 17, 10, 0, 15, tzinfo=UTC)
SECRET = bytes(range(SECRET_BYTES))


@pytest.mark.parametrize(("unix_time", "eight_digits"), RFC_VECTORS)
def test_codes_match_the_rfc_6238_test_vectors(unix_time, eight_digits):
    step = unix_time // second_factor.PERIOD_SECONDS

    assert second_factor.code_at_step(RFC_SEED, step) == eight_digits[-6:]


def test_a_step_is_thirty_seconds():
    start = datetime(2026, 10, 17, 10, 0, 0, tzinfo=UTC)

    assert second_factor.step_at(start + timedelta(seconds=29)) == (
        second_factor.step_at(start)
    )
    assert second_factor.step_at(start + timedelta(seconds=30)) == (
        second_factor.step_at(start) + 1
    )


def code(offset: int) -> str:
    """The code shown `offset` steps from NOW's."""
    return second_factor.code_at_step(SECRET, second_factor.step_at(NOW) + offset)


def test_the_current_code_is_accepted():
    assert second_factor.accepted_step(SECRET, code(0), NOW, None) == (
        second_factor.step_at(NOW)
    )


def test_the_code_from_just_before_is_accepted_for_typing_time():
    assert second_factor.accepted_step(SECRET, code(-1), NOW, None) == (
        second_factor.step_at(NOW) - 1
    )


@pytest.mark.parametrize("offset", [-3, -2, 1, 2])
def test_an_older_or_a_future_code_is_refused(offset):
    assert second_factor.accepted_step(SECRET, code(offset), NOW, None) is None


def test_a_code_works_once():
    step = second_factor.accepted_step(SECRET, code(0), NOW, None)

    assert second_factor.accepted_step(SECRET, code(0), NOW, step) is None


def test_after_the_current_code_the_one_before_is_refused_too():
    """Otherwise a code read over someone's shoulder would still work."""
    step = second_factor.accepted_step(SECRET, code(0), NOW, None)

    assert second_factor.accepted_step(SECRET, code(-1), NOW, step) is None


def test_after_the_previous_code_the_current_one_still_works():
    step = second_factor.accepted_step(SECRET, code(-1), NOW, None)

    assert second_factor.accepted_step(SECRET, code(0), NOW, step) == step + 1


def test_a_wrong_code_is_refused():
    wrong = f"{(int(code(0)) + 1) % 1_000_000:06d}"

    assert second_factor.accepted_step(SECRET, wrong, NOW, None) is None


def test_another_secret_s_code_is_refused():
    other = bytes(reversed(SECRET))

    assert second_factor.accepted_step(other, code(0), NOW, None) is None


def test_a_new_secret_is_160_random_bits():
    first, second = second_factor.new_secret(), second_factor.new_secret()

    assert len(first) == SECRET_BYTES == 20
    assert first != second


def test_the_secret_is_shown_as_unpadded_base32():
    text = second_factor.secret_text(SECRET)

    assert re.fullmatch(r"[A-Z2-7]{32}", text)
    assert base64.b32decode(text) == SECRET


def test_the_setup_link_carries_the_secret_and_the_issuer():
    link = urlsplit(second_factor.setup_link(SECRET, "admin-1f0c2a9b"))
    query = parse_qs(link.query)

    assert link.scheme == "otpauth"
    assert link.netloc == "totp"
    assert query["secret"] == [second_factor.secret_text(SECRET)]
    assert query["issuer"] == [second_factor.ISSUER]
    assert "admin-1f0c2a9b" in link.path


def test_a_ticket_fits_the_shape_the_api_accepts():
    ticket = second_factor.new_ticket()
    pattern = SetupTicket.__metadata__[0].metadata[0].pattern

    assert re.fullmatch(pattern, ticket)
    assert ticket != second_factor.new_ticket()


def test_a_ticket_is_stored_as_its_sha256():
    hashed = second_factor.hash_ticket("example_ticket_not_a_real_one_01")

    assert re.fullmatch(r"[0-9a-f]{64}", hashed)
    assert hashed != second_factor.hash_ticket("example_ticket_not_a_real_one_02")
