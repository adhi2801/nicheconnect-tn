"""The real Instagram and YouTube clients, against recorded shapes (item 29, D-134).

These prove what we send and how we read the answer, as Meta's and Google's
references describe them (read 26 October 2026). They cannot prove the live
platforms answer that way: that waits on the approved apps.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.modules.profiles.platform_clients import (
    InstagramClient,
    PlatformRefused,
    PlatformUnavailable,
    Tokens,
    YouTubeClient,
    _Http,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)
REDIRECT = "https://app.nicheconnect.test/connect/instagram"


@pytest.fixture(autouse=True)
def apps(monkeypatch) -> None:
    monkeypatch.setattr(settings, "meta_app_id", "123456789")
    monkeypatch.setattr(settings, "meta_app_secret", SecretStr("meta-secret"))
    monkeypatch.setattr(settings, "google_client_id", "c.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", SecretStr("google-secret"))


class Recorder:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, body = answer
        return httpx2.Response(status, json=body)


def http(recorder: Recorder) -> _Http:
    return _Http(
        client=httpx2.Client(transport=httpx2.MockTransport(recorder)),
        sleep=lambda _: None,
        jitter=lambda: 0.0,
    )


def form_of(request: httpx2.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


# --- Instagram ---------------------------------------------------------------------


def test_instagram_asks_for_the_least_access():
    url = InstagramClient(http(Recorder([]))).authorize_url(
        redirect_uri=REDIRECT, state="the-state", code_challenge=None
    )
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}

    assert url.startswith("https://www.instagram.com/oauth/authorize?")
    assert query == {
        "client_id": "123456789",
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": "instagram_business_basic",
        "state": "the-state",
    }


def test_instagram_trades_the_code_for_a_sixty_day_token():
    recorder = Recorder(
        [
            (200, {"access_token": "short", "user_id": 1}),
            (
                200,
                {"access_token": "long", "token_type": "bearer", "expires_in": 5_184_000},
            ),
        ]
    )

    tokens = InstagramClient(http(recorder)).exchange(
        code="the-code", redirect_uri=REDIRECT, code_verifier=None, now=NOW
    )

    first, second = recorder.requests
    assert str(first.url) == "https://api.instagram.com/oauth/access_token"
    assert form_of(first) == {
        "client_id": "123456789",
        "client_secret": "meta-secret",
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT,
        "code": "the-code",
    }
    assert second.url.params["grant_type"] == "ig_exchange_token"
    assert second.url.params["access_token"] == "short"
    assert tokens == Tokens(
        access_token="long", refresh_token=None, expires_at=NOW + timedelta(days=60)
    )


def test_instagram_reads_the_handle_and_followers():
    recorder = Recorder(
        [(200, {"user_id": "1784", "username": "priya.eats", "followers_count": 24000})]
    )

    found = InstagramClient(http(recorder)).profile(Tokens("tok", None, None))

    (request,) = recorder.requests
    assert request.headers["Authorization"] == "Bearer tok"
    assert "tok" not in str(request.url)  # in the header, never the URL a log could hold
    assert (found.platform_user_id, found.handle, found.followers) == (
        "1784",
        "priya.eats",
        24000,
    )


def test_a_refused_code_is_never_retried():
    recorder = Recorder([(400, {"error_message": "code used"})])

    with pytest.raises(PlatformRefused):
        InstagramClient(http(recorder)).exchange(
            code="x", redirect_uri=REDIRECT, code_verifier=None, now=NOW
        )
    assert len(recorder.requests) == 1


def test_a_failed_exchange_is_never_retried():
    recorder = Recorder([(503, {})])

    with pytest.raises(PlatformUnavailable):
        InstagramClient(http(recorder)).exchange(
            code="x", redirect_uri=REDIRECT, code_verifier=None, now=NOW
        )
    assert len(recorder.requests) == 1  # a code works once: asking again could spend it


def test_a_read_retries_then_gives_up():
    recorder = Recorder([(503, {}), httpx2.ConnectError("down"), (502, {})])

    with pytest.raises(PlatformUnavailable):
        InstagramClient(http(recorder)).profile(Tokens("tok", None, None))
    assert len(recorder.requests) == 3


def test_a_read_that_recovers_is_used():
    recorder = Recorder(
        [(503, {}), (200, {"user_id": "1", "username": "a", "followers_count": 5})]
    )

    assert (
        InstagramClient(http(recorder)).profile(Tokens("tok", None, None)).followers == 5
    )


# --- YouTube -----------------------------------------------------------------------


def test_youtube_asks_for_read_only_access_with_pkce():
    url = YouTubeClient(http(Recorder([]))).authorize_url(
        redirect_uri=REDIRECT, state="s", code_challenge="the-challenge"
    )
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["scope"] == "https://www.googleapis.com/auth/youtube.readonly"
    assert (query["code_challenge"], query["code_challenge_method"]) == (
        "the-challenge",
        "S256",
    )
    assert (query["access_type"], query["prompt"]) == ("offline", "consent")


def test_youtube_sends_the_verifier_and_keeps_the_refresh_token():
    recorder = Recorder(
        [(200, {"access_token": "a", "refresh_token": "r", "expires_in": 3599})]
    )

    tokens = YouTubeClient(http(recorder)).exchange(
        code="c", redirect_uri=REDIRECT, code_verifier="the-verifier", now=NOW
    )

    (request,) = recorder.requests
    assert form_of(request)["code_verifier"] == "the-verifier"
    assert tokens == Tokens("a", "r", NOW + timedelta(seconds=3599))


def test_youtube_reads_the_channel():
    recorder = Recorder(
        [
            (
                200,
                {
                    "items": [
                        {
                            "id": "UCabc",
                            "snippet": {"title": "Priya Eats", "customUrl": "@priyaeats"},
                            "statistics": {
                                "subscriberCount": "1200",
                                "hiddenSubscriberCount": False,
                            },
                        }
                    ]
                },
            )
        ]
    )

    found = YouTubeClient(http(recorder)).profile(Tokens("tok", "r", None))

    (request,) = recorder.requests
    assert request.url.params["mine"] == "true"
    assert (found.platform_user_id, found.handle, found.followers) == (
        "UCabc",
        "@priyaeats",
        1200,
    )


def test_a_hidden_subscriber_count_is_none_not_zero():
    recorder = Recorder(
        [
            (
                200,
                {
                    "items": [
                        {
                            "id": "UC1",
                            "snippet": {"title": "T"},
                            "statistics": {
                                "subscriberCount": "0",
                                "hiddenSubscriberCount": True,
                            },
                        }
                    ]
                },
            )
        ]
    )

    assert (
        YouTubeClient(http(recorder)).profile(Tokens("t", None, None)).followers is None
    )


def test_a_google_account_without_a_channel_is_refused():
    recorder = Recorder([(200, {"items": []})])

    with pytest.raises(PlatformRefused):
        YouTubeClient(http(recorder)).profile(Tokens("t", None, None))


def test_revoking_sends_the_refresh_token_and_never_raises():
    recorder = Recorder([(400, {"error": "invalid_token"})])

    YouTubeClient(http(recorder)).revoke(Tokens("a", "r", None))

    (request,) = recorder.requests
    assert form_of(request) == {"token": "r"}


def test_an_answer_that_is_not_json_is_unavailable():
    def handler(request):
        return httpx2.Response(200, content=b"<html>")

    client = YouTubeClient(
        _Http(
            client=httpx2.Client(transport=httpx2.MockTransport(handler)),
            sleep=lambda _: None,
        )
    )

    with pytest.raises(PlatformUnavailable):
        client.profile(Tokens("t", None, None))
