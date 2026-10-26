"""Connected accounts switched on for a test, with fake platforms (item 29, D-134).

The fixture is `platforms`, in this folder's conftest.py.

Nothing here reaches Instagram or Google: `FakePlatformClient` answers, set
by each test. The token key is plain on purpose: a random-looking literal
would be flagged by the history's secret scan, and a test key protects
nothing.
"""

from collections.abc import Iterator

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.modules.profiles import connection_service
from app.modules.profiles.platform_clients import FakePlatformClient, PlatformProfile

REDIRECT_BASE = "https://app.nicheconnect.test/connect"
META_SECRET = "test-meta-app-secret-for-signatures"
TOKEN_KEY = "test-platform-token-key-not-a-secret"
NOTICE = "connect-v1"


@pytest.fixture
def platforms(monkeypatch) -> Iterator[dict[str, FakePlatformClient]]:
    fakes = {
        "instagram": FakePlatformClient(platform="instagram", uses_pkce=False),
        "youtube": FakePlatformClient(platform="youtube", uses_pkce=True),
    }
    monkeypatch.setattr(settings, "platform_connections_enabled", True)
    monkeypatch.setattr(settings, "platform_redirect_base", REDIRECT_BASE)
    monkeypatch.setattr(settings, "meta_app_id", "123456789")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr(META_SECRET))
    monkeypatch.setattr(
        settings, "google_client_id", "test-client.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "google_client_secret", SecretStr("test-google-secret"))
    monkeypatch.setattr(settings, "platform_token_key", SecretStr(TOKEN_KEY))
    monkeypatch.setattr(settings, "connect_notice_version", NOTICE)
    monkeypatch.setattr(connection_service, "get_platform_client", lambda p: fakes[p])
    yield fakes


def profile(
    user_id: str = "17841400000000001", handle: str = "priya.eats", followers=24_000
):
    return PlatformProfile(platform_user_id=user_id, handle=handle, followers=followers)
