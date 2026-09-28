"""RFC 3161 timestamps (D-060), checked against real DigiCert and Sectigo tokens.

fixtures/*_probe.tsr are genuine tokens both authorities issued on
26 September 2026 over SHA-256("probe"), saved byte for byte. They make the
verification tests real without reaching the network. The one test that
does reach the authorities runs only with LIVE_TSA=1.
"""

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from app.modules.deal_memo import timestamp_authority as tsa
from app.modules.deal_memo.timestamp_authority import (
    MAX_ATTEMPTS,
    Rfc3161Authority,
    TimestampFailed,
    verify,
    with_sorted_certificates,
)

FIXTURES = Path(__file__).parent / "fixtures"
PROBE = hashlib.sha256(b"probe").digest()
ISSUED = {
    "digicert": datetime(2026, 9, 26, 18, 3, 44, tzinfo=UTC),
    "sectigo": datetime(2026, 9, 26, 18, 3, 45, tzinfo=UTC),
}


def token(name: str) -> bytes:
    return (FIXTURES / f"{name}_probe.tsr").read_bytes()


# --- checking real tokens ---------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ISSUED))
def test_a_genuine_token_verifies_and_gives_the_authoritys_time(name):
    assert verify(token(name), PROBE, nonce=None) == ISSUED[name]


@pytest.mark.parametrize("name", sorted(ISSUED))
def test_a_token_does_not_vouch_for_other_data(name):
    with pytest.raises(TimestampFailed):
        verify(token(name), hashlib.sha256(b"something else").digest(), nonce=None)


@pytest.mark.parametrize("name", sorted(ISSUED))
def test_a_token_with_a_changed_signed_byte_is_refused(name):
    original = token(name)
    # The fingerprint itself sits inside the signed content: change one byte of it.
    imprint = hashlib.sha256(PROBE).digest()
    at = original.index(imprint)
    tampered = original[:at] + bytes([original[at] ^ 0x01]) + original[at + 1 :]

    with pytest.raises(TimestampFailed):
        verify(tampered, PROBE, nonce=None)


@pytest.mark.parametrize("name", sorted(ISSUED))
def test_a_replayed_answer_to_someone_elses_request_is_refused(name):
    """A fresh answer must carry the nonce we sent."""
    with pytest.raises(TimestampFailed):
        verify(token(name), PROBE, nonce=12345)


# --- the certificate-order repair ---------------------------------------------------


@pytest.mark.parametrize("name", sorted(ISSUED))
def test_sorting_the_certificates_keeps_every_byte_and_the_length(name):
    original = token(name)
    sorted_copy = with_sorted_certificates(original)

    assert sorted_copy != original  # both authorities send them out of order
    assert len(sorted_copy) == len(original)
    assert sorted(sorted_copy) == sorted(original)  # same bytes, rearranged
    assert with_sorted_certificates(sorted_copy) == sorted_copy  # already in order


def test_something_that_is_not_a_timestamp_reply_is_refused():
    with pytest.raises(ValueError):
        with_sorted_certificates(b"\x04\x03abc")


def test_a_malformed_reply_is_a_timestamp_failure_not_a_crash():
    with pytest.raises(TimestampFailed):
        verify(b"\x30\x03\x02\x01\x00", PROBE, nonce=None)


# --- asking --------------------------------------------------------------------------


class FakeAuthority:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def authority(fake: FakeAuthority, sleeps: list[float] | None = None) -> Rfc3161Authority:
    recorded = sleeps if sleeps is not None else []
    return Rfc3161Authority(
        "digicert",
        "https://tsa.example.test",
        client=httpx2.Client(transport=httpx2.MockTransport(fake)),
        sleep=recorded.append,
        jitter=lambda: 0.5,
    )


def test_a_stamp_is_checked_against_the_nonce_we_sent_and_kept_as_issued(monkeypatch):
    fake = FakeAuthority(httpx2.Response(200, content=token("digicert")))
    seen: dict = {}

    def checking(body, fingerprint, *, nonce):
        seen.update(body=body, fingerprint=fingerprint, nonce=nonce)
        return ISSUED["digicert"]

    monkeypatch.setattr(tsa, "verify", checking)

    stamp = authority(fake).stamp(PROBE)

    [request] = fake.requests
    assert request.headers["content-type"] == "application/timestamp-query"
    assert seen["fingerprint"] == PROBE
    assert isinstance(seen["nonce"], int)  # a fresh nonce, not None
    assert stamp.token == token("digicert")  # the original bytes, not the sorted copy
    assert stamp.signed_at == ISSUED["digicert"]


def test_an_answer_that_does_not_verify_is_not_kept():
    """The real token carries another request's nonce, so it must be refused."""
    fake = FakeAuthority(httpx2.Response(200, content=token("digicert")))

    with pytest.raises(TimestampFailed):
        authority(fake).stamp(PROBE)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_busy_authority_is_retried(monkeypatch, status):
    monkeypatch.setattr(tsa, "verify", lambda *a, **k: ISSUED["digicert"])
    fake = FakeAuthority(httpx2.Response(status), httpx2.Response(200, content=b"ok"))
    sleeps: list[float] = []

    authority(fake, sleeps).stamp(PROBE)

    assert len(fake.requests) == 2
    assert sleeps == [0.5]


def test_it_gives_up_after_three_attempts():
    fake = FakeAuthority(*[httpx2.ConnectError("down")] * MAX_ATTEMPTS)
    sleeps: list[float] = []

    with pytest.raises(TimestampFailed, match="after 3 attempts"):
        authority(fake, sleeps).stamp(PROBE)

    assert len(fake.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_a_refusal_is_not_retried():
    fake = FakeAuthority(httpx2.Response(400))

    with pytest.raises(TimestampFailed, match="status 400"):
        authority(fake).stamp(PROBE)

    assert len(fake.requests) == 1


# --- the real authorities, only when asked ---------------------------------------------


@pytest.mark.skipif(
    os.environ.get("LIVE_TSA") != "1",
    reason="set LIVE_TSA=1 to call the real authorities",
)
@pytest.mark.parametrize("name", sorted(tsa.AUTHORITY_URLS))
def test_the_real_authority_stamps_and_verifies(name):
    stamp = Rfc3161Authority(name, tsa.AUTHORITY_URLS[name]).stamp(PROBE)

    assert abs((stamp.signed_at - datetime.now(UTC)).total_seconds()) < 300
    assert verify(stamp.token, PROBE, nonce=None) == stamp.signed_at
