"""Work out who is really calling, for rate limiting.

Behind a load balancer every request arrives from the proxy, so limits keyed
on the socket address would put all users in one bucket: one attacker could
lock everyone out. X-Forwarded-For fixes that, but anyone can send it, so it
is trusted only when the connection itself comes from a proxy we configured
(TRUSTED_PROXIES). Empty by default: trust nothing.
"""

import ipaddress
from functools import lru_cache

from starlette.requests import Request

from app.core.config import settings

FORWARDED_FOR = "x-forwarded-for"
UNKNOWN = "unknown"


@lru_cache(maxsize=8)
def _parse_networks(raw: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Read the setting into networks, ignoring anything unparseable."""
    networks = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def trusted_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    return _parse_networks(settings.trusted_proxies)


def _is_trusted(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed in network for network in trusted_networks())


def client_ip(request: Request) -> str:
    """The caller's address: the socket address, or the client behind a trusted proxy.

    X-Forwarded-For is read right to left, skipping our own proxies, so a
    forged value prepended by the caller is never used.
    """
    socket_address = request.client.host if request.client else UNKNOWN
    if not _is_trusted(socket_address):
        return socket_address

    forwarded = request.headers.get(FORWARDED_FOR, "")
    for candidate in reversed([part.strip() for part in forwarded.split(",") if part.strip()]):
        if not _is_trusted(candidate):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                break  # malformed entry: stop and fall back
            return candidate
    # Every hop is one of ours, or the header is missing or malformed.
    return socket_address
