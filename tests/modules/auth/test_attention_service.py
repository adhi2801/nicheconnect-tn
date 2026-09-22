"""How the attention list is put in order and cut to length.

The end-to-end tests (tests/modules/test_attention_api.py) prove each kind
appears and disappears. These prove the rules that are awkward to reach
through real deals: ties on the same day, and the cap of 50 items.
"""

import uuid
from datetime import date

from app.core.attention import MAX_ITEMS, AttentionItem, by_urgency
from app.modules.auth import attention_service
from app.modules.auth.models.account import Account
from tests.factories import FIXED_NOW, build_brand

CAMPAIGN = uuid.uuid4()


def item(kind: str, due_on: date | None, **ids) -> AttentionItem:
    return AttentionItem(
        kind=kind, due_on=due_on, campaign_id=CAMPAIGN, campaign_title="Pongal", **ids
    )


def test_overdue_comes_before_soon_and_undated_comes_last():
    later = item("review_proof", date(2026, 9, 30))
    undated = item("review_applications", None)
    overdue = item("pay_creator", date(2026, 9, 1))

    assert by_urgency([later, undated, overdue]) == [overdue, later, undated]


def test_on_the_same_day_money_and_disputes_come_first():
    day = date(2026, 9, 24)
    review = item("review_proof", day, proof_id=uuid.uuid4())
    pay = item("pay_creator", day, memo_id=uuid.uuid4())
    dispute = item("respond_to_dispute", day, memo_id=uuid.uuid4())

    assert [i.kind for i in by_urgency([review, pay, dispute])] == [
        "respond_to_dispute",
        "pay_creator",
        "review_proof",
    ]


def test_the_same_records_always_give_the_same_order():
    day = date(2026, 9, 24)
    payments = [item("pay_creator", day, memo_id=uuid.uuid4()) for _ in range(5)]

    assert by_urgency(payments) == by_urgency(list(reversed(payments)))


def test_the_list_is_cut_at_the_cap_and_the_counts_still_cover_everything(
    db, monkeypatch
):
    brand = build_brand(db)
    db.add(brand)
    db.flush()
    account = db.get(Account, brand.account_id)
    many = [
        item("pay_creator", date(2026, 9, 1 + i % 28), memo_id=uuid.uuid4())
        for i in range(MAX_ITEMS + 10)
    ]
    monkeypatch.setattr(attention_service.campaigns, "for_brand", lambda *a: [])
    monkeypatch.setattr(attention_service.deal_memos, "for_brand", lambda *a: [])
    monkeypatch.setattr(attention_service.payments, "for_brand", lambda *a: many)
    monkeypatch.setattr(attention_service.disputes, "for_brand", lambda *a: [])

    result = attention_service.for_account(db, account, FIXED_NOW)

    assert len(result.items) == MAX_ITEMS
    assert result.total == MAX_ITEMS + 10
    assert result.truncated is True
    assert result.counts["pay_creator"] == MAX_ITEMS + 10
    # The ones kept are the most urgent ones.
    assert result.items == by_urgency(many)[:MAX_ITEMS]
