"""Deleting your account (item 6, D-122), through the API: asking, waiting, cancelling.

A code for `delete_account`; refused while a deal is unfinished; 30 days the
owner can cancel with no code, told by a notice nobody can mute and first on
the attention list. What the erasure itself does is in
test_account_deletion_erasure.py, its races in
test_account_deletion_concurrency.py, the table's rules in
tests/modules/auth/test_account_model.py.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.clock import india_date
from app.modules.auth.models.step_up_challenge import StepUpChallenge
from app.modules.me import account_deletion_service as service
from app.modules.me.account_deletion_registry import KEPT
from app.modules.me.account_deletion_router import REQUEST_LIMIT
from app.modules.notifications.models import Notification
from app.modules.notifications.preference_models import URGENT_TYPES
from tests.deal_flow import (
    CAMPAIGNS_URL,
    MEMOS_URL,
    PITCH,
    User,
    accepted_memo,
    brand_user,
    creator_user,
    finish_deal,
)
from tests.factories import create_account
from tests.step_up import STEP_UP_URL, with_code

URL = "/api/v1/me/deletion"
ATTENTION_URL = "/api/v1/me/attention"


@pytest.fixture
def creator(db, clock) -> User:
    user = creator_user(db, clock)
    # Committed, so a refusal's rollback inside a request cannot undo it.
    db.commit()
    return user


@pytest.fixture
def brand(db, clock) -> User:
    user = brand_user(db, clock)
    db.commit()
    return user


def draft_memo(client, brand: User, creator: User) -> str:
    """An accepted application and a memo the brand has not sent yet."""
    campaign_id = client.post(
        CAMPAIGNS_URL,
        json={
            "title": "Diwali hampers",
            "description": "Two reels about our hamper boxes.",
            "campaign_type": "paid",
            "budget_min_paise": 500_000,
            "budget_max_paise": 900_000,
            "cities": ["Chennai"],
            "niches": ["food"],
            "deliverables": "2 Instagram reels",
        },
        headers=brand.headers,
    ).json()["id"]
    client.post(f"{CAMPAIGNS_URL}/{campaign_id}/publish", headers=brand.headers)
    application_id = client.post(
        f"{CAMPAIGNS_URL}/{campaign_id}/applications",
        json={"pitch": PITCH},
        headers=creator.headers,
    ).json()["id"]
    client.post(f"/api/v1/applications/{application_id}/shortlist", headers=brand.headers)
    client.post(f"/api/v1/applications/{application_id}/accept", headers=brand.headers)
    memo = client.post(
        f"{MEMOS_URL}/for-application/{application_id}",
        json={"deliverables": "2 reels.", "fee_amount_paise": 600_000},
        headers=brand.headers,
    )
    assert memo.status_code == 201, memo.text
    return str(memo.json()["id"])


def ask(client, user: User):
    return client.post(URL, headers=with_code(client, user.headers, "delete_account"))


def state(client, user: User) -> dict:
    response = client.get(URL, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def notices(db, user: User, kind: str) -> int:
    return len(
        db.scalars(
            select(Notification.id).where(
                Notification.account_id == user.account_id,
                Notification.notification_type == kind,
            )
        ).all()
    )


# --- reading where it stands ----------------------------------------------


def test_nothing_asked_for_reads_as_none_with_what_would_be_kept(client, creator):
    body = state(client, creator)

    assert body["status"] == "none"
    assert body["requested_at"] is None
    assert body["takes_effect_at"] is None
    assert body["unfinished_deals"] == 0
    assert body["unfinished_deal_ids"] == []
    assert [kind["kind"] for kind in body["kept"]] == [kind.kind for kind in KEPT]
    # No period is guessed (constraint 6): every kind is kept as the law may require.
    assert {kind["kept_for_days"] for kind in body["kept"]} == {None}
    assert all(kind["what"] for kind in body["kept"])


def test_reading_needs_a_login(client):
    assert client.get(URL).status_code == 401


def test_an_unfinished_deal_is_listed_by_its_memo(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)

    for user in (brand, creator):
        body = state(client, user)
        assert body["unfinished_deals"] == 1
        assert body["unfinished_deal_ids"] == [memo_id]


def test_a_finished_deal_holds_nothing(client, brand, creator):
    memo_id = accepted_memo(client, brand, creator)
    finish_deal(client, brand, creator, memo_id)

    assert state(client, creator)["unfinished_deals"] == 0
    assert state(client, brand)["unfinished_deals"] == 0


# --- asking -----------------------------------------------------------------


@pytest.mark.parametrize("role", ["brand", "creator"])
def test_asking_starts_30_days_and_tells_the_owner(
    client, db, clock, role, brand, creator
):
    user = brand if role == "brand" else creator

    response = ask(client, user)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "waiting"
    takes_effect_at = clock.now + timedelta(days=30)
    assert body["takes_effect_at"] == takes_effect_at.isoformat().replace("+00:00", "Z")
    assert body == state(client, user)
    assert notices(db, user, "deletion_requested") == 1
    # A notice nobody can mute: it may be the only sign someone else asked.
    assert "deletion_requested" in URGENT_TYPES


def test_asking_needs_a_code(client, creator):
    response = client.post(URL, headers=creator.headers)

    assert response.status_code == 401
    assert response.json()["code"] == "step_up_required"
    assert state(client, creator)["status"] == "none"


def test_a_wrong_code_is_refused(client, creator):
    with_code(client, creator.headers, "delete_account")  # one was sent

    response = client.post(URL, headers={**creator.headers, "Step-Up-Code": "000000"})

    assert response.status_code == 400
    assert response.json()["code"] == "step_up_code_invalid"
    assert state(client, creator)["status"] == "none"


def test_a_code_for_another_change_is_refused(client, creator):
    headers = with_code(client, creator.headers, "log_out_everywhere")

    response = client.post(URL, headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "step_up_code_invalid"


def test_asking_needs_a_login(client):
    assert client.post(URL).status_code == 401


def test_a_code_works_once(client, creator):
    headers = with_code(client, creator.headers, "delete_account")
    assert client.post(URL, headers=headers).status_code == 202
    client.delete(URL, headers=creator.headers)

    again = client.post(URL, headers=headers)

    assert again.status_code == 400
    assert again.json()["code"] == "step_up_code_invalid"


def test_asking_twice_is_refused_before_a_code_is_sent(client, db, creator):
    assert ask(client, creator).status_code == 202
    codes_before = len(db.scalars(select(StepUpChallenge.id)).all())

    response = client.post(
        STEP_UP_URL, json={"action": "delete_account"}, headers=creator.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "deletion_already_requested"
    assert len(db.scalars(select(StepUpChallenge.id)).all()) == codes_before


def test_asking_with_a_code_while_one_waits_is_refused(client, db, creator):
    headers = with_code(client, creator.headers, "delete_account")
    assert ask(client, creator).status_code == 202

    response = client.post(URL, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "deletion_already_requested"
    assert notices(db, creator, "deletion_requested") == 1


@pytest.mark.parametrize("side", ["brand", "creator"])
def test_an_unfinished_deal_refuses_it_before_a_code_is_sent(
    client, db, brand, creator, side
):
    accepted_memo(client, brand, creator)
    user = brand if side == "brand" else creator

    response = client.post(
        STEP_UP_URL, json={"action": "delete_account"}, headers=user.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "deletion_held_by_deals"
    assert "1 of your deals" in response.json()["detail"]
    assert (
        db.scalars(
            select(StepUpChallenge.id).where(
                StepUpChallenge.account_id == user.account_id
            )
        ).all()
        == []
    )


def test_a_deal_begun_after_the_code_still_refuses_it(client, brand, creator):
    headers = with_code(client, creator.headers, "delete_account")
    accepted_memo(client, brand, creator)

    response = client.post(URL, headers=headers)

    assert response.status_code == 409
    assert response.json()["code"] == "deletion_held_by_deals"
    assert state(client, creator)["status"] == "none"


def test_a_brands_draft_memo_holds_it(client, brand, creator):
    # Someone is waiting on a draft: the brand sends or cancels it first.
    draft_memo(client, brand, creator)

    response = client.post(
        STEP_UP_URL, json={"action": "delete_account"}, headers=brand.headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "deletion_held_by_deals"


def test_an_admin_cannot_delete_their_account_here(client, db, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    response = client.post(URL, headers={**admin.headers, "Step-Up-Code": "123456"})

    assert response.status_code == 403
    assert response.json()["code"] == "role_not_allowed"


def test_an_admin_is_refused_a_code_for_it(client, db, clock):
    admin = User(create_account(db, "admin").id, "admin", clock)
    db.commit()

    response = client.post(
        STEP_UP_URL, json={"action": "delete_account"}, headers=admin.headers
    )

    assert response.status_code == 403


def test_a_retry_with_the_same_key_gets_the_first_answer(client, creator):
    headers = {
        **with_code(client, creator.headers, "delete_account"),
        "Idempotency-Key": "delete-retry-1",
    }

    first = client.post(URL, headers=headers)
    second = client.post(URL, headers=headers)

    assert first.status_code == second.status_code == 202
    assert second.json() == first.json()


def test_asking_is_rate_limited(client, creator):
    allowed = int(REQUEST_LIMIT.split(" per ")[0])
    for _ in range(allowed):
        assert client.post(URL, headers=creator.headers).status_code == 401

    response = client.post(URL, headers=creator.headers)

    assert response.status_code == 429
    assert "Retry-After" in response.headers


# --- while it waits -------------------------------------------------------------


def test_the_account_works_as_before_while_it_waits(client, creator, clock):
    assert ask(client, creator).status_code == 202
    clock.advance(timedelta(days=29))

    assert client.get("/api/v1/auth/me", headers=creator.headers).status_code == 200
    assert state(client, creator)["status"] == "waiting"


def test_a_waiting_deletion_leads_the_attention_list(client, creator, clock):
    assert ask(client, creator).status_code == 202

    attention = client.get(ATTENTION_URL, headers=creator.headers).json()

    first = attention["items"][0]
    assert first["kind"] == "deletion_pending"
    assert first["due_on"] == india_date(clock.now + timedelta(days=30)).isoformat()
    assert attention["counts"]["deletion_pending"] == 1


def test_the_attention_item_goes_once_cancelled(client, creator):
    assert ask(client, creator).status_code == 202
    assert client.delete(URL, headers=creator.headers).status_code == 204

    attention = client.get(ATTENTION_URL, headers=creator.headers).json()

    assert attention["counts"]["deletion_pending"] == 0


def test_a_held_deletion_still_leads_the_attention_list(
    client, db, brand, creator, clock
):
    assert ask(client, creator).status_code == 202
    accepted_memo(client, brand, creator)
    clock.advance(timedelta(days=31))

    body = state(client, creator)
    attention = client.get(ATTENTION_URL, headers=creator.headers).json()

    assert body["status"] == "held"
    assert body["unfinished_deals"] == 1
    assert attention["counts"]["deletion_pending"] == 1


def test_the_export_says_when_it_was_asked_and_when_it_takes_effect(
    client, db, creator, clock
):
    from app.modules.auth.models.account import Account
    from app.modules.me import export_service

    assert ask(client, creator).status_code == 202
    account = db.get_one(Account, creator.account_id)

    exported = export_service.build_export(db, account, clock.now)

    [row] = exported["data"]["account"]
    assert row["deletion_requested_at"] is not None
    assert row["deletion_takes_effect_at"] is not None
    assert "deleted_at" not in row


# --- cancelling -----------------------------------------------------------------


def test_cancelling_needs_no_code_and_tells_the_owner(client, db, creator):
    assert ask(client, creator).status_code == 202

    response = client.delete(URL, headers=creator.headers)

    assert response.status_code == 204
    assert state(client, creator)["status"] == "none"
    assert notices(db, creator, "deletion_cancelled") == 1
    assert "deletion_cancelled" in URGENT_TYPES


def test_cancelling_with_nothing_waiting_is_fine_and_says_nothing(client, db, creator):
    response = client.delete(URL, headers=creator.headers)

    assert response.status_code == 204
    assert notices(db, creator, "deletion_cancelled") == 0


def test_cancelling_needs_a_login(client):
    assert client.delete(URL).status_code == 401


def test_it_can_be_asked_again_after_cancelling(client, creator, clock):
    assert ask(client, creator).status_code == 202
    assert client.delete(URL, headers=creator.headers).status_code == 204
    clock.advance(timedelta(days=3))

    response = ask(client, creator)

    assert response.status_code == 202
    assert response.json()["requested_at"] == clock.now.isoformat().replace("+00:00", "Z")


def test_a_held_deletion_can_be_cancelled(client, brand, creator, clock):
    assert ask(client, creator).status_code == 202
    accepted_memo(client, brand, creator)
    clock.advance(timedelta(days=31))

    assert client.delete(URL, headers=creator.headers).status_code == 204
    assert state(client, creator)["status"] == "none"


def test_the_service_never_cancels_a_deletion_already_done(db, creator, clock):
    from app.modules.auth.models.account import Account

    account = db.get_one(Account, creator.account_id)
    account.deletion_requested_at = clock.now - timedelta(days=31)
    account.deletion_takes_effect_at = clock.now - timedelta(days=1)
    db.commit()
    assert service.erase(db, account.id, clock.now) == "erased"

    service.cancel(db, account, clock.now)

    db.refresh(account)
    assert account.deleted_at is not None
    assert account.deletion_requested_at is not None


# --- what holds it, counted fairly -------------------------------------------------


def test_reading_costs_the_same_queries_for_one_deal_or_three(client, db, clock):
    from tests.query_counts import queries_for

    one, three = (brand_user(db, clock), brand_user(db, clock))
    db.commit()
    accepted_memo(client, one, creator_user(db, clock))
    for _ in range(3):
        accepted_memo(client, three, creator_user(db, clock))

    assert queries_for(client, URL, one.headers) == queries_for(
        client, URL, three.headers
    )
    assert state(client, three)["unfinished_deals"] == 3


def test_only_the_persons_own_deals_hold_it(client, db, clock, brand, creator):
    """Two brands and two creators, so a filter missing its join cannot pass by luck."""
    other_brand, other_creator = brand_user(db, clock), creator_user(db, clock)
    db.commit()
    accepted_memo(client, other_brand, other_creator)
    mine = accepted_memo(client, brand, other_creator)

    assert state(client, brand)["unfinished_deal_ids"] == [mine]
    assert state(client, creator)["unfinished_deals"] == 0
    assert state(client, other_creator)["unfinished_deals"] == 2


@pytest.mark.parametrize("ending", ["decline", "cancel"])
def test_a_declined_or_cancelled_deal_holds_nothing(client, brand, creator, ending):
    memo_id = draft_memo(client, brand, creator)
    client.patch(
        f"{MEMOS_URL}/{memo_id}",
        json={"content_due_on": "2026-12-31"},
        headers=brand.headers,
    )
    sent = client.post(f"{MEMOS_URL}/{memo_id}/send", headers=brand.headers)
    assert sent.status_code == 200, sent.text
    actor = creator if ending == "decline" else brand
    ended = client.post(
        f"{MEMOS_URL}/{memo_id}/{ending}",
        json={"reason": "other"} if ending == "cancel" else None,
        headers=actor.headers,
    )
    assert ended.status_code == 200, ended.text

    assert state(client, brand)["unfinished_deals"] == 0
    assert state(client, creator)["unfinished_deals"] == 0
