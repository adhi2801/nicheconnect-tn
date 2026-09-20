"""One shared Redis client for the app.

Redis is already the home of rate-limit counters (D-003). Anything else that
needs it should come through here rather than opening its own connection:
`redis.Redis.from_url` builds a connection pool, and one pool per process is
the point of it.

The readiness check in `health.py` deliberately keeps its own short-timeout
client, so a hung pool cannot make `/readyz` hang with it.
"""

import redis

from app.core.config import settings

# Short enough that a Redis problem surfaces as an error rather than a stall.
CONNECT_TIMEOUT_SECONDS = 2
OPERATION_TIMEOUT_SECONDS = 2

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """The shared client, built on first use."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
            socket_timeout=OPERATION_TIMEOUT_SECONDS,
        )
    return _client


def reset_redis() -> None:
    """Drop the client so the next call rebuilds it. For tests."""
    global _client
    if _client is not None:
        _client.close()
    _client = None
