"""Telling creators when a published campaign fits their alert (item 43, D-130).

Publishing queues the campaign in its own transaction; the job sends it.
The rules worth proving: the SQL asks exactly what `alert_rules.matches`
says; nobody is told twice, however the job runs; nobody is told of a
campaign they could not act on, nor by someone they cannot deal with; and
the daily cap holds. Every filter here has two or more creators, one told
and one not (testing.md section 2).
"""

import itertools
import uuid
from contextlib import nullcontext
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.modules.auth.models.account import Account
from app.modules.campaigns import alert_service
from app.modules.campaigns.alert_models import CampaignAlert, CampaignAlertSend
from app.modules.campaigns.alert_rules import AlertTerms, CampaignTerms, matches
from app.modules.campaigns.models import CAMPAIGN_TYPES
from app.modules.notifications.models import Notification
from app.modules.safety.models import AccountBlock
from tests.deal_flow import CAMPAIGNS_URL, User, brand_user, creator_user
from tests.factories import FIXED_NOW, build_campaign, build_creator, create_account
from tests.modules.admin.test_takedowns_api import brand_id_of, creator_id_of, withhold
from tests.query_counts import count_queries

BRIEF = {
    "title": "Pongal sweets launch",
    "description": "Three reels featuring our new sweet box.",
    "campaign_type": "paid",
    "budget_min_paise": 500_000,
    "budget_max_paise": 1_500_000,
    "cities": ["Madurai"],
    "niches": ["food"],
    "deliverables": "3 Instagram reels",
}


def clear_other_sends(db) -> None:
    """Sends a laptop's other runs left due would take this test's turn.
    Marked sent inside the test's transaction, which is rolled back."""
    db.execute(
        update(CampaignAlertSend)
        .where(CampaignAlertSend.sent_at.is_(None))
        .values(sent_at=FIXED_NOW, recipients=0)
    )


@pytest.fixture(autouse=True)
def only_this_tests_sends(db) -> None:
    clear_other_sends(db)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


def with_alert(db, user: User, **terms) -> CampaignAlert:
    alert = CampaignAlert(creator_id=uuid.UUID(creator_id_of(db, user)), **terms)
    db.add(alert)
    db.flush()
    return alert


def creator_alerted(db, clock, **terms) -> User:
    user = creator_user(db, clock)
    with_alert(db, user, **terms)
    return user


def publish(client, brand: User, **changes) -> str:
    made = client.post(CAMPAIGNS_URL, json=BRIEF | changes, headers=brand.headers)
    assert made.status_code == 201, made.text
    campaign_id = made.json()["id"]
    opened = client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    assert opened.status_code == 200, opened.text
    return campaign_id


def run(db, clock) -> alert_service.AlertRun:
    return alert_service.send_due(lambda: nullcontext(db), clock.now)


def alerts_to(db, user: User) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == "campaign_alert",
            )
        ).all()
    )


def told(db, user: User, campaign_id: str) -> bool:
    return any(str(n.campaign_id) == campaign_id for n in alerts_to(db, user))


def send_of(db, campaign_id: str) -> CampaignAlertSend:
    return db.scalars(
        select(CampaignAlertSend).where(
            CampaignAlertSend.campaign_id == uuid.UUID(campaign_id)
        )
    ).one()


# --- queueing and sending ----------------------------------------------------------


def test_publishing_queues_the_campaign_and_a_draft_is_not(client, db, brand):
    draft = client.post(CAMPAIGNS_URL, json=BRIEF, headers=brand.headers).json()["id"]
    published = publish(client, brand)

    send = send_of(db, published)
    assert (send.sent_at, send.recipients) == (None, None)
    assert (
        db.scalar(
            select(CampaignAlertSend.id).where(
                CampaignAlertSend.campaign_id == uuid.UUID(draft)
            )
        )
        is None
    )


def test_a_fitting_alert_is_told_and_one_that_does_not_fit_is_not(
    client, db, clock, brand
):
    by_city = creator_alerted(db, clock, city="madurai")
    by_type = creator_alerted(db, clock, campaign_type="paid", niche="food")
    other_city = creator_alerted(db, clock, city="Salem")
    other_niche = creator_alerted(db, clock, niche="tech")
    campaign_id = publish(client, brand)

    ran = run(db, clock)

    assert (ran.sends, ran.notified) == (1, 2)
    assert told(db, by_city, campaign_id) and told(db, by_type, campaign_id)
    assert not alerts_to(db, other_city) and not alerts_to(db, other_niche)
    (notice,) = alerts_to(db, by_city)
    assert notice.details == {"alert_id": str(with_alert_id(db, by_city))}
    send = send_of(db, campaign_id)
    assert (send.sent_at, send.recipients) == (clock.now, 2)


def with_alert_id(db, user: User) -> uuid.UUID:
    return db.scalars(
        select(CampaignAlert.id).where(
            CampaignAlert.creator_id == uuid.UUID(creator_id_of(db, user))
        )
    ).one()


def test_two_fitting_alerts_tell_a_creator_once(client, db, clock, brand):
    user = creator_alerted(db, clock, city="Madurai")
    with_alert(db, user, niche="food")
    campaign_id = publish(client, brand)

    run(db, clock)

    assert [str(n.campaign_id) for n in alerts_to(db, user)] == [campaign_id]


def test_a_send_cut_short_and_run_again_tells_nobody_twice(client, db, clock, brand):
    users = [creator_alerted(db, clock, city="Madurai") for _ in range(3)]
    campaign_id = publish(client, brand)
    run(db, clock)
    # As if the run had died after its batches but before its last commit.
    send = send_of(db, campaign_id)
    send.sent_at, send.recipients = None, None
    db.flush()

    again = run(db, clock)

    assert again.notified == 0
    assert all(len(alerts_to(db, user)) == 1 for user in users)
    assert send_of(db, campaign_id).recipients == 3


def test_a_big_send_goes_in_batches_and_reaches_everyone(
    client, db, clock, brand, monkeypatch
):
    monkeypatch.setattr(alert_service, "BATCH_SIZE", 2)
    users = [creator_alerted(db, clock, niche="food") for _ in range(5)]
    campaign_id = publish(client, brand)

    assert run(db, clock).notified == 5
    assert all(told(db, user, campaign_id) for user in users)
    assert send_of(db, campaign_id).recipients == 5


def test_the_oldest_due_campaign_goes_first(client, db, clock, brand, monkeypatch):
    monkeypatch.setattr(alert_service, "SENDS_PER_RUN", 1)
    user = creator_alerted(db, clock, niche="food")
    first = publish(client, brand)
    clock.advance(timedelta(minutes=1))
    second = publish(client, brand, title="Diwali sweets launch")

    run(db, clock)

    assert told(db, user, first) and not told(db, user, second)
    run(db, clock)
    assert told(db, user, second)


def test_the_cost_of_a_send_does_not_grow_with_its_recipients(client, db, clock):
    def cost(how_many: int) -> int:
        brand = brand_user(db, clock)
        city = f"Testpur {uuid.uuid4().hex[:8]}"
        for _ in range(how_many):
            creator_alerted(db, clock, city=city)
        publish(client, brand, cities=[city])
        with count_queries() as statements:
            assert run(db, clock).notified == how_many
        return len(statements)

    assert cost(2) == cost(8)


# --- the daily cap ---------------------------------------------------------------


def test_a_creator_hears_of_at_most_the_days_cap(client, db, clock, brand, monkeypatch):
    monkeypatch.setattr(alert_service, "MAX_ALERTS_A_DAY", 2)
    capped = creator_alerted(db, clock, niche="food")
    for n in range(3):
        publish(client, brand, title=f"Launch {n}")
    run(db, clock)
    assert len(alerts_to(db, capped)) == 2

    clock.advance(timedelta(days=1))
    publish(client, brand, title="The next day's launch")
    run(db, clock)

    assert len(alerts_to(db, capped)) == 3


def test_the_cap_is_a_tamil_nadu_day(client, db, clock, brand, monkeypatch):
    """23:00 and 01:00 UTC on the same date are two days in Tamil Nadu."""
    monkeypatch.setattr(alert_service, "MAX_ALERTS_A_DAY", 1)
    user = creator_alerted(db, clock, niche="food")
    clock.now = clock.now.replace(hour=18, minute=0)  # 23:30 in Tamil Nadu
    publish(client, brand, title="Late launch")
    run(db, clock)
    clock.advance(timedelta(hours=1))  # 00:30 the next day there
    publish(client, brand, title="Early launch")
    run(db, clock)

    assert len(alerts_to(db, user)) == 2


# --- nobody told of what they could not act on ------------------------------------


def suspend(db, account_id) -> None:
    db.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(suspended_at=FIXED_NOW, suspension_reason="fake_profile")
    )
    db.flush()


def admin_of(db, clock) -> User:
    return User(create_account(db, "admin").id, "admin", clock)


def their_other_side(db, clock, brand: User) -> User:
    """A creator account on the brand's own number (D-126)."""
    phone = db.get_one(Account, brand.account_id).phone
    account = create_account(db, "creator", phone=phone)
    db.add(
        build_creator(db, handle=f"side{uuid.uuid4().hex[:10]}", account_id=account.id)
    )
    db.flush()
    return User(account.id, "creator", clock)


CREATOR_LEFT_OUT = {
    "suspended": lambda client, db, clock, user, brand: suspend(db, user.account_id),
    "deleted": lambda client, db, clock, user, brand: db.execute(
        update(Account)
        .where(Account.id == user.account_id)
        .values(
            deletion_requested_at=FIXED_NOW - timedelta(days=30),
            deletion_takes_effect_at=FIXED_NOW,
            deleted_at=FIXED_NOW,
            phone=None,
        )
    ),
    "withheld": lambda client, db, clock, user, brand: withhold(
        client, admin_of(db, clock), "creator", creator_id_of(db, user)
    ),
    "blocked by the creator": lambda client, db, clock, user, brand: db.add(
        AccountBlock(
            blocker_account_id=user.account_id, blocked_account_id=brand.account_id
        )
    ),
    "blocked by the brand": lambda client, db, clock, user, brand: db.add(
        AccountBlock(
            blocker_account_id=brand.account_id, blocked_account_id=user.account_id
        )
    ),
}


@pytest.mark.parametrize("how", CREATOR_LEFT_OUT)
def test_a_creator_who_could_not_act_on_it_is_not_told(client, db, clock, brand, how):
    left_out = creator_alerted(db, clock, niche="food")
    kept = creator_alerted(db, clock, niche="food")
    CREATOR_LEFT_OUT[how](client, db, clock, left_out, brand)
    db.flush()
    campaign_id = publish(client, brand)

    run(db, clock)

    assert not told(db, left_out, campaign_id)
    assert told(db, kept, campaign_id)


def test_the_brands_own_other_side_is_never_told(client, db, clock, brand):
    own = their_other_side(db, clock, brand)
    with_alert(db, own, niche="food")
    kept = creator_alerted(db, clock, niche="food")
    campaign_id = publish(client, brand)

    run(db, clock)

    assert not told(db, own, campaign_id)
    assert told(db, kept, campaign_id)


CAMPAIGN_GONE = {
    "closed": lambda client, db, clock, brand, campaign_id: client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/close", headers=brand.headers
    ),
    "the brand suspended": lambda client, db, clock, brand, campaign_id: suspend(
        db, brand.account_id
    ),
    "the campaign withheld": lambda client, db, clock, brand, campaign_id: withhold(
        client, admin_of(db, clock), "campaign", campaign_id
    ),
    "the brand withheld": lambda client, db, clock, brand, campaign_id: withhold(
        client, admin_of(db, clock), "brand", brand_id_of(db, brand)
    ),
}


@pytest.mark.parametrize("how", CAMPAIGN_GONE)
def test_a_campaign_gone_before_its_turn_tells_nobody(client, db, clock, brand, how):
    user = creator_alerted(db, clock, niche="food")
    other_brand = brand_user(db, clock)
    gone = publish(client, brand)
    kept = publish(client, other_brand)
    CAMPAIGN_GONE[how](client, db, clock, brand, gone)
    db.flush()

    run(db, clock)

    assert not told(db, user, gone)
    assert told(db, user, kept)
    assert send_of(db, gone).recipients == 0


# --- the SQL asks what the rule says ----------------------------------------------


def test_the_sql_fits_exactly_the_alerts_the_rule_does(db, clock):
    """Every alert shape against campaigns of every kind, asked both ways."""
    terms = list(
        itertools.product(
            [None, "Madurai", "madurai", "Salem"],
            [None, "food", "tech"],
            [None, "paid", "barter", "commission"],
            [None, 500_000, 2_000_000],
        )
    )
    alerts = []
    for city, niche, campaign_type, budget in terms:
        if not any((city, niche, campaign_type, budget)):
            continue  # an alert names a term (ck_campaign_alert_names_a_term)
        if campaign_type == "barter" and budget is not None:
            continue  # ck_campaign_alert_no_budget_on_barter
        user = creator_user(db, clock)
        alerts.append(
            with_alert(
                db,
                user,
                city=city,
                niche=niche,
                campaign_type=campaign_type,
                min_budget_paise=budget,
            )
        )
    ids = [alert.id for alert in alerts]
    campaigns = [
        build_campaign(db, cities=["MADURAI", "Chennai"], niches=["food"]),
        build_campaign(
            db, cities=["Salem"], niches=["tech", "food"], budget_max_paise=2_000_000
        ),
        build_campaign(
            db,
            campaign_type="barter",
            budget_min_paise=None,
            budget_max_paise=None,
            cities=["Coimbatore"],
            niches=["travel"],
        ),
        build_campaign(
            db,
            campaign_type="commission",
            budget_min_paise=None,
            budget_max_paise=None,
            cities=["madurai"],
            niches=["tech"],
        ),
    ]
    assert {c.campaign_type for c in campaigns} <= set(CAMPAIGN_TYPES)

    for campaign in campaigns:
        asked = set(
            db.scalars(
                select(CampaignAlert.id).where(
                    CampaignAlert.id.in_(ids), *alert_service.fits(campaign)
                )
            ).all()
        )
        said = {
            alert.id
            for alert in alerts
            if matches(
                AlertTerms(
                    alert.city, alert.niche, alert.campaign_type, alert.min_budget_paise
                ),
                CampaignTerms(
                    campaign.cities,
                    campaign.niches,
                    campaign.campaign_type,
                    campaign.budget_max_paise,
                ),
            )
        }
        assert asked == said
        assert said and said != set(ids)  # each campaign fits some, not all
