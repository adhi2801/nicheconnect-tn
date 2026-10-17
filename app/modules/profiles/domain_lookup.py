"""Asking the world about a brand's domain: its TXT record, and its age (item 74, D-106).

**DNS over HTTPS, two resolvers.** Cloudflare's and Google's public
resolvers both validate DNSSEC and answer over TLS, so nothing between us
and them can forge an answer, and an answer one of them got wrong cannot
verify a domain alone: the IETF draft asks for a DNSSEC-validating resolver,
and for diverse resolvers to cross-check when the zone is unsigned (9.7).
Both are asked through the HTTP client the app already uses, so no DNS
library is added. The host asked about is the brand's, but the hosts we
call are only these fixed ones, never a URL anyone gives us (security.md,
API7).

**RDAP for the date it was registered.** IANA's bootstrap file names each
top-level domain's registry server (the .in registry's since 2026); the
registration event gives the date. A registry that does not answer, or does
not say, gives None, which is shown as "not known", never guessed.

Every call has short timeouts and at most 3 attempts with backoff and
jitter, and runs only in the background job (CLAUDE.md section 3).
"""

import logging
import random
import re
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Protocol

import httpx2

from app.modules.profiles.brand_domains import ResolverAnswer

logger = logging.getLogger(__name__)

RESOLVERS: tuple[str, ...] = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)
RDAP_BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
TIMEOUT = httpx2.Timeout(10.0, connect=3.0)
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 0.5
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
TXT_TYPE = 16
# DNS response codes: 0 is an answer, 3 is "no such name", which is an
# answer too (the record is absent). Anything else is a failure to answer.
NOERROR, NXDOMAIN = 0, 3
_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
# The bootstrap file changes rarely; a day is plenty.
BOOTSTRAP_TTL_SECONDS = 24 * 60 * 60


class DomainLookup(Protocol):
    def txt(self, name: str) -> list[ResolverAnswer]: ...

    def registered_on(self, domain: str) -> date | None: ...


def txt_strings(data: str) -> str:
    """One TXT record's text: its quoted strings joined, as RFC 7208 reads them."""
    parts = _QUOTED.findall(data)
    if not parts:
        return data
    return "".join(part.replace('\\"', '"').replace("\\\\", "\\") for part in parts)


def parse_doh_answer(body: Any) -> ResolverAnswer:
    """A DNS-over-HTTPS JSON answer (RFC 8427's shape, as both resolvers send it)."""
    if not isinstance(body, dict) or not isinstance(body.get("Status"), int):
        return ResolverAnswer(values=None)
    status = body["Status"]
    if status == NXDOMAIN:
        return ResolverAnswer(values=(), authenticated=body.get("AD") is True)
    if status != NOERROR:
        return ResolverAnswer(values=None)
    records = body.get("Answer") or []
    values = tuple(
        txt_strings(record["data"])
        for record in records
        if isinstance(record, dict)
        and record.get("type") == TXT_TYPE
        and isinstance(record.get("data"), str)
    )
    return ResolverAnswer(values=values, authenticated=body.get("AD") is True)


def registration_date(body: Any) -> date | None:
    """The `registration` event of an RDAP domain answer (RFC 9083), or None."""
    if not isinstance(body, dict):
        return None
    for event in body.get("events") or []:
        if isinstance(event, dict) and event.get("eventAction") == "registration":
            try:
                return datetime.fromisoformat(
                    str(event.get("eventDate")).replace("Z", "+00:00")
                ).date()
            except ValueError:
                return None
    return None


def rdap_base_for(bootstrap: Any, domain: str) -> str | None:
    """The registry's RDAP server for this domain's top-level domain, from IANA's file."""
    tld = domain.rsplit(".", 1)[-1]
    if not isinstance(bootstrap, dict):
        return None
    for service in bootstrap.get("services") or []:
        if (
            isinstance(service, list)
            and len(service) == 2
            and tld in service[0]
            and service[1]
            and isinstance(service[1][0], str)
            and service[1][0].startswith("https://")
        ):
            base: str = service[1][0]
            return base if base.endswith("/") else f"{base}/"
    return None


class HttpsDomainLookup:
    """The real lookups, over HTTPS. One client, reused between calls."""

    def __init__(
        self,
        client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or httpx2.Client(timeout=TIMEOUT)
        self._sleep = sleep
        self._jitter = jitter
        self._clock = clock
        self._bootstrap: tuple[float, Any] | None = None

    def txt(self, name: str) -> list[ResolverAnswer]:
        return [
            parse_doh_answer(
                self._get_json(
                    resolver,
                    params={"name": name, "type": "TXT"},
                    headers={"accept": "application/dns-json"},
                )
            )
            for resolver in RESOLVERS
        ]

    def registered_on(self, domain: str) -> date | None:
        base = rdap_base_for(self._bootstrap_file(), domain)
        if base is None:
            return None
        return registration_date(
            self._get_json(
                f"{base}domain/{domain}", headers={"accept": "application/rdap+json"}
            )
        )

    def _bootstrap_file(self) -> Any:
        now = self._clock()
        if self._bootstrap is None or now - self._bootstrap[0] > BOOTSTRAP_TTL_SECONDS:
            body = self._get_json(RDAP_BOOTSTRAP)
            if body is None:
                return None
            self._bootstrap = (now, body)
        return self._bootstrap[1]

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """The JSON body, or None after MAX_ATTEMPTS. Never raises."""
        failure = "no attempt made"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.get(url, params=params, headers=headers)
            except httpx2.TransportError as exc:
                failure = type(exc).__name__
            else:
                if response.is_success:
                    try:
                        return response.json()
                    except ValueError:
                        return None
                if response.status_code not in RETRY_STATUSES:
                    # 404 from a registry means "not ours to say"; asking
                    # again would only repeat it.
                    return None
                failure = f"status {response.status_code}"
            # The host, never the domain: it is the brand's, and logs keep
            # events, not data (backend.md section 9).
            logger.warning(
                "domain_lookup.retry host=%s attempt=%d reason=%s",
                httpx2.URL(url).host,
                attempt,
                failure,
            )
            if attempt < MAX_ATTEMPTS:
                delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
                self._sleep(delay * (0.5 + self._jitter()))
        return None


class FakeDomainLookup:
    """Answers set by a test; nothing leaves the process."""

    def __init__(self) -> None:
        self.records: dict[str, list[ResolverAnswer]] = {}
        self.dates: dict[str, date | None] = {}
        self.asked: list[str] = []

    def publish(self, name: str, *values: str, authenticated: bool = True) -> None:
        """Both resolvers see these values at `name`."""
        answer = ResolverAnswer(values=tuple(values), authenticated=authenticated)
        self.records[name] = [answer, answer]

    def txt(self, name: str) -> list[ResolverAnswer]:
        self.asked.append(name)
        return self.records.get(
            name, [ResolverAnswer(values=()), ResolverAnswer(values=())]
        )

    def registered_on(self, domain: str) -> date | None:
        return self.dates.get(domain)


_default: HttpsDomainLookup | None = None


def get_domain_lookup() -> DomainLookup:
    """The lookup the job uses: the real one, made once."""
    global _default
    if _default is None:
        _default = HttpsDomainLookup()
    return _default
