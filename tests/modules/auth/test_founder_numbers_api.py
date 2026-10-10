"""The founders' weekly numbers (item 63).

Every test builds its own rows in March 2024 and in a city of its own, so
rows from other tests or from local sample data can never change a count
(testing.md section 4: tests over aggregates use names of their own).
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.modules.auth.numbers_router import NUMBERS_LIMIT
from app.modules.campaigns.models import Application
from app.modules.deal_memo.models import DealMemo
from app.modules.payment_status.models import PaymentStatus
from tests.deal_flow import User, brand_user, creator_user
from tests.factories import build_brand, build_campaign, build_creator, create_account
from tests.query_counts import queries_for

URL = "/api/v1/admin/numbers"
END = date(2024, 3, 31)  # a month no other data lives in
PITCH = "I run a Madurai street-food page with 12,000 local followers."


def at(day: int, hour: int = 12) -> datetime:
    """A moment in March 2024 (UTC; Tamil Nadu is 5.5 hours ahead)."""
    return datetime(2024, 3, day, hour, tzinfo=UTC)


@pytest.fixture
def admin(db, clock) -> User:
    account = create_account(db, "admin")
    db.commit()  # survives a refused request's rollback, as in the admin tests
    return User(account.id, "admin", clock)


@pytest.fixture
def city() -> str:
    return f"Testpur {uuid.uuid4().hex[:8]}"


def numbers(client, admin: User, city: str, **params) -> dict:
    response = client.get(
        URL,
        params={"ending_on": END.isoformat(), "city": city, **params},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


class World:
    """Builds rows with the moments a test chooses."""

    def __init__(self, db, city: str) -> None:
        self.db = db
        self.city = city

    def brand(self, created: datetime | None = None):
        brand = build_brand(self.db, email=f"b-{uuid.uuid4().hex[:12]}@example.com")
        if created:
            brand.created_at = created
        self.db.add(brand)
        self.db.flush()
        return brand

    def creator(self, created: datetime | None = None):
        creator = build_creator(
            self.db, handle=f"n{uuid.uuid4().hex[:12]}", city=self.city.title()
        )
        if created:
            creator.created_at = created
        self.db.add(creator)
        self.db.flush()
        return creator

    def campaign(self, created: datetime, brand=None, status: str = "open"):
        campaign = build_campaign(
            self.db,
            brand_id=(brand or self.brand()).id,
            cities=[self.city],
            status=status,
            created_at=created,
            updated_at=created,
        )
        self.db.add(campaign)
        self.db.flush()
        return campaign

    def application(
        self, campaign, created: datetime, creator=None, *, invited=False, status=None
    ):
        row = Application(
            campaign_id=campaign.id,
            creator_id=(creator or self.creator()).id,
            origin="invited" if invited else "applied",
            pitch=None if invited else PITCH,
            status=status or ("invited" if invited else "submitted"),
            status_changed_at=created,
            created_at=created,
            updated_at=created,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def deal(self, campaign, agreed: datetime, creator=None, fee: int = 800_000):
        application = self.application(
            campaign, agreed - timedelta(hours=1), creator, status="accepted"
        )
        memo = DealMemo(
            application_id=application.id,
            deliverables="Three reels.",
            fee_amount_paise=fee,
            status="accepted",
            accepted_at=agreed,
            created_at=agreed,
            updated_at=agreed,
        )
        self.db.add(memo)
        self.db.flush()
        return memo

    def payment(self, memo, due_on: date, marked: datetime, confirmed: datetime):
        row = PaymentStatus(
            deal_memo_id=memo.id,
            amount_paise=memo.fee_amount_paise,
            due_on=due_on,
            method="upi",
            reference="412345678901",
            marked_paid_at=marked,
            confirmed_at=confirmed,
            created_at=marked,
            updated_at=confirmed,
        )
        self.db.add(row)
        self.db.flush()
        return row


@pytest.fixture
def world(db, city) -> World:
    return World(db, city)


# --- who may read it ---------------------------------------------------------------------


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_only_an_admin_reads_it(client, db, clock, role):
    user = brand_user(db, clock) if role == "brand" else creator_user(db, clock)

    assert client.get(URL, headers=user.headers).status_code == 404


def test_without_a_login_it_is_not_found(client):
    assert client.get(URL).status_code == 404


@pytest.mark.parametrize("days", [0, 91])
def test_a_period_outside_1_to_90_days_is_refused(client, admin, days):
    assert (
        client.get(URL, params={"days": days}, headers=admin.headers).status_code == 422
    )


# --- the counts --------------------------------------------------------------------------


def test_an_empty_period_is_zeros_and_nulls_never_invented_rates(client, admin, city):
    current = numbers(client, admin, city)["current"]

    assert current["campaigns_posted"] == 0
    assert current["campaign_fill_rate"] is None
    assert current["application_success_so_far"] is None
    assert current["repeat_share"] is None
    assert current["paid_on_time_share"] is None
    assert current["median_hours_to_first_application"] is None


def test_the_period_is_tamil_nadu_days_beside_the_one_before(client, admin, city):
    body = numbers(client, admin, city)

    assert (body["current"]["from_on"], body["current"]["to_on"]) == (
        "2024-03-25",
        "2024-03-31",
    )
    assert (body["previous"]["from_on"], body["previous"]["to_on"]) == (
        "2024-03-18",
        "2024-03-24",
    )
    assert body["city"] == city.lower()


def test_activity_lands_in_its_own_period(client, admin, world):
    world.creator(created=at(26))
    world.creator(created=at(20))  # the previous week
    brand = world.brand()
    world.campaign(at(26), brand)
    world.campaign(at(27), brand, status="draft")  # never posted: not counted
    world.campaign(at(19), brand)  # previous week

    body = numbers(client, admin, world.city)

    assert body["current"]["new_creators"] == 1
    assert body["previous"]["new_creators"] == 1
    assert body["current"]["campaigns_posted"] == 1
    assert body["previous"]["campaigns_posted"] == 1


def test_applications_and_invitations_are_counted_apart(client, admin, world):
    campaign = world.campaign(at(25))
    world.application(campaign, at(26))
    world.application(campaign, at(27), status="accepted")
    world.application(campaign, at(28), invited=True)

    current = numbers(client, admin, world.city)["current"]

    assert current["applications_sent"] == 2
    assert current["applications_accepted_so_far"] == 1
    assert current["invitations_sent"] == 1


def test_deals_their_value_and_repeats(client, admin, world):
    brand, creator = world.brand(), world.creator()
    first = world.campaign(at(20), brand)
    second = world.campaign(at(26), brand)
    world.deal(first, at(21), creator, fee=500_000)  # previous week
    world.deal(second, at(27), creator, fee=700_000)  # same pair again: a repeat
    world.deal(second, at(28), fee=300_000)  # a new creator

    body = numbers(client, admin, world.city)

    assert body["current"]["deals_agreed"] == 2
    assert body["current"]["value_of_deals_agreed_paise"] == 1_000_000
    assert body["current"]["repeat_deals"] == 1
    assert body["current"]["repeat_share"] is None  # 2 deals: below five
    assert body["previous"]["deals_agreed"] == 1
    assert body["previous"]["repeat_deals"] == 0


def test_paid_on_time_is_marked_paid_by_the_due_date_in_tamil_nadu(client, admin, world):
    campaign = world.campaign(at(10))
    for n in range(5):
        memo = world.deal(campaign, at(11 + n))
        # 19:00 UTC on the 26th is already the 27th in Tamil Nadu: one is late.
        marked = at(26, 19) if n == 0 else at(26, 10)
        world.payment(memo, date(2024, 3, 26), marked, at(28))

    current = numbers(client, admin, world.city)["current"]

    assert current["payments_confirmed"] == 5
    assert current["paid_on_time"] == 4
    assert current["paid_on_time_share"] == pytest.approx(0.8)


def test_active_brands_and_creators_did_something_that_moves_a_deal(client, admin, world):
    poster, dealer = world.brand(), world.brand()
    world.campaign(at(26), poster)
    applier = world.creator()
    old = world.campaign(at(5), dealer)
    world.application(old, at(27), applier)
    world.deal(old, at(28))

    current = numbers(client, admin, world.city)["current"]

    assert current["active_brands"] == 2
    assert current["active_creators"] == 2


# --- the rates ---------------------------------------------------------------------------


def test_the_fill_rate_counts_only_campaigns_old_enough_to_judge(client, admin, world):
    # A 30-day period: campaigns posted by the 17th are 14 days old by the 31st.
    for day in range(2, 7):  # five old enough
        campaign = world.campaign(at(day))
        if day <= 4:  # three filled within 14 days
            world.deal(campaign, at(day + 5))
    late = world.campaign(at(7))
    world.deal(late, at(7 + 20))  # filled, but after 14 days: not filled in time
    world.campaign(at(29))  # too young to judge

    current = numbers(client, admin, world.city, days=30)["current"]

    assert current["campaigns_posted"] == 7
    assert current["campaigns_old_enough_to_judge"] == 6
    assert current["campaigns_filled_within_14_days"] == 3
    assert current["campaign_fill_rate"] == pytest.approx(0.5)


def test_four_campaigns_are_not_enough_to_give_a_rate(client, admin, world):
    for day in range(2, 6):
        world.deal(world.campaign(at(day)), at(day + 1))

    current = numbers(client, admin, world.city, days=30)["current"]

    assert current["campaigns_filled_within_14_days"] == 4
    assert current["campaign_fill_rate"] is None


def test_hours_to_a_first_application_ignore_invitations(client, admin, world):
    for n, hours in enumerate((2, 4, 6, 8, 10)):
        campaign = world.campaign(at(25 + (n % 3), 1))
        world.application(
            campaign, campaign.created_at + timedelta(hours=1), invited=True
        )
        world.application(campaign, campaign.created_at + timedelta(hours=hours))

    current = numbers(client, admin, world.city)["current"]

    assert current["median_hours_to_first_application"] == 6.0


def test_a_city_sees_only_its_own_campaigns(client, admin, world, db):
    world.campaign(at(26))
    elsewhere = World(db, f"Elsewhere {uuid.uuid4().hex[:8]}")
    elsewhere.campaign(at(26))
    elsewhere.campaign(at(27))

    assert numbers(client, admin, world.city)["current"]["campaigns_posted"] == 1
    assert numbers(client, admin, elsewhere.city)["current"]["campaigns_posted"] == 2


# --- cost and limits ---------------------------------------------------------------------


def test_more_activity_costs_no_more_queries(client, admin, world):
    params = {"ending_on": END.isoformat(), "city": world.city}
    world.deal(world.campaign(at(26)), at(27))
    one = queries_for(client, URL, admin.headers, params)

    for day in range(25, 31):
        campaign = world.campaign(at(day))
        world.application(campaign, at(day, 14))
        world.deal(campaign, at(day, 16))
    many = queries_for(client, URL, admin.headers, params)

    assert many == one


def test_it_is_rate_limited(client, admin):
    allowed = int(NUMBERS_LIMIT.split()[0])

    answers = [
        client.get(URL, headers=admin.headers).status_code for _ in range(allowed + 1)
    ]

    assert answers[:allowed] == [200] * allowed
    assert answers[allowed] == 429


def test_the_period_ends_at_midnight_in_tamil_nadu(client, admin, world):
    # 23:00 on 31 March in Tamil Nadu is inside the period; 00:30 on 1 April
    # is not, though both are still 31 March in UTC.
    world.creator(created=datetime(2024, 3, 31, 17, 30, tzinfo=UTC))
    world.creator(created=datetime(2024, 3, 31, 19, 0, tzinfo=UTC))
    # And 00:30 on 25 March in Tamil Nadu is in, though UTC still says the 24th.
    world.creator(created=datetime(2024, 3, 24, 19, 0, tzinfo=UTC))

    current = numbers(client, admin, world.city)["current"]

    assert current["new_creators"] == 2
