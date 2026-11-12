"""Every outside HTTP client, against a server misbehaving on purpose (item 118, D-186).

Each real client, with its real transport, meets a real socket
(`tests/misbehaving_server.py`) that never answers, trickles its headers,
or trickles its body a byte at a time, each byte inside the read timeout.
Every call must end at its whole limit (made 1 s here), measured with the
clock, and fail the way its callers already handle. A server that fails once
then answers must still be answered. This is testing.md section 0's "failure
on purpose" for WhatsApp (MSG91), the timestamp authorities, the DNS and RDAP
lookups and Instagram and YouTube; S3 is in tests/core/test_storage.py and
the Claude API in tests/core/test_claude_calls.py.

Then each client's own loop, with a fake clock: once the limit has passed
it neither waits nor tries again, and no wait runs past the limit.
"""

import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import httpx2
import pytest

from app.core.config import settings
from app.modules.auth import msg91_sender
from app.modules.auth.msg91_sender import Msg91WhatsAppSender, OtpDeliveryFailed
from app.modules.deal_memo import timestamp_authority
from app.modules.deal_memo.timestamp_authority import Rfc3161Authority, TimestampFailed
from app.modules.profiles import domain_lookup, platform_clients
from app.modules.profiles.domain_lookup import HttpsDomainLookup
from app.modules.profiles.platform_clients import PlatformUnavailable, _Http
from tests.misbehaving_server import misbehaving, timed

LIMIT = 1.0
# How far past its limit a call may end: the time to notice, never a wait.
SLACK = 0.5
FAILED = object()


@dataclass(frozen=True)
class Client:
    """One outside client: how to make one call, and what a failed call looks like."""

    module: ModuleType
    call: Callable[[str, Callable[[float], None]], Any]
    failed: Callable[[object], bool]
    answered: Callable[[object], bool]
    body: bytes = b'{"ok": true}'


def msg91(url: str, sleep: Callable[[float], None]) -> Any:
    msg91_sender.API_URL = url  # restored by the fixture below
    sender = Msg91WhatsAppSender(
        auth_key="test-auth-key-not-real",
        integrated_number="919000000001",
        template="login_code",
        language="en",
        sleep=sleep,
        jitter=lambda: 0.5,
    )
    return sender.send_code("+919876543210", "482915")


def authority(url: str, sleep: Callable[[float], None]) -> Any:
    return Rfc3161Authority("test-tsa", url, sleep=sleep, jitter=lambda: 0.5)._post(b"q")


def lookup(url: str, sleep: Callable[[float], None]) -> Any:
    return HttpsDomainLookup(sleep=sleep, jitter=lambda: 0.5)._get_json(url)


def platform_read(url: str, sleep: Callable[[float], None]) -> Any:
    return _Http(sleep=sleep, jitter=lambda: 0.5).get(url, params={}, headers={})


def platform_exchange(url: str, sleep: Callable[[float], None]) -> Any:
    return _Http(sleep=sleep, jitter=lambda: 0.5).post_once(url, {"code": "c"})


CLIENTS = {
    "msg91": Client(
        msg91_sender,
        msg91,
        failed=lambda o: isinstance(o, OtpDeliveryFailed),
        answered=lambda o: o is None,
        body=b'{"status": "success", "hasError": false}',
    ),
    "timestamp_authority": Client(
        timestamp_authority,
        authority,
        failed=lambda o: isinstance(o, TimestampFailed),
        answered=lambda o: o == b"token",
        body=b"token",
    ),
    "domain_lookup": Client(
        domain_lookup,
        lookup,
        # It never raises: an unreachable resolver is "not known" (None).
        failed=lambda o: o is None,
        answered=lambda o: o == {"ok": True},
    ),
    "platform_read": Client(
        platform_clients,
        platform_read,
        failed=lambda o: isinstance(o, PlatformUnavailable),
        answered=lambda o: o == {"ok": True},
    ),
    "platform_exchange": Client(
        platform_clients,
        platform_exchange,
        failed=lambda o: isinstance(o, PlatformUnavailable),
        answered=lambda o: o == {"ok": True},
    ),
}


@pytest.fixture(autouse=True)
def one_second_limits(monkeypatch):
    for client in CLIENTS.values():
        monkeypatch.setattr(client.module, "CALL_LIMIT_SECONDS", LIMIT)
    monkeypatch.setattr(msg91_sender, "API_URL", msg91_sender.API_URL)
    monkeypatch.setattr(settings, "meta_app_id", "123456789")


def test_every_client_with_a_call_limit_is_tested_here():
    """A client given a limit later must join this file, or this fails."""
    app = pathlib.Path(__file__).resolve().parents[2] / "app"
    limited = {
        str(path.relative_to(app.parent)).replace("\\", "/")
        for path in app.rglob("*.py")
        if re.search(r"^CALL_LIMIT_SECONDS = ", path.read_text(encoding="utf-8"), re.M)
    }
    tested_here = {
        f"app/{client.module.__name__.removeprefix('app.').replace('.', '/')}.py"
        for client in CLIENTS.values()
    }
    tested_elsewhere = {"app/core/claude_calls.py", "app/core/storage.py"}

    assert len(limited) == 6
    assert limited == tested_here | tested_elsewhere


@pytest.mark.parametrize("behaviour", ["silent", "trickle_headers", "trickle_body"])
@pytest.mark.parametrize("name", sorted(CLIENTS))
def test_a_server_that_holds_the_call_is_cut_off_at_the_limit(name, behaviour):
    client = CLIENTS[name]
    with misbehaving(behaviour, body=client.body) as server:
        outcome, elapsed = timed(lambda: client.call(server.url, lambda _: None))

    assert client.failed(outcome), outcome
    assert len(server.requests) == 1  # no time left for another try
    assert LIMIT - 0.05 <= elapsed < LIMIT + SLACK


@pytest.mark.parametrize("name", sorted(set(CLIENTS) - {"platform_exchange"}))
def test_a_server_that_fails_once_then_answers_is_answered(name):
    client = CLIENTS[name]
    with misbehaving(
        "flaky", body=client.body, content_type="application/json"
    ) as server:
        outcome, elapsed = timed(lambda: client.call(server.url, lambda _: None))

    assert client.answered(outcome), outcome
    assert len(server.requests) == 2
    assert elapsed < LIMIT


def test_a_single_use_code_is_never_sent_twice_even_when_the_first_fails():
    with misbehaving("flaky", body=b'{"ok": true}') as server:
        outcome, _ = timed(lambda: platform_exchange(server.url, lambda _: None))

    assert isinstance(outcome, PlatformUnavailable)
    assert len(server.requests) == 1


# --- each client's loop, with a fake clock --------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def failing_transport(clock: Clock, takes: float) -> httpx2.Client:
    """Answers 503 to everything, each answer taking `takes` seconds of `clock`."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        clock.now += takes
        return httpx2.Response(503)

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def loops(clock: Clock, client: httpx2.Client, sleeps: list[float]):
    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.now += seconds

    common = {"client": client, "sleep": sleep, "jitter": lambda: 0.5, "clock": clock}
    return {
        "msg91": lambda: Msg91WhatsAppSender(
            auth_key="k",
            integrated_number="919000000001",
            template="login_code",
            language="en",
            **common,
        ).send_code("+919876543210", "482915"),
        "timestamp_authority": lambda: Rfc3161Authority(
            "test-tsa", "https://tsa.test/", **common
        )._post(b"q"),
        "domain_lookup": lambda: HttpsDomainLookup(**common)._get_json(
            "https://dns.test/"
        ),
        "platform_read": lambda: _Http(**common).get(
            "https://graph.test/", params={}, headers={}
        ),
    }


LOOPED = ["msg91", "timestamp_authority", "domain_lookup", "platform_read"]


@pytest.mark.parametrize("name", LOOPED)
def test_once_the_limit_has_passed_there_is_no_wait_and_no_other_try(name, monkeypatch):
    """The first try takes the whole limit: give up at once, not after a wait."""
    clock, sleeps = Clock(), []
    monkeypatch.setattr(CLIENTS[name].module, "CALL_LIMIT_SECONDS", 15.0)
    client = failing_transport(clock, takes=15.0)
    sent: list[int] = []
    client.event_hooks["request"].append(lambda request: sent.append(1))

    outcome, _ = timed(loops(clock, client, sleeps)[name])

    assert CLIENTS[name].failed(outcome), outcome
    assert sent == [1]
    assert sleeps == []


@pytest.mark.parametrize("name", LOOPED)
def test_no_wait_between_tries_runs_past_the_limit(name, monkeypatch):
    """14.8 s spent on the first try, a 0.5 s wait due: it is cut to the 0.2 s left."""
    clock, sleeps = Clock(), []
    monkeypatch.setattr(CLIENTS[name].module, "CALL_LIMIT_SECONDS", 15.0)

    outcome, _ = timed(loops(clock, failing_transport(clock, takes=14.8), sleeps)[name])

    assert CLIENTS[name].failed(outcome), outcome
    assert sleeps == [pytest.approx(0.2)]


@pytest.mark.parametrize("name", LOOPED)
def test_with_time_to_spare_the_waits_are_the_usual_ones(name, monkeypatch):
    clock, sleeps = Clock(), []
    monkeypatch.setattr(CLIENTS[name].module, "CALL_LIMIT_SECONDS", 15.0)

    outcome, _ = timed(loops(clock, failing_transport(clock, takes=0.1), sleeps)[name])

    assert CLIENTS[name].failed(outcome), outcome
    assert sleeps == [0.5, 1.0]  # 0.5 s then 1 s, at the middle of the jitter
