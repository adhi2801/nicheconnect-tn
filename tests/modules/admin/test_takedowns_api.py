"""Admins withholding one item, and lifting it (item 52, D-104).

What the item looks like to everyone else while it is withheld is
tests/modules/safety/test_takedown_visibility_api.py. This file is the
admin's side: the order and its 3-hour clock, the owner told, the admin log,
the preserved text, and every refusal.
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.modules.admin.models.admin_action import AdminAction
from app.modules.auth.models.account import Account
from app.modules.auth.models.brand import Brand
from app.modules.auth.models.creator import Creator
from tests.deal_flow import CAMPAIGNS_URL, User, brand_user, creator_user
from tests.factories import create_account
from tests.modules.campaigns.test_invitation_api import open_campaign
from tests.query_counts import queries_for

URL = "/api/v1/admin/takedowns"
MINE = "/api/v1/me/takedowns"
NOTIFICATIONS = "/api/v1/notifications"
ORDER = {
    "basis": "court_order",
    "issued_by": "High Court of Madras",
    "order_reference": "WP 1012 of 2026",
    "legal_provision": "IT Act 2000, section 79(3)(b)",
    "note": "Order received by email; it names this campaign.",
}


@pytest.fixture
def admin(db, clock) -> User:
    return User(create_account(db, "admin").id, "admin", clock)


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def creator_id_of(db, user: User) -> str:
    return str(db.scalar(select(Creator.id).where(Creator.account_id == user.account_id)))


def brand_id_of(db, user: User) -> str:
    return str(db.scalar(select(Brand.id).where(Brand.account_id == user.account_id)))


def stamp(moment) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def withhold(client, admin: User, kind: str, subject_id, *, received_ago=None, **body):
    """An order received `received_ago` before the clock's now (an hour by default)."""
    fields = dict(ORDER)
    fields.update(subject_kind=kind, subject_id=str(subject_id))
    fields.update(body)
    if fields["basis"] != "report" and "received_at" not in body:
        fields["received_at"] = stamp(
            admin.clock.now - (received_ago or timedelta(hours=1))
        )
    # None leaves a field out, as a client would.
    sent = {key: value for key, value in fields.items() if value is not None}
    return client.post(URL, json=sent, headers=admin.headers)


def notifications_of(client, user: User, kind: str) -> list[dict]:
    items = client.get(NOTIFICATIONS, headers=user.headers).json()["items"]
    return [n for n in items if n["notification_type"] == kind]


# --- withholding on an order ------------------------------------------------------------


def test_an_order_withholds_one_campaign(client, db, admin, brand, clock):
    campaign_id = open_campaign(client, brand)

    response = withhold(client, admin, "campaign", campaign_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert response.headers["Location"] == f"{URL}/{body['id']}"
    assert body["subject_kind"] == "campaign"
    assert body["subject_id"] == campaign_id
    assert body["owner_account_id"] == str(brand.account_id)
    assert body["basis"] == "court_order"
    assert body["issued_by"] == "High Court of Madras"
    assert body["withheld_at"] == stamp(clock.now)
    assert body["withheld_by_account_id"] == str(admin.account_id)
    assert body["lifted_at"] is None
    assert body["preserved"]["title"] == "Pongal sweets launch"


def test_the_clock_is_three_hours_from_when_the_order_reached_us(
    client, admin, brand, clock
):
    campaign_id = open_campaign(client, brand)

    body = withhold(
        client, admin, "campaign", campaign_id, received_ago=timedelta(hours=2)
    ).json()

    assert body["received_at"] == stamp(clock.now - timedelta(hours=2))
    assert body["due_at"] == stamp(clock.now + timedelta(hours=1))
    assert body["late"] is False


def test_acted_on_after_three_hours_is_late(client, admin, brand):
    campaign_id = open_campaign(client, brand)

    body = withhold(
        client,
        admin,
        "campaign",
        campaign_id,
        received_ago=timedelta(hours=3, seconds=1),
    ).json()

    assert body["late"] is True


def test_acted_on_exactly_at_three_hours_is_in_time(client, admin, brand):
    campaign_id = open_campaign(client, brand)

    body = withhold(
        client, admin, "campaign", campaign_id, received_ago=timedelta(hours=3)
    ).json()

    assert body["late"] is False


@pytest.mark.parametrize(
    "received_ago", [timedelta(minutes=-1), timedelta(days=30, seconds=1)]
)
def test_the_order_must_have_reached_us_in_the_last_30_days(
    client, admin, brand, received_ago
):
    """In the future, or a mistyped year: either would make the clock a lie."""
    campaign_id = open_campaign(client, brand)

    response = withhold(client, admin, "campaign", campaign_id, received_ago=received_ago)

    assert response.status_code == 422
    assert response.json()["code"] == "order_time_not_possible"


def test_received_30_days_ago_is_accepted(client, admin, brand):
    campaign_id = open_campaign(client, brand)

    response = withhold(
        client, admin, "campaign", campaign_id, received_ago=timedelta(days=30)
    )

    assert response.status_code == 201, response.text
    assert response.json()["late"] is True


@pytest.mark.parametrize("missing", ["issued_by", "order_reference", "received_at"])
def test_an_order_names_who_issued_it_its_number_and_when_it_came(
    client, admin, brand, missing
):
    campaign_id = open_campaign(client, brand)

    response = withhold(client, admin, "campaign", campaign_id, **{missing: None})

    assert response.status_code == 422


def test_a_time_without_a_zone_is_refused(client, admin, brand, clock):
    campaign_id = open_campaign(client, brand)

    response = withhold(
        client,
        admin,
        "campaign",
        campaign_id,
        received_at=clock.now.replace(tzinfo=None).isoformat(),
    )

    assert response.status_code == 422


def test_a_government_notice_is_an_order_too(client, admin, creator, db):
    response = withhold(
        client,
        admin,
        "creator",
        creator_id_of(db, creator),
        basis="government_notice",
        issued_by="Deputy Inspector General of Police, Cyber Crime, Chennai",
        legal_provision=None,
    )

    assert response.status_code == 201, response.text
    assert response.json()["legal_provision"] is None


def test_an_unknown_item_is_not_found(client, admin):
    for kind in ("creator", "brand", "campaign"):
        response = withhold(client, admin, kind, uuid.uuid4())

        assert response.status_code == 404
        assert response.json()["code"] == "takedown_subject_not_found"


def test_an_item_is_withheld_once(client, admin, brand):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "campaign", campaign_id)

    response = withhold(client, admin, "campaign", campaign_id)

    assert response.status_code == 409
    assert response.json()["code"] == "already_withheld"


def test_a_repeated_tap_withholds_once(client, admin, brand):
    """The same Idempotency-Key answers the first response, not a 409 (D-040)."""
    campaign_id = open_campaign(client, brand)
    key = {"Idempotency-Key": uuid.uuid4().hex}
    body = {
        **ORDER,
        "subject_kind": "campaign",
        "subject_id": campaign_id,
        "received_at": stamp(admin.clock.now - timedelta(hours=1)),
    }

    first = client.post(URL, json=body, headers={**admin.headers, **key})
    again = client.post(URL, json=body, headers={**admin.headers, **key})

    assert (first.status_code, again.status_code) == (201, 201)
    assert first.json()["id"] == again.json()["id"]


# --- on a report ------------------------------------------------------------------------


def file_report(client, user: User, kind: str, subject_id, category="impersonation"):
    response = client.post(
        "/api/v1/reports",
        json={"subject_kind": kind, "subject_id": str(subject_id), "category": category},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_a_report_keeps_its_own_clock(client, db, admin, brand, creator, clock):
    filed = file_report(client, brand, "creator", creator_id_of(db, creator))
    clock.advance(timedelta(minutes=40))

    response = withhold(
        client,
        admin,
        "creator",
        creator_id_of(db, creator),
        basis="report",
        issued_by=None,
        order_reference=None,
        legal_provision=None,
        report_id=filed["id"],
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["basis"] == "report"
    assert body["received_at"] == filed["created_at"]
    assert body["due_at"] == filed["due_at"]  # 2 hours: impersonation (item 51)
    assert body["late"] is False
    assert body["report_id"] == filed["id"]


REPORT_BODY = {
    "basis": "report",
    "issued_by": None,
    "order_reference": None,
    "legal_provision": None,
}


def test_a_report_about_something_else_is_refused(client, db, admin, brand, creator):
    filed = file_report(client, creator, "brand", brand_id_of(db, brand))

    response = withhold(
        client,
        admin,
        "creator",
        creator_id_of(db, creator),
        **REPORT_BODY,
        report_id=filed["id"],
    )

    assert response.status_code == 422
    assert response.json()["code"] == "report_names_another_item"


def test_an_unknown_report_is_not_found(client, db, admin, creator):
    response = withhold(
        client,
        admin,
        "creator",
        creator_id_of(db, creator),
        **REPORT_BODY,
        report_id=str(uuid.uuid4()),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "report_not_found"


@pytest.mark.parametrize(
    "extra",
    [
        {},  # no report_id
        {"report_id": str(uuid.uuid4()), "issued_by": "High Court of Madras"},
        {"report_id": str(uuid.uuid4()), "reference_sealed": True},
        {"report_id": str(uuid.uuid4()), "received_at": "2026-10-16T00:00:00Z"},
    ],
)
def test_a_report_takedown_carries_no_order_details(client, db, admin, creator, extra):
    body = {
        "subject_kind": "creator",
        "subject_id": creator_id_of(db, creator),
        "basis": "report",
        "note": "Looking into an impersonation report.",
        **extra,
    }

    assert client.post(URL, json=body, headers=admin.headers).status_code == 422


def test_an_order_may_name_the_report_it_answers(client, db, admin, brand, creator):
    filed = file_report(client, brand, "creator", creator_id_of(db, creator))

    response = withhold(
        client, admin, "creator", creator_id_of(db, creator), report_id=filed["id"]
    )

    assert response.status_code == 201, response.text
    assert response.json()["report_id"] == filed["id"]


# --- the owner, the log, the preserved text ---------------------------------------------


def test_the_owner_is_told_at_once(client, admin, brand):
    campaign_id = open_campaign(client, brand)
    takedown = withhold(client, admin, "campaign", campaign_id).json()

    [told] = notifications_of(client, brand, "content_withheld")

    assert told["details"] == {
        "takedown_id": takedown["id"],
        "subject_kind": "campaign",
        "subject_id": campaign_id,
        "basis": "court_order",
    }


def test_the_admin_log_records_who_why_and_about_whom(client, db, admin, brand):
    campaign_id = open_campaign(client, brand)
    withhold(client, admin, "campaign", campaign_id)

    [entry] = db.scalars(
        select(AdminAction).where(
            AdminAction.admin_account_id == admin.account_id,
            AdminAction.action == "withhold",
        )
    ).all()

    assert entry.subject_account_id == brand.account_id
    assert entry.note == ORDER["note"]


def test_an_edit_after_it_cannot_change_what_was_preserved(client, admin, brand):
    campaign_id = open_campaign(client, brand)
    takedown = withhold(client, admin, "campaign", campaign_id).json()

    edited = client.patch(
        f"{CAMPAIGNS_URL}/{campaign_id}",
        json={"description": "Nothing to see here."},
        headers=brand.headers,
    )
    [listed] = client.get(URL, headers=admin.headers).json()["items"][:1]

    assert edited.status_code == 200, edited.text
    assert listed["id"] == takedown["id"]
    assert (
        listed["preserved"]["description"] == "Three reels featuring our new sweet box."
    )


def test_a_creator_is_preserved_with_their_links_and_packages(client, db, admin, creator):
    client.post(
        "/api/v1/creators/me/packages",
        json={
            "platform": "instagram",
            "format": "reel",
            "title": "1 Instagram Reel",
            "description": "One reel, shot and edited by me.",
            "price_paise": 800_000,
            "delivery_days": 5,
            "usage_rights_days": 30,
            "position": 0,
        },
        headers=creator.headers,
    )

    preserved = withhold(client, admin, "creator", creator_id_of(db, creator)).json()[
        "preserved"
    ]

    handle = db.scalar(
        select(Creator.handle).where(Creator.account_id == creator.account_id)
    )
    assert preserved["handle"] == handle
    assert preserved["packages"] == [
        {"title": "1 Instagram Reel", "description": "One reel, shot and edited by me."}
    ]
    assert "channels" in preserved
    assert "price_paise" not in str(preserved)


def test_a_brand_is_preserved_by_name_and_campaigns_never_its_email(
    client, db, admin, brand
):
    first = open_campaign(client, brand, title="Pongal")
    second = open_campaign(client, brand, title="Diwali")

    preserved = withhold(client, admin, "brand", brand_id_of(db, brand)).json()[
        "preserved"
    ]

    assert preserved["name"] == "Acme"
    assert {c["id"] for c in preserved["open_campaigns"]} == {first, second}
    assert preserved["more_open_campaigns"] is False
    assert "@" not in str(preserved)


# --- lifting ----------------------------------------------------------------------------


def lift(
    client, admin: User, takedown_id: str, note="The order was set aside on appeal."
):
    return client.post(
        f"{URL}/{takedown_id}/lift", json={"note": note}, headers=admin.headers
    )


def test_lifting_restores_it_and_tells_the_owner(client, db, admin, brand, clock):
    campaign_id = open_campaign(client, brand)
    takedown = withhold(client, admin, "campaign", campaign_id).json()
    clock.advance(timedelta(days=2))

    response = lift(client, admin, takedown["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lifted_at"] == stamp(clock.now)
    assert body["lifted_by_account_id"] == str(admin.account_id)
    assert body["preserved"] == takedown["preserved"]  # the record stays
    [told] = notifications_of(client, brand, "content_restored")
    assert told["details"]["takedown_id"] == takedown["id"]
    assert (
        db.scalar(select(AdminAction.note).where(AdminAction.action == "lift_withhold"))
        == "The order was set aside on appeal."
    )


def test_a_takedown_is_lifted_once(client, admin, brand):
    takedown = withhold(client, admin, "campaign", open_campaign(client, brand)).json()
    lift(client, admin, takedown["id"])

    response = lift(client, admin, takedown["id"])

    assert response.status_code == 409
    assert response.json()["code"] == "takedown_already_lifted"


def test_lifting_an_unknown_takedown_is_not_found(client, admin):
    response = lift(client, admin, str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "takedown_not_found"


def test_a_lift_needs_a_note(client, admin, brand):
    takedown = withhold(client, admin, "campaign", open_campaign(client, brand)).json()

    assert lift(client, admin, takedown["id"], note="").status_code == 422


def test_after_a_lift_the_item_can_be_withheld_again(client, admin, brand):
    campaign_id = open_campaign(client, brand)
    first = withhold(client, admin, "campaign", campaign_id).json()
    lift(client, admin, first["id"])

    second = withhold(client, admin, "campaign", campaign_id)

    assert second.status_code == 201, second.text
    assert second.json()["id"] != first["id"]


# --- the list ---------------------------------------------------------------------------


def test_the_list_filters_active_and_lifted(client, admin, brand):
    kept = withhold(client, admin, "campaign", open_campaign(client, brand)).json()
    lifted = withhold(client, admin, "campaign", open_campaign(client, brand)).json()
    lift(client, admin, lifted["id"])

    def listed(**params) -> list[str]:
        response = client.get(URL, params=params, headers=admin.headers)
        assert response.status_code == 200, response.text
        return [t["id"] for t in response.json()["items"]]

    assert kept["id"] in listed(active=True) and lifted["id"] not in listed(active=True)
    assert lifted["id"] in listed(active=False) and kept["id"] not in listed(active=False)
    assert {kept["id"], lifted["id"]} <= set(listed())


def test_the_list_pages_without_gaps_or_repeats(client, admin, brand, clock):
    made = []
    for _ in range(5):
        made.append(
            withhold(client, admin, "campaign", open_campaign(client, brand)).json()["id"]
        )
        clock.advance(timedelta(seconds=1))

    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get(URL, params=params, headers=admin.headers).json()
        seen += [t["id"] for t in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break

    mine = [t for t in seen if t in made]
    assert mine == list(reversed(made))
    assert len(seen) == len(set(seen))


def test_a_longer_list_costs_no_more_queries(client, admin, brand):
    withhold(client, admin, "campaign", open_campaign(client, brand))
    one = queries_for(client, URL, admin.headers)

    for _ in range(4):
        withhold(client, admin, "campaign", open_campaign(client, brand))
    five = queries_for(client, URL, admin.headers)

    assert five == one


# --- nobody else ------------------------------------------------------------------------


def test_nobody_but_an_admin_finds_these_routes(client, db, brand, creator, admin):
    campaign_id = open_campaign(client, brand)
    takedown = withhold(client, admin, "campaign", campaign_id).json()
    body = {
        **ORDER,
        "subject_kind": "campaign",
        "subject_id": campaign_id,
        "received_at": stamp(admin.clock.now),
    }

    for headers in (brand.headers, creator.headers, {}):
        assert client.post(URL, json=body, headers=headers).status_code == 404
        assert client.get(URL, headers=headers).status_code == 404
        assert (
            client.post(
                f"{URL}/{takedown['id']}/lift",
                json={"note": "Mine now."},
                headers=headers,
            ).status_code
            == 404
        )


def test_a_suspended_admin_cannot_withhold(client, db, admin, brand, clock):
    db.execute(
        update(Account)
        .where(Account.id == admin.account_id)
        .values(suspended_at=clock.now, suspension_reason="other")
    )
    db.flush()

    response = withhold(client, admin, "campaign", open_campaign(client, brand))

    assert response.status_code == 404
