from collections.abc import Callable
from typing import Any

from slowapi import Limiter
from starlette.requests import Request

from app.core.client_ip import client_ip
from app.core.config import settings

# Keyed by the caller's address, which behind a trusted proxy is the real
# client rather than the proxy (app/core/client_ip.py).
#
# Counters live where RATE_LIMIT_STORAGE_URI says. In memory they are per
# process, so two processes would each allow the full limit; Redis shares one
# count across every process (D-003).
limiter = Limiter(
    key_func=client_ip,
    default_limits=["60/minute"],
    storage_uri=settings.rate_limit_storage_uri,
)


def per_account(request: Request) -> str:
    """Key a limit by the signed-in account rather than the address.

    For limits on what a person may do, not what a network may send: an
    office behind one address is not one person, and one person does not
    escape a limit by changing networks. `get_current_account` records the
    account before the limit is checked, since slowapi checks it when the
    endpoint runs, after its dependencies. Falls back to the address when
    there is no account, which only an unauthenticated route would see.
    """
    account_id = getattr(request.state, "account_id", None)
    return f"account:{account_id}" if account_id else client_ip(request)


def rate_limit[Endpoint: Callable[..., Any]](
    value: str, *, key: Callable[[Request], str] | None = None
) -> Callable[[Endpoint], Endpoint]:
    """`limiter.limit(value)`, with the endpoint's type kept.

    slowapi declares its decorator as returning a bare `Callable`, so every
    endpoint behind it read to mypy as a function returning `Any`, and
    nothing about its signature was checked. The decorator returns the same
    function, wrapped with `functools.wraps`, which is what this says.
    Routers use this, never `limiter.limit` directly.
    """
    decorator: Callable[[Endpoint], Endpoint] = (
        limiter.limit(value) if key is None else limiter.limit(value, key_func=key)
    )
    return decorator
