"""Asking resolvers and registries about a domain, with no network (item 74, D-106).

The real client runs against httpx2's mock transport, so every answer shape
both resolvers and the registries send is exercised exactly as it would be
parsed, and nothing leaves the process (testing.md section 5).
"""

from datetime import date

import httpx2
import pytest

from app.modules.profiles import domain_lookup as lookup
from app.modules.profiles.brand_domains import ResolverAnswer

NAME = "_nicheconnect-challenge.smallshop.in"
RECORD = "nicheconnect-domain-verification=mfrggzdfmztwq2lknnwg23tpoa"
BOOTSTRAP = {
    "services": [
        [["com", "net"], ["https://rdap.verisign.com/com/v1/"]],
        [["in"], ["https://rdap.nixiregistry.in/rdap"]],
    ]
}


def doh(status: int = 0, *records: str, ad: bool = True) -> dict:
    return {
        "Status": status,
        "AD": ad,
        "Answer": [{"name": NAME, "type": 16, "data": f'"{r}"'} for r in records],
    }


# --- reading the answers -----------------------------------------------------------------


def test_a_txt_answer_is_read_with_its_dnssec_flag():
    assert lookup.parse_doh_answer(doh(0, RECORD)) == ResolverAnswer(
        values=(RECORD,), authenticated=True
    )


def test_no_such_name_is_an_answer_with_nothing_in_it():
    assert lookup.parse_doh_answer(doh(3, ad=False)) == ResolverAnswer(values=())


@pytest.mark.parametrize("body", [{"Status": 2}, {"Status": 5}, {}, [], None, "x"])
def test_a_failure_to_answer_is_never_read_as_absent(body):
    """SERVFAIL or a body we cannot read must not count against a brand."""
    assert lookup.parse_doh_answer(body).values is None


def test_records_of_other_types_are_ignored():
    body = doh(0, RECORD)
    body["Answer"].append({"name": NAME, "type": 5, "data": "elsewhere.example."})

    assert lookup.parse_doh_answer(body).values == (RECORD,)


@pytest.mark.parametrize(
    ("data", "text"),
    [
        ('"abc"', "abc"),
        ('"nicheconnect-domain-verification=" "mfrggzdfmztwq2lknnwg23tpoa"', RECORD),
        ('"say \\"hi\\""', 'say "hi"'),
        ("unquoted", "unquoted"),
    ],
)
def test_a_txt_record_split_into_strings_is_joined(data, text):
    """RFC 7208's reading: a long TXT record arrives as several quoted strings."""
    assert lookup.txt_strings(data) == text


def test_the_registration_date_comes_from_the_registration_event():
    body = {
        "events": [
            {"eventAction": "last changed", "eventDate": "2026-09-01T00:00:00Z"},
            {"eventAction": "registration", "eventDate": "2019-03-14T07:30:00Z"},
        ]
    }

    assert lookup.registration_date(body) == date(2019, 3, 14)


@pytest.mark.parametrize(
    "body",
    [
        {"events": [{"eventAction": "expiration", "eventDate": "2027-01-01T00:00:00Z"}]},
        {"events": [{"eventAction": "registration", "eventDate": "not a date"}]},
        {},
        None,
    ],
)
def test_no_registration_date_is_none_never_a_guess(body):
    assert lookup.registration_date(body) is None


def test_the_registry_server_comes_from_iana_s_file():
    assert lookup.rdap_base_for(BOOTSTRAP, "smallshop.co.in") == (
        "https://rdap.nixiregistry.in/rdap/"
    )
    assert lookup.rdap_base_for(BOOTSTRAP, "chennai.com") == (
        "https://rdap.verisign.com/com/v1/"
    )
    assert lookup.rdap_base_for(BOOTSTRAP, "shop.zz") is None
    assert lookup.rdap_base_for(None, "shop.in") is None


# --- the real client, against a mock transport --------------------------------------------


def client_answering(handler) -> lookup.HttpsDomainLookup:
    sleeps: list[float] = []
    found = lookup.HttpsDomainLookup(
        client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        sleep=sleeps.append,
        jitter=lambda: 0.5,
    )
    found.sleeps = sleeps  # type: ignore[attr-defined]
    return found


def test_both_resolvers_are_asked_over_https_for_the_txt_record():
    asked: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request)
        return httpx2.Response(200, json=doh(0, RECORD))

    answers = client_answering(handler).txt(NAME)

    assert [r.url.host for r in asked] == ["cloudflare-dns.com", "dns.google"]
    assert all(r.url.scheme == "https" for r in asked)
    assert all(
        r.url.params["name"] == NAME and r.url.params["type"] == "TXT" for r in asked
    )
    assert all(r.headers["accept"] == "application/dns-json" for r in asked)
    assert answers == [ResolverAnswer(values=(RECORD,), authenticated=True)] * 2


def test_a_resolver_that_keeps_failing_is_retried_three_times_then_unknown():
    calls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.url.host)
        if request.url.host == "dns.google":
            return httpx2.Response(503)
        return httpx2.Response(200, json=doh(0, RECORD))

    found = client_answering(handler)
    answers = found.txt(NAME)

    assert calls.count("dns.google") == lookup.MAX_ATTEMPTS
    assert answers[1].values is None
    # Backoff with jitter between the attempts: 0.5 s, then 1 s.
    assert found.sleeps == [0.5, 1.0]  # type: ignore[attr-defined]


def test_a_dropped_connection_is_retried():
    attempts = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx2.ConnectError("refused")
        return httpx2.Response(200, json=doh(0, RECORD))

    answers = client_answering(handler).txt(NAME)

    assert answers[0].values == (RECORD,)


def test_a_request_the_server_refuses_is_not_repeated():
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(400)

    answers = client_answering(handler).txt(NAME)

    assert calls["n"] == 2  # once per resolver
    assert [a.values for a in answers] == [None, None]


def test_the_registration_date_is_read_through_iana_s_bootstrap_once():
    asked: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(str(request.url))
        if request.url.host == "data.iana.org":
            return httpx2.Response(200, json=BOOTSTRAP)
        return httpx2.Response(
            200,
            json={
                "events": [
                    {"eventAction": "registration", "eventDate": "2021-06-01T00:00:00Z"}
                ]
            },
        )

    found = client_answering(handler)

    assert found.registered_on("smallshop.in") == date(2021, 6, 1)
    assert asked[0] == lookup.RDAP_BOOTSTRAP
    assert asked[1] == "https://rdap.nixiregistry.in/rdap/domain/smallshop.in"
    assert asked.count(lookup.RDAP_BOOTSTRAP) == 1


def test_a_registry_that_does_not_know_the_domain_gives_none():
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "data.iana.org":
            return httpx2.Response(200, json=BOOTSTRAP)
        return httpx2.Response(404)

    assert client_answering(handler).registered_on("smallshop.in") is None


def test_the_fake_answers_absent_unless_told_otherwise():
    fake = lookup.FakeDomainLookup()
    fake.publish("_nicheconnect-challenge.a.in", RECORD)

    assert fake.txt("_nicheconnect-challenge.b.in") == [ResolverAnswer(values=())] * 2
    assert fake.txt("_nicheconnect-challenge.a.in")[0].values == (RECORD,)
