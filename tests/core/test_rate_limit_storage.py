"""Rate-limit counters must be shared once more than one process runs (D-003).

In memory each process keeps its own count, so two processes would each allow
the full limit. These tests show that difference, and that the setting picks
the storage.
"""

import pytest
from limits import parse
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from pydantic import ValidationError
from slowapi import Limiter

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.rate_limit import limiter
from tests.core.test_config import valid_values

REDIS_URI = "redis://localhost:6379/1"


def make_limiter(storage_uri: str) -> Limiter:
    """A limiter like the app's, standing in for a second process."""
    return Limiter(
        key_func=client_ip, default_limits=["60/minute"], storage_uri=storage_uri
    )


def hits_until_refused(storages: list, item, key: str, attempts: int) -> list[bool]:
    """Alternate between the storages, as two processes would."""
    strategies = [FixedWindowRateLimiter(storage) for storage in storages]
    return [
        strategies[index % len(strategies)].hit(item, key) for index in range(attempts)
    ]


def test_the_app_uses_the_storage_from_settings():
    assert type(limiter._storage).__name__ in ("MemoryStorage", "RedisStorage")


def test_the_default_is_in_memory():
    assert (
        Settings(_env_file=None, **valid_values()).rate_limit_storage_uri == "memory://"
    )


@pytest.mark.parametrize(
    "uri", ["memory://", "redis://localhost:6379/1", "rediss://host:6379"]
)
def test_known_storage_values_are_accepted(uri):
    settings = Settings(_env_file=None, **valid_values(rate_limit_storage_uri=uri))

    assert settings.rate_limit_storage_uri == uri


@pytest.mark.parametrize("uri", ["memcached://localhost", "http://localhost", ""])
def test_unknown_storage_values_are_rejected(uri):
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, **valid_values(rate_limit_storage_uri=uri))

    assert "rate_limit_storage_uri" in str(exc_info.value)


def test_two_processes_each_get_their_own_count_in_memory():
    """The reason Redis is needed: in memory the limit is per process."""
    first, second = make_limiter("memory://"), make_limiter("memory://")
    item = parse("2/minute")
    key = "memory-demo"

    results = hits_until_refused([first._storage, second._storage], item, key, 4)

    # Each storage allows 2, so all four attempts succeed: the limit doubled.
    assert results == [True, True, True, True]


def test_two_processes_share_one_count_in_redis():
    storage = storage_from_string(REDIS_URI)
    if not storage.check():
        pytest.fail("Redis is not reachable at " + REDIS_URI)
    first, second = make_limiter(REDIS_URI), make_limiter(REDIS_URI)
    item = parse("2/minute")
    key = "redis-demo"
    first._storage.clear(item.key_for(key))

    results = hits_until_refused([first._storage, second._storage], item, key, 4)

    # One shared count: the third attempt is refused whichever process it hits.
    assert results == [True, True, False, False]
    first._storage.clear(item.key_for(key))


def test_a_redis_backed_limiter_can_be_reset():
    storage = storage_from_string(REDIS_URI)
    if not storage.check():
        pytest.fail("Redis is not reachable at " + REDIS_URI)
    item = parse("1/minute")
    key = "redis-reset-demo"
    strategy = FixedWindowRateLimiter(storage)
    assert strategy.hit(item, key) is True
    assert strategy.hit(item, key) is False

    storage.clear(item.key_for(key))

    assert strategy.hit(item, key) is True
    storage.clear(item.key_for(key))
