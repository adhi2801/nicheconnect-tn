"""Signed timestamps from outside authorities, RFC 3161 (D-060).

An authority signs "this fingerprint existed at this time" with its own key.
We ask for the root of the day's checkpoint, check the answer, and keep the
signed token **exactly as issued**, so anyone can check it with
`openssl ts -verify` and a standard root certificate bundle, without our code.

What is checked before a token is kept: the authority granted it; it signs
the fingerprint we sent; it carries the nonce we sent (so it is a fresh
answer to our request, not a replay); and its signing certificate chains to
a root in the Mozilla store (`certifi`), which is how `openssl` would judge
it too.

**One repair, and why it is safe.** Both authorities attach their
certificates in an order that strict DER forbids, and the verifying library
parses strictly. The certificate list is not part of what is signed in a
CMS SignedData, so verification is done on a copy with only that list
sorted: every byte kept, lengths unchanged. The token stored is the original.

External-call rules (`backend.md` section 6): 3 s connect, 10 s read, at
most 3 attempts with backoff and jitter, retrying only a network failure,
429 or a 5xx. Only a SHA-256 fingerprint leaves the building.
"""

import logging
import random
import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import cache

import certifi
import httpx2
from cryptography import x509
from rfc3161_client import (
    HashAlgorithm,
    TimestampRequestBuilder,
    VerifierBuilder,
    decode_timestamp_response,
)
from rfc3161_client.errors import VerificationError

logger = logging.getLogger(__name__)

# Run by different companies, so no single outage or compromise matters.
# DigiCert's endpoint is plain HTTP by DigiCert's own design: the token is
# signed, and the request carries only a fingerprint.
AUTHORITY_URLS: dict[str, str] = {
    "digicert": "http://timestamp.digicert.com",
    "sectigo": "https://timestamp.sectigo.com",
}
TIMEOUT = httpx2.Timeout(10.0, connect=3.0)
MAX_ATTEMPTS = 3
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
BASE_DELAY_SECONDS = 0.5
CONTENT_TYPE = "application/timestamp-query"


class TimestampFailed(RuntimeError):
    """No usable timestamp from this authority. The checkpoint stays unstamped."""


@dataclass(frozen=True)
class Stamp:
    token: bytes  # exactly as the authority issued it
    signed_at: datetime  # the authority's own time, from inside the token


@cache
def trusted_roots() -> tuple[x509.Certificate, ...]:
    """The Mozilla root store, as shipped by certifi."""
    with warnings.catch_warnings():
        # One long-standing root in the bundle has a serial number that
        # cryptography warns about. It is not one our authorities use.
        warnings.simplefilter("ignore")
        with open(certifi.where(), "rb") as bundle:
            return tuple(x509.load_pem_x509_certificates(bundle.read()))


# --- the certificate-order repair -------------------------------------------------


def _tlv(buf: bytes, pos: int) -> tuple[int, int, int]:
    """(tag, content start, content end) of the DER element at `pos`."""
    tag, first = buf[pos], buf[pos + 1]
    pos += 2
    if first < 0x80:
        return tag, pos, pos + first
    count = first & 0x7F
    if count == 0:
        raise ValueError("indefinite length: not DER")
    length = int.from_bytes(buf[pos : pos + count], "big")
    return tag, pos + count, pos + count + length


def _elements(buf: bytes, start: int, end: int) -> list[tuple[int, int, int, int]]:
    """(tag, element start, content start, end) of each element in a container."""
    found = []
    pos = start
    while pos < end:
        tag, content_start, content_end = _tlv(buf, pos)
        found.append((tag, pos, content_start, content_end))
        pos = content_end
    if pos != end:
        raise ValueError("elements overrun their container")
    return found


def with_sorted_certificates(response: bytes) -> bytes:
    """A copy of a TimeStampResp whose SignedData certificates are in DER order.

    Walks TimeStampResp > timeStampToken (ContentInfo) > [0] > SignedData >
    [0] certificates, and sorts that SET's elements by their encoding, as
    DER requires. Nothing else moves and no length changes.
    """
    tag, start, end = _tlv(response, 0)
    if tag != 0x30:
        raise ValueError("not a TimeStampResp")
    parts = _elements(response, start, end)
    if len(parts) < 2:
        return response  # a refusal carries no token, so nothing to sort
    token = parts[1]
    content_info = _elements(response, token[2], token[3])
    if len(content_info) < 2 or content_info[1][0] != 0xA0:
        raise ValueError("timeStampToken is not a ContentInfo with content")
    explicit = content_info[1]
    signed_data = _elements(response, explicit[2], explicit[3])[0]
    fields = _elements(response, signed_data[2], signed_data[3])
    certificates = [f for f in fields if f[0] == 0xA0]
    if not certificates:
        return response
    _, _, set_start, set_end = certificates[0]
    members = sorted(
        response[s:e] for (_, s, _, e) in _elements(response, set_start, set_end)
    )
    return response[:set_start] + b"".join(members) + response[set_end:]


# --- asking and checking ---------------------------------------------------------


def verify(token: bytes, fingerprint: bytes, *, nonce: int | None) -> datetime:
    """Check a token signs `fingerprint`; return the authority's time.

    Raises TimestampFailed. `nonce` is required when checking a fresh answer;
    None is only for re-checking a stored token, whose nonce was checked
    when it was received.
    """
    try:
        response = decode_timestamp_response(with_sorted_certificates(token))
        builder = VerifierBuilder(nonce=nonce)
        for root_certificate in trusted_roots():
            builder = builder.add_root_certificate(root_certificate)
        builder.build().verify_message(response, fingerprint)
    except (ValueError, VerificationError) as exc:
        raise TimestampFailed(f"the token did not verify ({type(exc).__name__})") from exc
    signed_at: datetime = response.tst_info.gen_time
    return signed_at


class Rfc3161Authority:
    """One timestamp authority, spoken to over RFC 3161."""

    def __init__(
        self,
        name: str,
        url: str,
        *,
        client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.name = name
        self._url = url
        self._client = client or httpx2.Client(timeout=TIMEOUT)
        self._sleep = sleep
        self._jitter = jitter

    def stamp(self, fingerprint: bytes) -> Stamp:
        """Ask for, and check, a timestamp over `fingerprint`."""
        request = (
            TimestampRequestBuilder()
            .data(fingerprint)
            .hash_algorithm(HashAlgorithm.SHA256)
            .nonce(nonce=True)
            .cert_request(cert_request=True)
            .build()
        )
        body = self._post(request.as_bytes())
        signed_at = verify(body, fingerprint, nonce=request.nonce)
        return Stamp(token=body, signed_at=signed_at)

    def _post(self, request: bytes) -> bytes:
        failure = "no attempt made"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.post(
                    self._url, content=request, headers={"Content-Type": CONTENT_TYPE}
                )
            except httpx2.TransportError as exc:
                failure = type(exc).__name__
            else:
                if response.status_code in RETRY_STATUSES:
                    failure = f"status {response.status_code}"
                elif response.is_success:
                    return response.content
                else:
                    raise TimestampFailed(
                        f"{self.name} refused the request (status {response.status_code})"
                    )
            logger.warning(
                "timestamp.retry authority=%s attempt=%d reason=%s",
                self.name,
                attempt,
                failure,
            )
            if attempt < MAX_ATTEMPTS:
                delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
                self._sleep(delay * (0.5 + self._jitter()))
        raise TimestampFailed(
            f"{self.name} unreachable after {MAX_ATTEMPTS} attempts ({failure})"
        )


def default_authorities() -> list[Rfc3161Authority]:
    return [Rfc3161Authority(name, url) for name, url in AUTHORITY_URLS.items()]
