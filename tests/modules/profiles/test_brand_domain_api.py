"""A brand proves it controls its website's domain, and creators see it (item 74, D-106).

The checking job runs here through `brand_domain_service.run_checks` on the
test's session, with a fake lookup standing in for the resolvers and the
registry, so every answer is exactly the one the test sets.
"""

import uuid
from contextlib import nullcontext
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.clock import india_date
from app.core.rate_limit import limiter
from app.modules.auth.models.brand import Brand
from app.modules.profiles import brand_domain_service as service
from app.modules.profiles import brand_domains as rules
from app.modules.profiles.brand_domain_models import BrandDomain
from app.modules.profiles.brand_domains import ResolverAnswer
from app.modules.profiles.domain_lookup import FakeDomainLookup
from tests.deal_flow import Clock, User, brand_user, creator_user
from tests.factories import build_campaign
from tests.query_counts import queries_for
from tests.step_up import download_export

DOMAIN = "/api/v1/brands/me/domain"
CHECK = f"{DOMAIN}/check"
DISCOVER = "/api/v1/campaigns/discover"


def a_domain() -> str:
    return f"shop{uuid.uuid4().hex[:10]}.in"


@pytest.fixture
def lookup() -> FakeDomainLookup:
    return FakeDomainLookup()


@pytest.fixture
def brand(db, clock) -> User:
    user = brand_user(db, clock)
    db.commit()
    return user


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    db.commit()
    return user


def brand_id_of(db, user: User) -> uuid.UUID:
    return db.scalar(select(Brand.id).where(Brand.account_id == user.account_id))


def claim(client, user: User, domain: str):
    return client.post(DOMAIN, json={"domain": domain}, headers=user.headers)


def publish(lookup: FakeDomainLookup, body: dict) -> None:
    lookup.publish(body["record_name"], body["record_value"])


def run_job(db, lookup: FakeDomainLookup, clock: Clock) -> service.CheckRun:
    return service.run_checks(lambda: nullcontext(db), lookup, clock.now)


def verified(client, db, lookup, clock, user: User, domain: str | None = None) -> dict:
    """Claim, publish, check and run the job: a verified domain."""
    body = claim(client, user, domain or a_domain()).json()
    publish(lookup, body)
    assert client.post(CHECK, headers=user.headers).status_code == 202
    run_job(db, lookup, clock)
    found = client.get(DOMAIN, headers=user.headers).json()
    assert found["status"] == "verified", found
    return found


def mine(client, user: User) -> dict:
    return client.get(DOMAIN, headers=user.headers).json()


def attention(client, user: User) -> list[dict]:
    response = client.get("/api/v1/me/attention", headers=user.headers)
    assert response.status_code == 200, response.text
    return [
        i
        for i in response.json()["items"]
        if i["kind"].startswith(("fix_domain", "domain_"))
    ]


def open_campaign(db, user: User, city: str = "Madurai") -> uuid.UUID:
    campaign = build_campaign(
        db, status="open", brand_id=brand_id_of(db, user), cities=[city]
    )
    db.add(campaign)
    db.commit()
    return campaign.id


# --- claiming -----------------------------------------------------------------------------


def test_a_brand_claims_its_domain_and_is_told_what_to_publish(client, brand, clock):
    response = claim(client, brand, "SmallShop.in")

    assert response.status_code == 201, response.text
    assert response.headers["location"] == DOMAIN
    body = response.json()
    assert body["domain"] == "smallshop.in"
    assert body["status"] == "pending"
    assert body["record_type"] == "TXT"
    assert body["record_name"] == "_nicheconnect-challenge.smallshop.in"
    assert body["record_value"].startswith("nicheconnect-domain-verification=")
    assert body["token_expires_at"] == (
        clock.now + timedelta(days=7)
    ).isoformat().replace("+00:00", "Z")
    assert body["check_waiting"] is False
    assert body["last_result"] is None


def test_a_leading_www_is_dropped(client, brand):
    assert (
        claim(client, brand, "www.smallshop.co.in").json()["domain"] == "smallshop.co.in"
    )


@pytest.mark.parametrize(
    ("typed", "says"),
    [
        ("co.in", "a suffix many sites share"),
        ("shop.smallshop.in", "smallshop.in"),
        ("xn--nyka-x2a.com", "other scripts"),
        ("https://smallshop.in", "letters a to z"),
    ],
)
def test_a_domain_that_cannot_be_claimed_says_why(client, brand, typed, says):
    response = claim(client, brand, typed)

    assert response.status_code == 422
    assert response.json()["code"] == "domain_not_accepted"
    assert says in response.json()["detail"]


def test_a_domain_another_brand_verified_cannot_be_claimed(
    client, db, lookup, clock, brand
):
    held = verified(client, db, lookup, clock, brand)["domain"]
    other = brand_user(db, clock)
    db.commit()

    response = claim(client, other, held)

    assert response.status_code == 409
    assert response.json()["code"] == "domain_held_elsewhere"


def test_claiming_again_replaces_the_claim_with_a_new_token(
    client, db, lookup, clock, brand
):
    first = verified(client, db, lookup, clock, brand)

    again = claim(client, brand, first["domain"]).json()

    assert again["status"] == "pending"
    assert again["record_value"] != first["record_value"]
    assert again["verified_at"] is None


def test_only_a_brand_has_a_domain(client, creator):
    assert claim(client, creator, "smallshop.in").status_code == 403
    assert client.get(DOMAIN, headers=creator.headers).status_code == 403


def test_it_needs_a_login(client):
    assert client.post(DOMAIN, json={"domain": "smallshop.in"}).status_code == 401
    assert client.get(DOMAIN).status_code == 401


def test_nothing_claimed_is_not_found(client, brand):
    response = client.get(DOMAIN, headers=brand.headers)

    assert response.status_code == 404
    assert response.json()["code"] == "domain_claim_not_found"
    assert client.post(CHECK, headers=brand.headers).status_code == 404
    assert client.delete(DOMAIN, headers=brand.headers).status_code == 404


@pytest.mark.parametrize(
    "body",
    [{}, {"domain": ""}, {"domain": "x" * 261}, {"domain": "a.in", "status": "verified"}],
)
def test_a_malformed_claim_is_refused(client, brand, body):
    assert client.post(DOMAIN, json=body, headers=brand.headers).status_code == 422


# --- checking -----------------------------------------------------------------------------


def test_a_check_is_accepted_at_once_and_the_job_verifies_the_domain(
    client, db, lookup, clock, brand
):
    body = claim(client, brand, a_domain()).json()
    publish(lookup, body)
    lookup.dates[body["domain"]] = date(2019, 3, 14)

    accepted = client.post(CHECK, headers=brand.headers)
    run = run_job(db, lookup, clock)

    assert accepted.status_code == 202
    assert accepted.json()["check_waiting"] is True
    assert run == service.CheckRun(checked=1, verified=1, lapsed=0)
    found = mine(client, brand)
    assert found["status"] == "verified"
    assert found["last_result"] == "found"
    assert found["check_waiting"] is False
    assert found["dnssec_validated"] is True
    assert found["registered_on"] == "2019-03-14"
    assert lookup.asked == [body["record_name"]]


def test_without_the_record_the_claim_stays_pending_and_the_brand_is_told(
    client, db, lookup, clock, brand
):
    body = claim(client, brand, a_domain()).json()
    client.post(CHECK, headers=brand.headers)

    run_job(db, lookup, clock)

    assert mine(client, brand)["status"] == "pending"
    assert mine(client, brand)["last_result"] == "absent"
    (item,) = attention(client, brand)
    assert item["kind"] == "fix_domain_record"
    assert item["domain"] == body["domain"]
    assert item["due_on"] == india_date(clock.now + timedelta(days=7)).isoformat()
    assert item["campaign_id"] is None


def test_one_resolver_alone_never_verifies(client, db, lookup, clock, brand):
    body = claim(client, brand, a_domain()).json()
    lookup.records[body["record_name"]] = [
        ResolverAnswer(values=(body["record_value"],)),
        ResolverAnswer(values=()),
    ]
    client.post(CHECK, headers=brand.headers)

    run_job(db, lookup, clock)

    assert mine(client, brand)["status"] == "pending"


def test_asking_twice_before_the_job_runs_checks_once(client, db, lookup, clock, brand):
    claim(client, brand, a_domain())
    client.post(CHECK, headers=brand.headers)
    client.post(CHECK, headers=brand.headers)

    assert run_job(db, lookup, clock).checked == 1
    assert run_job(db, lookup, clock).checked == 0


def test_an_expired_token_cannot_be_checked(client, db, clock, brand):
    claim(client, brand, a_domain())
    clock.advance(timedelta(days=7))

    response = client.post(CHECK, headers=brand.headers)

    assert response.status_code == 409
    assert response.json()["code"] == "domain_claim_expired"
    assert [i["kind"] for i in attention(client, brand)] == ["domain_claim_expired"]


def test_a_check_asked_just_before_the_token_expired_is_dropped(
    client, db, lookup, clock, brand
):
    body = claim(client, brand, a_domain()).json()
    publish(lookup, body)
    clock.advance(timedelta(days=7) - timedelta(seconds=1))
    client.post(CHECK, headers=brand.headers)
    clock.advance(timedelta(seconds=1))

    assert run_job(db, lookup, clock).checked == 0
    assert mine(client, brand)["status"] == "pending"
    assert lookup.asked == []


def test_checks_are_limited_per_brand(client, brand):
    claim(client, brand, a_domain())

    answers = [client.post(CHECK, headers=brand.headers).status_code for _ in range(6)]

    assert answers[:5] == [202] * 5
    assert answers[5] == 429


# --- staying verified -----------------------------------------------------------------------


def test_a_verified_domain_is_checked_again_after_a_day_not_before(
    client, db, lookup, clock, brand
):
    verified(client, db, lookup, clock, brand)
    lookup.asked.clear()

    clock.advance(timedelta(hours=23, minutes=59))
    assert run_job(db, lookup, clock).checked == 0
    clock.advance(timedelta(minutes=1))
    assert run_job(db, lookup, clock).checked == 1
    assert len(lookup.asked) == 1


def test_three_daily_checks_without_the_record_lapse_it(client, db, lookup, clock, brand):
    found = verified(client, db, lookup, clock, brand)
    campaign = open_campaign(db, brand)
    lookup.records.clear()

    for day in range(1, 4):
        clock.advance(timedelta(days=1))
        run = run_job(db, lookup, clock)
        state = mine(client, brand)
        if day < 3:
            assert (state["status"], state["consecutive_absent"]) == ("verified", day)
            (item,) = attention(client, brand)
            assert item["kind"] == "fix_domain_record"
            # Due the day it would lapse.
            due = india_date(clock.now + timedelta(days=3 - day))
            assert item["due_on"] == due.isoformat()

    assert run.lapsed == 1
    assert state["status"] == "lapsed"
    assert state["verified_at"] == found["verified_at"]
    assert [i["kind"] for i in attention(client, brand)] == ["domain_lapsed"]
    seen = client.get(f"/api/v1/campaigns/{campaign}", headers=brand.headers).json()
    assert seen["verified_domain"] is None
    lapsed_check = client.post(CHECK, headers=brand.headers)
    assert lapsed_check.status_code == 409
    assert lapsed_check.json()["code"] == "domain_claim_lapsed"


def test_a_lapsed_domain_is_not_revived_by_its_old_record(
    client, db, lookup, clock, brand
):
    body = verified(client, db, lookup, clock, brand)
    lookup.records.clear()
    for _ in range(3):
        clock.advance(timedelta(days=1))
        run_job(db, lookup, clock)
    publish(lookup, body)

    clock.advance(timedelta(days=1))
    run_job(db, lookup, clock)

    assert mine(client, brand)["status"] == "lapsed"


def test_an_outage_never_counts_against_a_verified_domain(
    client, db, lookup, clock, brand
):
    body = verified(client, db, lookup, clock, brand)
    lookup.records[body["record_name"]] = [ResolverAnswer(values=None)] * 2

    for _ in range(5):
        clock.advance(timedelta(days=1))
        run_job(db, lookup, clock)

    state = mine(client, brand)
    assert (state["status"], state["consecutive_absent"]) == ("verified", 0)
    assert state["last_result"] == "unknown"


def test_the_record_coming_back_resets_the_count(client, db, lookup, clock, brand):
    body = verified(client, db, lookup, clock, brand)
    lookup.records.clear()
    clock.advance(timedelta(days=1))
    run_job(db, lookup, clock)
    publish(lookup, body)

    clock.advance(timedelta(days=1))
    run_job(db, lookup, clock)

    assert mine(client, brand)["consecutive_absent"] == 0
    assert attention(client, brand) == []


def test_a_second_brand_proving_a_held_domain_stays_pending(
    client, db, lookup, clock, brand
):
    domain = a_domain()
    other = brand_user(db, clock)
    db.commit()
    theirs = claim(client, other, domain).json()
    verified(client, db, lookup, clock, brand, domain)
    publish(lookup, theirs)

    client.post(CHECK, headers=other.headers)
    run_job(db, lookup, clock)

    state = mine(client, other)
    assert (state["status"], state["last_result"]) == ("pending", "taken")
    assert [i["kind"] for i in attention(client, other)] == ["fix_domain_record"]


def test_a_result_for_a_token_since_replaced_is_dropped(client, db, lookup, clock, brand):
    """A brand that claims again while a check runs keeps its new claim untouched."""
    body = claim(client, brand, a_domain()).json()
    publish(lookup, body)
    client.post(CHECK, headers=brand.headers)
    (due,) = service.take_due(db, clock.now)
    claim(client, brand, body["domain"])

    applied = service.apply_check(
        db, due, rules.CheckOutcome("found", True), None, clock.now
    )

    assert applied is None
    assert mine(client, brand)["status"] == "pending"


def test_a_check_taken_by_a_run_is_not_taken_again_until_its_lease_runs_out(
    client, db, clock, brand
):
    claim(client, brand, a_domain())
    client.post(CHECK, headers=brand.headers)

    assert len(service.take_due(db, clock.now)) == 1
    assert service.take_due(db, clock.now + timedelta(minutes=4)) == []
    assert (
        len(service.take_due(db, clock.now + service.LEASE + timedelta(seconds=1))) == 1
    )


def test_withdrawing_takes_the_domain_off_at_once(
    client, db, lookup, clock, brand, creator
):
    verified(client, db, lookup, clock, brand)
    campaign = open_campaign(db, brand)

    assert client.delete(DOMAIN, headers=brand.headers).status_code == 204

    seen = client.get(f"/api/v1/campaigns/{campaign}", headers=creator.headers).json()
    assert seen["verified_domain"] is None
    assert client.get(DOMAIN, headers=brand.headers).status_code == 404


# --- what creators see --------------------------------------------------------------------


def test_creators_see_the_domain_on_the_brand_s_campaigns_and_payment_record(
    client, db, lookup, clock, brand, creator
):
    domain = a_domain()
    lookup.dates[domain] = date(2026, 10, 10)
    found = verified(client, db, lookup, clock, brand, domain)
    campaign = open_campaign(db, brand)
    expected = {
        "domain": domain,
        "verified_since": found["verified_at"],
        "last_checked_at": found["last_checked_at"],
        "registered_on": "2026-10-10",
        "dnssec_validated": True,
    }

    one = client.get(f"/api/v1/campaigns/{campaign}", headers=creator.headers).json()
    listed = client.get(DISCOVER, headers=creator.headers).json()["items"]
    record = client.get(
        f"/api/v1/brands/{brand_id_of(db, brand)}/reliability", headers=creator.headers
    ).json()

    assert one["verified_domain"] == expected
    assert [c["verified_domain"] for c in listed if c["id"] == str(campaign)] == [
        expected
    ]
    assert record["verified_domain"] == expected
    # Never the token, nor anything only the brand should see.
    assert "record_value" not in str(one) and "token" not in one["verified_domain"]


def test_a_pending_claim_shows_creators_nothing(client, db, brand, creator):
    claim(client, brand, a_domain())
    campaign = open_campaign(db, brand)

    seen = client.get(f"/api/v1/campaigns/{campaign}", headers=creator.headers).json()

    assert seen["verified_domain"] is None


def test_discovery_costs_the_same_queries_however_many_brands_are_verified(
    client, db, lookup, clock, creator
):
    """In a city of the test's own, so other campaigns cannot fill the page."""
    city = f"Town{uuid.uuid4().hex[:8]}"
    url = f"{DISCOVER}?city={city}"

    def verified_brand_with_a_campaign() -> None:
        user = brand_user(db, clock)
        db.commit()
        verified(client, db, lookup, clock, user)
        open_campaign(db, user, city)

    for _ in range(2):
        verified_brand_with_a_campaign()
    limiter.reset()
    listed = client.get(url, headers=creator.headers).json()["items"]
    assert len(listed) == 2 and all(c["verified_domain"] for c in listed)
    with_two = queries_for(client, url, creator.headers)
    for _ in range(4):
        verified_brand_with_a_campaign()
    limiter.reset()
    with_six = queries_for(client, url, creator.headers)

    assert with_two == with_six


def test_the_brand_s_export_holds_the_claim_but_never_the_token(
    client, db, lookup, clock, brand
):
    found = verified(client, db, lookup, clock, brand)

    response = download_export(client, brand.headers)

    assert response.status_code == 200, response.text
    (row,) = response.json()["data"]["website_domain"]
    assert row["domain"] == found["domain"]
    assert row["status"] == "verified"
    assert not any("token" in key for key in row)
    assert found["record_value"].split("=")[1] not in str(row)
    db.expire_all()
    assert db.scalars(select(BrandDomain)).first() is not None
