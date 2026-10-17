"""A brand's domain claim, as pure rules (item 74, D-106).

No database and no network: what a domain must look like, what the brand
publishes, what a set of resolver answers means, and what a check does to a
claim. The service and the job apply these; the tests prove them alone.

**The registrable domain only.** A claim is for the name a registrar sold,
never a public suffix (`co.in`, `myshopify.com`) and never a name under one
(`nykaa.com.evil.ru` is a claim to `evil.ru`), following the Public Suffix
List, as the IETF draft asks (9.9). Punycode and non-Latin letters are
refused, as for links (`app/core/links.py`): "nykaa.com" with one Cyrillic
letter in it reads as Nykaa to a person and as someone else to a computer.

**Two resolvers must agree.** Cloudflare's and Google's, asked over HTTPS
(`domain_lookup.py`). Found means both saw the token; absent means both
answered and not both saw it; unknown means one could not be asked. Only an
absent answer counts against a verified domain, so an outage never does.
"""

import base64
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from publicsuffixlist import PublicSuffixList

from app.modules.profiles.brand_domain_models import (
    DOMAIN_MAX_LENGTH,
    MAX_ABSENT_CHECKS,
)

RECORD_PREFIX = "_nicheconnect-challenge"
VALUE_PREFIX = "nicheconnect-domain-verification="
TOKEN_LIFETIME = timedelta(days=7)
# A verified domain is checked again a day after its last check.
RECHECK_AFTER = timedelta(hours=24)
_LABEL_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
_SUFFIXES = PublicSuffixList()


class DomainNotAccepted(ValueError):
    """Why a typed domain cannot be claimed, in words the brand can act on."""


def registrable_domain(typed: str) -> str:
    """The domain to claim, lower case, or DomainNotAccepted saying why not.

    A leading `www.` and a trailing dot are tolerated, since both are how
    people write their own site; anything else under the registrable domain
    is refused with the domain to claim instead.
    """
    domain = typed.strip().lower().removesuffix(".")
    if not domain or len(domain) > DOMAIN_MAX_LENGTH:
        raise DomainNotAccepted("Enter your website's domain, such as smallshop.in")
    labels = domain.split(".")
    for label in labels:
        if not label or len(label) > 63 or not set(label) <= _LABEL_CHARACTERS:
            raise DomainNotAccepted(
                "Use only letters a to z, digits, hyphens and dots, such as smallshop.in"
            )
        if label.startswith("-") or label.endswith("-"):
            raise DomainNotAccepted(
                "A part of a domain cannot start or end with a hyphen"
            )
        if label.startswith("xn--"):
            raise DomainNotAccepted(
                "Domains in other scripts cannot be claimed: their letters can "
                "pass for someone else's"
            )
    if len(labels) < 2 or _SUFFIXES.is_public(domain):
        raise DomainNotAccepted(
            "That is a suffix many sites share, not one website: enter your own domain"
        )
    registrable = _SUFFIXES.privatesuffix(domain)
    if registrable is None:
        raise DomainNotAccepted("Enter your website's domain, such as smallshop.in")
    if domain == f"www.{registrable}":
        return registrable
    if domain != registrable:
        raise DomainNotAccepted(
            f"Claim the domain itself, {registrable}: a name under it is not "
            "the whole website"
        )
    return registrable


def new_token() -> str:
    """A 128-bit random token, base32 in lower case: TOKEN_LENGTH (26) characters."""
    return base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=").lower()


def record_name(domain: str) -> str:
    """Where the brand publishes the TXT record."""
    return f"{RECORD_PREFIX}.{domain}"


def record_value(token: str) -> str:
    """What the TXT record says."""
    return f"{VALUE_PREFIX}{token}"


# --- what the resolvers said ------------------------------------------------------------


@dataclass(frozen=True)
class ResolverAnswer:
    """One resolver's answer for the record. `values` is None when it could not be asked."""

    values: tuple[str, ...] | None
    # The resolver validated DNSSEC for this answer (its AD bit).
    authenticated: bool = False


@dataclass(frozen=True)
class CheckOutcome:
    result: str  # found, absent or unknown (CHECK_RESULTS less taken)
    dnssec_validated: bool


def classify(answers: list[ResolverAnswer], token: str) -> CheckOutcome:
    """What a set of answers means for this token. Every resolver must answer."""
    wanted = record_value(token)
    if not answers or any(answer.values is None for answer in answers):
        return CheckOutcome(result="unknown", dnssec_validated=False)
    seen = [wanted in (answer.values or ()) for answer in answers]
    if all(seen):
        return CheckOutcome(
            result="found",
            dnssec_validated=all(answer.authenticated for answer in answers),
        )
    return CheckOutcome(result="absent", dnssec_validated=False)


# --- what a check does to a claim ---------------------------------------------------------


@dataclass(frozen=True)
class Transition:
    status: str
    consecutive_absent: int
    verified_now: bool = False
    lapsed_now: bool = False


def after_check(status: str, consecutive_absent: int, result: str) -> Transition:
    """A claim's next state after a check with this result.

    Pending becomes verified on `found`, and stays pending otherwise. Verified
    stays verified on `found` and `unknown` (an outage is not evidence),
    and lapses on the MAX_ABSENT_CHECKS-th `absent` in a row. Lapsed never
    changes: the brand claims again, with a new token.
    """
    if status == "pending":
        if result == "found":
            return Transition("verified", 0, verified_now=True)
        return Transition("pending", 0)
    if status == "verified":
        if result in ("found", "taken"):
            return Transition("verified", 0)
        if result == "unknown":
            return Transition("verified", consecutive_absent)
        absent = consecutive_absent + 1
        if absent >= MAX_ABSENT_CHECKS:
            return Transition("lapsed", MAX_ABSENT_CHECKS, lapsed_now=True)
        return Transition("verified", absent)
    return Transition(status, consecutive_absent)


def is_recheck_due(status: str, last_checked_at: datetime | None, now: datetime) -> bool:
    """A verified domain is checked again a day after its last check."""
    return (
        status == "verified"
        and last_checked_at is not None
        and now - last_checked_at >= RECHECK_AFTER
    )
