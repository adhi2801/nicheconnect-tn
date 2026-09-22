from collections.abc import Callable
from typing import Any

from slowapi import Limiter

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


def rate_limit[Endpoint: Callable[..., Any]](
    value: str,
) -> Callable[[Endpoint], Endpoint]:
    """`limiter.limit(value)`, with the endpoint's type kept.

    slowapi declares its decorator as returning a bare `Callable`, so every
    endpoint behind it read to mypy as a function returning `Any`, and
    nothing about its signature was checked. The decorator returns the same
    function, wrapped with `functools.wraps`, which is what this says.
    Routers use this, never `limiter.limit` directly.
    """
    decorator: Callable[[Endpoint], Endpoint] = limiter.limit(value)
    return decorator
