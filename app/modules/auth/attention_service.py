"""Everything waiting on one account, gathered from every module.

Each module reports its own items (its `attention.py`); this only asks the
right ones for the account's role and puts the answers in order, the way
`export_service` gathers export sections. See app/core/attention.py.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.attention import (
    BRAND_KINDS,
    CREATOR_KINDS,
    MAX_ITEMS,
    AttentionList,
    by_urgency,
)
from app.core.clock import india_date
from app.modules.auth.models.account import Account
from app.modules.campaigns import attention as campaigns
from app.modules.campaigns.service import get_brand_for_account, get_creator_for_account
from app.modules.deal_memo import attention as deal_memos
from app.modules.disputes import attention as disputes
from app.modules.payment_status import attention as payments


def for_account(db: Session, account: Account, now: datetime) -> AttentionList:
    """What is waiting on this account now, most urgent first.

    Raises BrandProfileRequired or CreatorProfileRequired when the profile
    has not been created yet, as every other signed-in endpoint does.
    """
    today = india_date(now)
    if account.role == "brand":
        brand = get_brand_for_account(db, account.id)
        kinds = BRAND_KINDS
        found = [
            *campaigns.for_brand(db, brand.id),
            *deal_memos.for_brand(db, brand.id, now),
            *payments.for_brand(db, brand.id),
            *disputes.for_brand(db, brand.id, today),
        ]
    else:
        creator = get_creator_for_account(db, account.id)
        kinds = CREATOR_KINDS
        found = [
            *deal_memos.for_creator(db, creator.id, now),
            *payments.for_creator(db, creator.id, today),
            *disputes.for_creator(db, creator.id, today),
        ]

    ordered = by_urgency(found)
    counts = dict.fromkeys(kinds, 0)
    for item in ordered:
        counts[item.kind] += 1
    return AttentionList(
        role=account.role,
        as_of=today,
        counts=counts,
        items=ordered[:MAX_ITEMS],
        total=len(ordered),
        truncated=len(ordered) > MAX_ITEMS,
    )
