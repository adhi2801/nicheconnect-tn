"""Talking to Instagram and YouTube (item 29, D-134).

One interface (`PlatformClient`), two real clients and a fake (choice c A).
The real clients follow Meta's and Google's published references, read 26
October 2026; **they have not yet run against the live platforms**, which
needs the apps Meta App Review and Google verification approve. Until then
the switch stays off and every test uses `FakePlatformClient`.

- **Instagram** (Instagram API with Instagram Login): the code is exchanged
  with our app secret for a 1-hour token, then for a 60-day one. Only
  `instagram_business_basic` is asked for: it covers the handle and
  `followers_count`, and least access is what App Review asks of us.
  Meta's Login does not document PKCE, so `state` and the secret guard it.
- **YouTube** (Google OAuth 2.0 and the Data API): PKCE (S256) and
  `access_type=offline` for a refresh token; `channels.list?mine=true`
  (1 quota unit) gives the channel's id, handle and subscriber count.

Every call has explicit timeouts (connect 3 s, read 10 s). A code is used
once, so its exchange is never retried; reads retry at most 3 times with
backoff and jitter (backend.md section 6). Nothing here logs a token, a
code or a handle.
"""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx2

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx2.Timeout(10.0, connect=3.0)
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 0.5
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

INSTAGRAM_AUTHORIZE = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_TOKEN = "https://api.instagram.com/oauth/access_token"  # noqa: S105 - a public URL, not a secret
INSTAGRAM_GRAPH = "https://graph.instagram.com"
INSTAGRAM_SCOPES = ("instagram_business_basic",)

GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 - a public URL, not a secret
GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
YOUTUBE_CHANNELS = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_SCOPES = ("https://www.googleapis.com/auth/youtube.readonly",)


class PlatformRefused(Exception):
    """The platform said no: a code expired, used or not ours, or access removed."""


class PlatformUnavailable(Exception):
    """The platform did not answer usably, after retrying where that is safe."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None


@dataclass(frozen=True)
class PlatformProfile:
    platform_user_id: str
    handle: str
    # None when the platform hides it (a YouTube channel can).
    followers: int | None


class PlatformClient(Protocol):
    platform: str
    uses_pkce: bool

    def authorize_url(
        self, *, redirect_uri: str, state: str, code_challenge: str | None
    ) -> str: ...

    def exchange(
        self, *, code: str, redirect_uri: str, code_verifier: str | None, now: datetime
    ) -> Tokens: ...

    def profile(self, tokens: Tokens) -> PlatformProfile: ...

    def refresh(self, tokens: Tokens, now: datetime) -> Tokens: ...

    def revoke(self, tokens: Tokens) -> None: ...


class _Http:
    """The shared HTTP habits: timeouts, and retries only where safe."""

    def __init__(
        self,
        client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._client = client or httpx2.Client(timeout=TIMEOUT)
        self._sleep = sleep
        self._jitter = jitter

    def post_once(self, url: str, data: dict[str, str]) -> Any:
        """A POST that must not repeat (a code is single use)."""
        try:
            response = self._client.post(url, data=data)
        except httpx2.TransportError as exc:
            raise PlatformUnavailable(type(exc).__name__) from exc
        return self._body(response, url)

    def get(self, url: str, *, params: dict[str, str], headers: dict[str, str]) -> Any:
        failure = "no attempt made"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._client.get(url, params=params, headers=headers)
            except httpx2.TransportError as exc:
                failure = type(exc).__name__
            else:
                if response.status_code not in RETRY_STATUSES:
                    return self._body(response, url)
                failure = f"status {response.status_code}"
            logger.warning(
                "platform.retry host=%s attempt=%d reason=%s",
                httpx2.URL(url).host,
                attempt,
                failure,
            )
            if attempt < MAX_ATTEMPTS:
                delay = BASE_DELAY_SECONDS * 2 ** (attempt - 1)
                self._sleep(delay * (0.5 + self._jitter()))
        raise PlatformUnavailable(failure)

    @staticmethod
    def _body(response: httpx2.Response, url: str) -> Any:
        if response.status_code in RETRY_STATUSES:
            raise PlatformUnavailable(f"status {response.status_code}")
        if not response.is_success:
            # The status only: a platform's error text can echo the code.
            logger.info(
                "platform.refused host=%s status=%d",
                httpx2.URL(url).host,
                response.status_code,
            )
            raise PlatformRefused(f"status {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise PlatformUnavailable("not JSON") from exc


def _expires(now: datetime, body: Any) -> datetime | None:
    seconds = body.get("expires_in") if isinstance(body, dict) else None
    if isinstance(seconds, int) and not isinstance(seconds, bool) and seconds > 0:
        return now + timedelta(seconds=seconds)
    return None


def _text(body: Any, *keys: str) -> str:
    value: Any = body
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    if value is None or isinstance(value, bool):
        raise PlatformUnavailable(f"no {'.'.join(keys)}")
    return str(value)


class InstagramClient:
    platform = "instagram"
    uses_pkce = False

    def __init__(self, http: _Http | None = None) -> None:
        self._http = http or _Http()

    def authorize_url(
        self, *, redirect_uri: str, state: str, code_challenge: str | None
    ) -> str:
        query = {
            "client_id": settings.meta_app_id or "",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(INSTAGRAM_SCOPES),
            "state": state,
        }
        return f"{INSTAGRAM_AUTHORIZE}?{urlencode(query)}"

    def exchange(
        self, *, code: str, redirect_uri: str, code_verifier: str | None, now: datetime
    ) -> Tokens:
        secret = (
            settings.meta_app_secret.get_secret_value()
            if settings.meta_app_secret
            else ""
        )
        short = self._http.post_once(
            INSTAGRAM_TOKEN,
            {
                "client_id": settings.meta_app_id or "",
                "client_secret": secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        long = self._http.get(
            f"{INSTAGRAM_GRAPH}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": secret,
                "access_token": _text(short, "access_token"),
            },
            headers={},
        )
        return Tokens(
            access_token=_text(long, "access_token"),
            refresh_token=None,
            expires_at=_expires(now, long),
        )

    def profile(self, tokens: Tokens) -> PlatformProfile:
        body = self._http.get(
            f"{INSTAGRAM_GRAPH}/me",
            params={"fields": "user_id,username,followers_count"},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        followers = body.get("followers_count") if isinstance(body, dict) else None
        return PlatformProfile(
            platform_user_id=_text(body, "user_id"),
            handle=_text(body, "username"),
            followers=followers
            if isinstance(followers, int) and followers >= 0
            else None,
        )

    def refresh(self, tokens: Tokens, now: datetime) -> Tokens:
        """A new 60-day token for one at least a day old and not yet expired."""
        body = self._http.get(
            f"{INSTAGRAM_GRAPH}/refresh_access_token",
            params={"grant_type": "ig_refresh_token"},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        return Tokens(
            access_token=_text(body, "access_token"),
            refresh_token=None,
            expires_at=_expires(now, body),
        )

    def revoke(self, tokens: Tokens) -> None:
        # Instagram Login offers no revoke call; removing our tokens, and the
        # creator removing the app in Instagram, is what ends access.
        return None


class YouTubeClient:
    platform = "youtube"
    uses_pkce = True

    def __init__(self, http: _Http | None = None) -> None:
        self._http = http or _Http()

    def authorize_url(
        self, *, redirect_uri: str, state: str, code_challenge: str | None
    ) -> str:
        query = {
            "client_id": settings.google_client_id or "",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
            "code_challenge": code_challenge or "",
            "code_challenge_method": "S256",
        }
        return f"{GOOGLE_AUTHORIZE}?{urlencode(query)}"

    def exchange(
        self, *, code: str, redirect_uri: str, code_verifier: str | None, now: datetime
    ) -> Tokens:
        secret = (
            settings.google_client_secret.get_secret_value()
            if settings.google_client_secret
            else ""
        )
        body = self._http.post_once(
            GOOGLE_TOKEN,
            {
                "client_id": settings.google_client_id or "",
                "client_secret": secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": code_verifier or "",
            },
        )
        refresh = body.get("refresh_token") if isinstance(body, dict) else None
        return Tokens(
            access_token=_text(body, "access_token"),
            refresh_token=refresh if isinstance(refresh, str) else None,
            expires_at=_expires(now, body),
        )

    def profile(self, tokens: Tokens) -> PlatformProfile:
        body = self._http.get(
            YOUTUBE_CHANNELS,
            params={"part": "snippet,statistics", "mine": "true"},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items:
            # A Google account with no channel has nothing to verify.
            raise PlatformRefused("no channel")
        channel = items[0]
        statistics = channel.get("statistics", {}) if isinstance(channel, dict) else {}
        hidden = statistics.get("hiddenSubscriberCount") is True
        raw = statistics.get("subscriberCount")
        followers = (
            int(raw) if isinstance(raw, str) and raw.isdigit() and not hidden else None
        )
        snippet = channel.get("snippet", {}) if isinstance(channel, dict) else {}
        handle = snippet.get("customUrl") or snippet.get("title")
        if not isinstance(handle, str) or not handle.strip():
            raise PlatformUnavailable("no channel name")
        return PlatformProfile(
            platform_user_id=_text(channel, "id"),
            handle=handle.strip()[:100],
            followers=followers,
        )

    def refresh(self, tokens: Tokens, now: datetime) -> Tokens:
        """A new access token from the refresh token, which stays the same."""
        if tokens.refresh_token is None:
            raise PlatformRefused("no refresh token")
        secret = (
            settings.google_client_secret.get_secret_value()
            if settings.google_client_secret
            else ""
        )
        body = self._http.post_once(
            GOOGLE_TOKEN,
            {
                "client_id": settings.google_client_id or "",
                "client_secret": secret,
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
            },
        )
        return Tokens(
            access_token=_text(body, "access_token"),
            refresh_token=tokens.refresh_token,
            expires_at=_expires(now, body),
        )

    def revoke(self, tokens: Tokens) -> None:
        token = tokens.refresh_token or tokens.access_token
        try:
            self._http.post_once(GOOGLE_REVOKE, {"token": token})
        except PlatformRefused, PlatformUnavailable:
            # Already revoked, or Google is down: our copy goes regardless.
            logger.info("platform.revoke_not_confirmed platform=youtube")


@dataclass
class FakePlatformClient:
    """Answers set by a test; nothing leaves the process."""

    platform: str
    uses_pkce: bool = False
    # code -> the profile a sign-in with it reaches
    profiles: dict[str, PlatformProfile] = field(default_factory=dict)
    exchanged: list[tuple[str, str | None]] = field(default_factory=list)
    revoked: list[str] = field(default_factory=list)
    refreshed: list[str] = field(default_factory=list)
    unavailable: bool = False
    # Access the creator removed at the platform: refreshing and reading refuse.
    refused: bool = False

    def authorize_url(
        self, *, redirect_uri: str, state: str, code_challenge: str | None
    ) -> str:
        query = {"redirect_uri": redirect_uri, "state": state}
        if code_challenge is not None:
            query["code_challenge"] = code_challenge
        return f"https://{self.platform}.example/authorize?{urlencode(query)}"

    def exchange(
        self, *, code: str, redirect_uri: str, code_verifier: str | None, now: datetime
    ) -> Tokens:
        if self.unavailable:
            raise PlatformUnavailable("fake")
        if code not in self.profiles:
            raise PlatformRefused("unknown code")
        self.exchanged.append((code, code_verifier))
        return Tokens(
            access_token=f"access-for-{code}",
            refresh_token=f"refresh-for-{code}" if self.uses_pkce else None,
            expires_at=now + timedelta(days=60),
        )

    def profile(self, tokens: Tokens) -> PlatformProfile:
        if self.unavailable:
            raise PlatformUnavailable("fake")
        if self.refused:
            raise PlatformRefused("access removed")
        code = tokens.access_token.removeprefix("access-for-")
        return self.profiles[code]

    def refresh(self, tokens: Tokens, now: datetime) -> Tokens:
        if self.unavailable:
            raise PlatformUnavailable("fake")
        if self.refused:
            raise PlatformRefused("access removed")
        self.refreshed.append(tokens.access_token)
        return Tokens(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_at=now + timedelta(days=60),
        )

    def revoke(self, tokens: Tokens) -> None:
        self.revoked.append(tokens.access_token)


_clients: dict[str, PlatformClient] = {}


def get_platform_client(platform: str) -> PlatformClient:
    """The client for a platform: the real one, made once."""
    if platform not in _clients:
        _clients[platform] = (
            InstagramClient() if platform == "instagram" else YouTubeClient()
        )
    return _clients[platform]
