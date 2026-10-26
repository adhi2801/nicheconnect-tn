"""Feedback on a finished deal (item 77, D-136).

The rules worth proving: only a finished deal takes feedback, once a side,
within 14 days; neither side's answer is seen, by anyone, until both have
answered or the window has closed; each is sealed; and a profile's figures
count only revealed answers, null below three, with how many partners they
come from.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.auth.models.account import Account
from app.modules.deal_memo.feedback_router import WRITE_LIMIT
from app.modules.deal_memo.record_models import DealRecordEntry
from app.modules.me import export_service
from app.modules.notifications.models import Notification
from tests.deal_flow import (
    MEMOS_URL,
    User,
    accepted_memo,
    brand_user,
    creator_user,
    finish_deal,
)
from tests.modules.admin.test_takedowns_api import brand_id_of, creator_id_of

GOOD = {"brief": 5, "reliability": 4, "easy": 5}


@pytest.fixture
def brand(db, clock) -> User:
    return brand_user(db, clock)


@pytest.fixture
def creator(db, clock) -> User:
    return creator_user(db, clock)


def finished(client, brand: User, creator: User) -> str:
    memo_id = accepted_memo(client, brand, creator)
    finish_deal(client, brand, creator, memo_id)
    return memo_id


def url(memo_id: str) -> str:
    return f"{MEMOS_URL}/{memo_id}/feedback"


def give(client, user: User, memo_id: str, **body):
    return client.post(url(memo_id), json=GOOD | body, headers=user.headers)


def given(client, user: User, memo_id: str, **body) -> dict:
    response = give(client, user, memo_id, **body)
    assert response.status_code == 201, response.text
    return response.json()


def seen(client, user: User, memo_id: str) -> dict:
    response = client.get(url(memo_id), headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_problem(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


# --- giving -------------------------------------------------------------------------


def test_an_unfinished_deal_takes_no_feedback(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    assert_problem(give(client, brand, memo_id), 409, "feedback_closed")
    assert seen(client, brand, memo_id)["window_ends_at"] is None


def test_one_side_answers_and_neither_sees_the_other_yet(
    client, db, clock, brand, creator
):
    memo_id = finished(client, brand, creator)

    body = given(client, brand, memo_id, note="Clear brief, delivered on time.")

    assert body["mine"]["note"] == "Clear brief, delivered on time."
    assert body["theirs"] is None
    theirs = seen(client, creator, memo_id)
    assert (theirs["mine"], theirs["theirs"], theirs["open"]) == (None, None, True)
    (entry,) = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.deal_memo_id == memo_id,
            DealRecordEntry.kind == "feedback_given",
        )
    ).all()
    assert entry.actor_role == "brand"
    assert set(entry.facts) == {"feedback_id", "feedback_sha256"}
    told = db.scalars(
        select(Notification).where(
            Notification.account_id == creator.account_id,
            Notification.notification_type == "feedback_received",
        )
    ).all()
    assert len(told) == 1 and "Clear brief" not in str(told[0].details)


def test_both_answers_show_once_both_have_answered(client, brand, creator):
    memo_id = finished(client, brand, creator)
    given(client, brand, memo_id, note="From the brand.")

    body = given(client, creator, memo_id, note="From the creator.")

    assert body["theirs"]["note"] == "From the brand."
    assert seen(client, brand, memo_id)["theirs"]["note"] == "From the creator."


def test_after_fourteen_days_an_answer_shows_and_no_more_are_taken(
    client, clock, brand, creator
):
    memo_id = finished(client, brand, creator)
    given(client, brand, memo_id, note="Only one side answered.")
    clock.advance(timedelta(days=14))

    assert seen(client, creator, memo_id)["theirs"]["note"] == "Only one side answered."
    assert_problem(give(client, creator, memo_id), 409, "feedback_closed")


def test_an_answer_is_given_once(client, brand, creator):
    memo_id = finished(client, brand, creator)
    given(client, brand, memo_id)

    assert_problem(give(client, brand, memo_id, brief=1), 409, "feedback_closed")
    assert seen(client, brand, memo_id)["mine"]["brief"] == GOOD["brief"]


@pytest.mark.parametrize(
    "change",
    [
        {"brief": 0},
        {"reliability": 6},
        {"easy": "five"},
        {"note": ""},
        {"note": "x" * 501},
        {"extra": 1},
    ],
)
def test_a_bad_answer_is_refused(client, brand, creator, change):
    memo_id = finished(client, brand, creator)

    assert give(client, brand, memo_id, **change).status_code == 422


def test_a_brands_note_asking_for_money_is_flagged(client, brand, creator):
    memo_id = finished(client, brand, creator)
    given(
        client,
        brand,
        memo_id,
        note="Pay a registration fee of 2000 to work with us again.",
    )
    given(client, creator, memo_id)

    flags = seen(client, creator, memo_id)["theirs"]["text_flags"]

    assert flags != []


def test_a_finished_barter_deal_takes_feedback(client, brand, creator):
    from tests.deal_flow import LINK
    from tests.modules.deal_memo.test_barter_shipment_api import barter_memo

    memo_id = barter_memo(client, brand, creator)
    proof = client.post(
        f"{MEMOS_URL}/{memo_id}/proof",
        json={"content_url": LINK, "format": "reel", "disclosure_confirmed": True},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"{MEMOS_URL}/{memo_id}/proof/{proof}/approve", headers=brand.headers)

    assert give(client, creator, memo_id).status_code == 201


def test_a_stranger_reaches_nothing(client, db, clock, brand, creator):
    memo_id = finished(client, brand, creator)

    for stranger in (brand_user(db, clock), creator_user(db, clock)):
        assert_problem(give(client, stranger, memo_id), 404, "memo_not_found")
        assert client.get(url(memo_id), headers=stranger.headers).status_code == 404


def test_giving_is_rate_limited_across_deals(client, db, clock, brand):
    """The limit counts per route across every deal (D-137), so a brand cannot
    escape it by answering on many deals."""
    from app.core.rate_limit import limiter

    limit = int(WRITE_LIMIT.split()[0])
    limiter.enabled = False  # building the deals is not what is tested
    try:
        memos = [
            finished(client, brand, creator_user(db, clock)) for _ in range(limit + 1)
        ]
    finally:
        limiter.enabled = True
    for memo_id in memos[:limit]:
        assert give(client, brand, memo_id).status_code == 201

    assert give(client, brand, memos[-1]).status_code == 429


# --- what a profile shows ------------------------------------------------------------


def creator_figures(client, user: User, creator: User, db) -> dict:
    response = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/feedback", headers=user.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_creators_figures_count_only_revealed_answers_and_wait_for_three(
    client, db, clock, creator
):
    brands = [brand_user(db, clock) for _ in range(3)]
    memos = [finished(client, b, creator) for b in brands]
    for b, memo_id in zip(brands[:2], memos[:2], strict=True):
        given(client, b, memo_id, brief=4)
        given(client, creator, memo_id)
    given(
        client, brands[2], memos[2], brief=1
    )  # not revealed: the creator has not answered
    reader = brand_user(db, clock)

    early = creator_figures(client, reader, creator, db)
    assert (early["answers"], early["brief"]) == (2, None)  # two is not enough to say

    given(client, creator, memos[2])
    body = creator_figures(client, reader, creator, db)
    assert (body["answers"], body["counterparties"]) == (3, 3)
    assert body["brief"] == pytest.approx(3.0)


def test_many_answers_from_one_partner_read_as_one_partner(client, db, clock, creator):
    only = brand_user(db, clock)
    for _ in range(3):
        memo_id = finished(client, only, creator)
        given(client, only, memo_id)
        given(client, creator, memo_id)

    body = creator_figures(client, brand_user(db, clock), creator, db)

    assert (body["answers"], body["counterparties"]) == (3, 1)


def test_another_creator_cannot_read_a_creators_figures(client, db, clock, creator):
    response = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/feedback",
        headers=creator_user(db, clock).headers,
    )

    assert response.status_code == 403


def test_a_brands_figures_and_notes_with_its_reply(client, db, clock, brand):
    creators = [creator_user(db, clock) for _ in range(3)]
    for c in creators:
        memo_id = finished(client, brand, c)
        given(client, c, memo_id, reliability=5, note="Paid on the day.")
        given(client, brand, memo_id, note="Great to work with.")

    figures = client.get(
        f"/api/v1/brands/{brand_id_of(db, brand)}/feedback", headers=creators[0].headers
    ).json()
    notes = client.get(
        f"/api/v1/brands/{brand_id_of(db, brand)}/feedback/notes",
        headers=creators[0].headers,
    ).json()["items"]

    assert (figures["answers"], figures["reliability"]) == (3, 5.0)
    assert [(n["note"], n["reply"]) for n in notes] == [
        ("Paid on the day.", "Great to work with.")
    ] * 3


def test_an_unrevealed_note_is_in_no_list(client, db, clock, brand, creator):
    memo_id = finished(client, brand, creator)
    given(client, brand, memo_id, note="Not yet seen.")

    body = client.get(
        f"/api/v1/creators/{creator_id_of(db, creator)}/feedback/notes",
        headers=brand_user(db, clock).headers,
    ).json()

    assert body["items"] == []


def test_the_other_sides_export_holds_an_answer_only_once_revealed(
    client, db, clock, brand, creator
):
    memo_id = finished(client, brand, creator)
    given(client, brand, memo_id, note="Hidden for now.")

    def exported(user: User) -> list[dict]:
        return export_service.build_export(
            db, db.get_one(Account, user.account_id), clock.now
        )["data"]["deal_feedback"]

    assert [f["note"] for f in exported(brand)] == ["Hidden for now."]
    assert exported(creator) == []
    given(client, creator, memo_id)
    assert sorted(f["author_side"] for f in exported(creator)) == ["brand", "creator"]


def test_each_answer_is_sealed_by_its_fingerprint(client, db, brand, creator):
    """Worked out here from what was said, not by the function being tested."""
    import json

    from app.modules.deal_memo import record_service

    memo_id = finished(client, brand, creator)
    given(client, brand, memo_id, brief=3, reliability=4, easy=5, note="Sealed.")

    (entry,) = db.scalars(
        select(DealRecordEntry).where(
            DealRecordEntry.kind == "feedback_given",
            DealRecordEntry.deal_memo_id == memo_id,
        )
    ).all()
    said = {"brief": 3, "easy": 5, "note": "Sealed.", "reliability": 4}

    assert entry.facts["feedback_sha256"] == record_service.fingerprint(
        json.dumps(said, sort_keys=True, separators=(",", ":"))
    )
