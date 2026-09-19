"""Who the rate limiter thinks is calling, behind a proxy and without one."""

import pytest
from starlette.requests import Request

from app.core import client_ip as client_ip_module
from app.core.client_ip import client_ip, trusted_networks
from app.core.config import settings


def make_request(socket_address: str | None, forwarded: str | None = None) -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (socket_address, 12345) if socket_address else None,
    }
    return Request(scope)


@pytest.fixture
def trust(monkeypatch):
    """Configure TRUSTED_PROXIES for one test."""

    def set_trusted(raw: str) -> None:
        monkeypatch.setattr(settings, "trusted_proxies", raw)
        client_ip_module._parse_networks.cache_clear()

    yield set_trusted
    client_ip_module._parse_networks.cache_clear()


# --- no proxy configured (the default) ------------------------------------


def test_nothing_is_trusted_by_default(trust):
    trust("")

    assert trusted_networks() == ()


def test_the_socket_address_is_used_when_no_proxy_is_configured(trust):
    trust("")

    assert client_ip(make_request("203.0.113.9")) == "203.0.113.9"


def test_a_forged_header_is_ignored_without_a_trusted_proxy(trust):
    trust("")

    # An attacker sending this must not get someone else's rate-limit bucket.
    assert client_ip(make_request("203.0.113.9", "1.2.3.4")) == "203.0.113.9"


# --- behind a trusted proxy ----------------------------------------------


def test_the_client_behind_a_trusted_proxy_is_used(trust):
    trust("10.0.0.0/8")

    assert client_ip(make_request("10.1.2.3", "203.0.113.9")) == "203.0.113.9"


def test_a_single_address_can_be_trusted(trust):
    trust("10.1.2.3")

    assert client_ip(make_request("10.1.2.3", "203.0.113.9")) == "203.0.113.9"


def test_several_entries_can_be_trusted(trust):
    trust("10.0.0.0/8, 172.16.0.0/12")

    assert client_ip(make_request("172.16.5.5", "203.0.113.9")) == "203.0.113.9"


def test_chained_proxies_give_the_client_not_the_other_proxy(trust):
    trust("10.0.0.0/8")

    # client -> proxy A (10.0.0.7) -> proxy B (10.0.0.8) -> us
    resolved = client_ip(make_request("10.0.0.8", "203.0.113.9, 10.0.0.7"))

    assert resolved == "203.0.113.9"


def test_a_client_forging_extra_hops_cannot_hide(trust):
    trust("10.0.0.0/8")

    # The caller prepends a fake address; the rightmost untrusted entry is
    # the one our proxy actually saw.
    resolved = client_ip(make_request("10.0.0.8", "9.9.9.9, 203.0.113.9"))

    assert resolved == "203.0.113.9"


def test_a_proxy_sending_no_header_falls_back_to_its_own_address(trust):
    trust("10.0.0.0/8")

    assert client_ip(make_request("10.0.0.8")) == "10.0.0.8"


def test_a_malformed_header_falls_back_to_the_socket_address(trust):
    trust("10.0.0.0/8")

    assert client_ip(make_request("10.0.0.8", "not-an-ip")) == "10.0.0.8"


def test_all_hops_trusted_falls_back_to_the_socket_address(trust):
    trust("10.0.0.0/8")

    assert client_ip(make_request("10.0.0.8", "10.0.0.7, 10.0.0.6")) == "10.0.0.8"


def test_ipv6_works_too(trust):
    trust("fd00::/8")

    assert client_ip(make_request("fd00::1", "2001:db8::42")) == "2001:db8::42"


# --- odd cases ------------------------------------------------------------


def test_unparseable_settings_are_ignored(trust):
    trust("not-a-network, 10.0.0.0/8, , 999.999.999.999")

    assert len(trusted_networks()) == 1
    assert client_ip(make_request("10.0.0.8", "203.0.113.9")) == "203.0.113.9"


def test_a_request_without_a_client_address_is_still_answered(trust):
    trust("10.0.0.0/8")

    assert client_ip(make_request(None)) == "unknown"


def test_the_test_client_address_is_not_trusted(trust):
    """Starlette's test client uses the name "testclient", not an address."""
    trust("10.0.0.0/8")

    assert client_ip(make_request("testclient", "1.2.3.4")) == "testclient"
