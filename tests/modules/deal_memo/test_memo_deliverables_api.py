"""Deliverables as a list (item 26, D-127), through the API.

A campaign's list pre-fills the memo's; the memo's changes only while it is
editable; from terms version 2 the deal record seals it, so changing a line
afterwards shows as changed terms, while every memo sealed before keeps its
version 1 fingerprint. The tables' rules are in test_memo_deliverables_model.py.
"""

import pytest
from sqlalchemy import select, text

from app.modules.auth.models.account import Account
from app.modules.me import export_service
from tests.deal_flow import (
    AGREED_DUE_ON,
    CAMPAIGNS_URL,
    MEMOS_URL,
    PITCH,
    User,
    brand_user,
    creator_user,
)

ITEMS = [
    {"platform": "instagram", "format": "reel", "quantity": 2},
    {
        "platform": "instagram",
        "format": "story",
        "quantity": 1,
        "note": "60 seconds, in Tamil",
    },
]


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


def campaign_body(items=None) -> dict:
    body = {
        "title": "Pongal sweets launch",
        "description": "Reels featuring our new sweet box.",
        "campaign_type": "paid",
        "budget_min_paise": 300_000,
        "budget_max_paise": 1_500_000,
        "cities": ["Madurai"],
        "niches": ["food"],
        "deliverables": "2 Instagram reels and a story",
    }
    if items is not None:
        body["deliverable_items"] = items
    return body


def accepted_application(client, brand: User, creator: User, items=ITEMS) -> str:
    campaign_id = client.post(
        CAMPAIGNS_URL, json=campaign_body(items), headers=brand.headers
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    return str(application_id)


def draft(client, brand: User, application_id: str, **extra) -> dict:
    response = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={
            "deliverables": "2 reels and a story.",
            "fee_amount_paise": 800_000,
            "content_due_on": AGREED_DUE_ON,
            **extra,
        },
        headers=brand.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def lines(read: dict) -> list[tuple]:
    return [
        (i["platform"], i["format"], i["quantity"], i["note"])
        for i in read["deliverable_items"]
    ]


def agree(client, brand: User, creator: User, memo_id: str) -> None:
    client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    accepted = client.post(f"{MEMOS_URL}/{memo_id}/accept", headers=creator.headers)
    assert accepted.status_code == 200, accepted.text


def record(client, user: User, memo_id: str) -> dict:
    response = client.get(f"{MEMOS_URL}/{memo_id}/record", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- the campaign's list -----------------------------------------------------------------


def test_a_campaign_keeps_its_list_in_order(client, brand):
    created = client.post(CAMPAIGNS_URL, json=campaign_body(ITEMS), headers=brand.headers)

    assert created.status_code == 201, created.text
    assert lines(created.json()) == [
        ("instagram", "reel", 2, None),
        ("instagram", "story", 1, "60 seconds, in Tamil"),
    ]
    read = client.get(
        f"{CAMPAIGNS_URL}/{created.json()['id']}", headers=brand.headers
    ).json()
    assert lines(read) == lines(created.json())


def test_a_campaign_without_a_list_has_an_empty_one(client, brand):
    created = client.post(CAMPAIGNS_URL, json=campaign_body(), headers=brand.headers)

    assert created.json()["deliverable_items"] == []


def test_an_open_campaigns_list_can_be_replaced_like_its_text(client, brand):
    campaign_id = client.post(
        CAMPAIGNS_URL, json=campaign_body(ITEMS), headers=brand.headers
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)

    updated = client.patch(
        f"{CAMPAIGNS_URL}/{campaign_id}",
        json={
            "deliverable_items": [
                {"platform": "youtube", "format": "short", "quantity": 3}
            ]
        },
        headers=brand.headers,
    )

    assert updated.status_code == 200, updated.text
    assert lines(updated.json()) == [("youtube", "short", 3, None)]


@pytest.mark.parametrize(
    "items",
    [
        [{"platform": "instagram", "format": "reel", "quantity": 1}] * 11,
        [{"platform": "instagram", "format": "reel", "quantity": 0}],
        [{"platform": "instagram", "format": "reel", "quantity": 21}],
        [{"platform": "tiktok", "format": "reel", "quantity": 1}],
        [{"platform": "instagram", "format": "carousel", "quantity": 1}],
        [{"platform": "instagram", "format": "reel", "note": "x" * 201}],
        [{"platform": "instagram", "format": "reel", "note": ""}],
        [{"platform": "instagram", "format": "reel", "unexpected": 1}],
    ],
)
def test_a_bad_list_is_refused(client, brand, items):
    response = client.post(
        CAMPAIGNS_URL, json=campaign_body(items), headers=brand.headers
    )

    assert response.status_code == 422


# --- the memo's list ------------------------------------------------------------------------


def test_a_memo_starts_from_the_campaigns_list(client, brand, creator):
    application_id = accepted_application(client, brand, creator)

    memo = draft(client, brand, application_id)

    assert lines(memo) == [
        ("instagram", "reel", 2, None),
        ("instagram", "story", 1, "60 seconds, in Tamil"),
    ]


def test_a_memo_may_set_its_own_list_or_none(client, brand, creator):
    own = draft(
        client,
        brand,
        accepted_application(client, brand, creator),
        deliverable_items=[{"platform": "youtube", "format": "video", "quantity": 1}],
    )
    other_creator = creator
    none = draft(
        client,
        brand,
        accepted_application(client, brand, other_creator),
        deliverable_items=[],
    )

    assert lines(own) == [("youtube", "video", 1, None)]
    assert none["deliverable_items"] == []


def test_a_draft_memos_list_can_be_replaced(client, brand, creator):
    memo = draft(client, brand, accepted_application(client, brand, creator))

    updated = client.patch(
        f"{MEMOS_URL}/{memo['id']}",
        json={
            "deliverable_items": [
                {"platform": "instagram", "format": "post", "quantity": 4}
            ]
        },
        headers=brand.headers,
    )

    assert updated.status_code == 200, updated.text
    assert lines(updated.json()) == [("instagram", "post", 4, None)]


def test_a_sent_memos_list_cannot_change(client, brand, creator):
    memo = draft(client, brand, accepted_application(client, brand, creator))
    client.post(f"{MEMOS_URL}/{memo['id']}/send", headers=brand.headers)

    response = client.patch(
        f"{MEMOS_URL}/{memo['id']}",
        json={"deliverable_items": []},
        headers=brand.headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "memo_not_editable"


def test_both_sides_read_the_same_list(client, brand, creator):
    memo = draft(client, brand, accepted_application(client, brand, creator))
    agree(client, brand, creator, memo["id"])

    for user in (brand, creator):
        read = client.get(f"{MEMOS_URL}/{memo['id']}", headers=user.headers).json()
        assert lines(read) == lines(memo)
    listed = client.get(f"{MEMOS_URL}/mine", headers=creator.headers).json()["items"]
    assert [lines(m) for m in listed if m["id"] == memo["id"]] == [lines(memo)]


# --- the record --------------------------------------------------------------------------------


def test_the_record_proves_the_list_it_was_agreed_with(client, db, brand, creator):
    memo = draft(client, brand, accepted_application(client, brand, creator))
    agree(client, brand, creator, memo["id"])

    assert record(client, brand, memo["id"])["terms_unchanged_since_accepted"] is True

    db.execute(
        text(
            "UPDATE memo_deliverable SET quantity = 3 WHERE deal_memo_id = :m AND position = 0"
        ),
        {"m": memo["id"]},
    )
    db.commit()

    assert record(client, brand, memo["id"])["terms_unchanged_since_accepted"] is False


def test_a_version_1_memo_still_proves_its_terms(client, db, brand, creator):
    """Every memo sealed before D-127 keeps the fingerprint it was sealed with.

    The seal is checked against version 1's fields worked out by hand, as
    every earlier seal was made, not against our own code, which would agree
    with itself whatever it did.
    """
    import hashlib
    import json

    from app.modules.deal_memo.models import DealMemo
    from app.modules.deal_memo.record_models import DealRecordEntry
    from app.modules.deal_memo.record_service import TERMS_FIELDS

    application_id = accepted_application(client, brand, creator)
    memo = draft(client, brand, application_id)
    db.execute(
        text("UPDATE deal_memo SET terms_version = 1 WHERE id = :m"), {"m": memo["id"]}
    )
    db.commit()
    agree(client, brand, creator, memo["id"])

    row = db.get_one(DealMemo, memo["id"])
    terms = {field: getattr(row, field) for field in TERMS_FIELDS}
    terms["content_due_on"] = row.content_due_on.isoformat()
    by_hand = hashlib.sha256(
        json.dumps(terms, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    sealed = db.scalars(
        select(DealRecordEntry.facts).where(
            DealRecordEntry.deal_memo_id == row.id,
            DealRecordEntry.kind == "memo_accepted",
        )
    ).one()

    assert sealed["terms_sha256"] == by_hand
    assert record(client, creator, memo["id"])["terms_unchanged_since_accepted"] is True


def test_a_repeat_deal_keeps_the_list(client, db, brand, creator):
    from tests.deal_flow import finish_deal

    first = draft(client, brand, accepted_application(client, brand, creator))
    agree(client, brand, creator, first["id"])
    finish_deal(client, brand, creator, first["id"])
    second_campaign = client.post(
        CAMPAIGNS_URL, json=campaign_body(), headers=brand.headers
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{second_campaign}/publish", headers=brand.headers)
    invitation = client.post(
        f"{MEMOS_URL}/{first['id']}/repeat",
        json={"campaign_id": second_campaign},
        headers=brand.headers,
    )
    assert invitation.status_code == 201, invitation.text
    accepted = client.post(
        f"/api/v1/applications/{invitation.json()['id']}/accept-invitation",
        headers=creator.headers,
    )
    assert accepted.status_code == 200, accepted.text

    memos = client.get(f"{MEMOS_URL}/mine", headers=brand.headers).json()["items"]
    repeat = next(m for m in memos if m["application_id"] == invitation.json()["id"])

    assert lines(repeat) == lines(first)


def test_both_exports_hold_the_lists(client, db, clock, brand, creator):
    memo = draft(client, brand, accepted_application(client, brand, creator))

    brand_export = export_service.build_export(
        db, db.get_one(Account, brand.account_id), clock.now
    )
    creator_export = export_service.build_export(
        db, db.get_one(Account, creator.account_id), clock.now
    )

    assert [r["quantity"] for r in brand_export["data"]["campaign_deliverables"]] == [
        2,
        1,
    ]
    for exported in (brand_export, creator_export):
        rows = [
            r
            for r in exported["data"]["memo_deliverables"]
            if r["deal_memo_id"] == memo["id"]
        ]
        assert [(r["format"], r["quantity"]) for r in rows] == [("reel", 2), ("story", 1)]
