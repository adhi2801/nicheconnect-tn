"""What of a brand's domain is waiting on the brand (item 74, D-106; app/core/attention.py).

How a brand learns a check failed or a verification lapsed: worked out on
read from the claim as it stands, so each item disappears the moment the
record is found again or the claim is withdrawn.

- `fix_domain_record`: a check did not find the record, on a pending claim
  (due the day its token expires) or on a verified one (due the day it would
  lapse, after MAX_ABSENT_CHECKS daily checks in a row);
- `domain_lapsed`: the verification lapsed; creators no longer see it;
- `domain_claim_expired`: the token expired before the record was found.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.attention import AttentionItem
from app.core.clock import india_date
from app.modules.profiles.brand_domain_models import MAX_ABSENT_CHECKS, BrandDomain
from app.modules.profiles.brand_domains import RECHECK_AFTER


def for_brand(db: Session, brand_id: uuid.UUID, now: datetime) -> list[AttentionItem]:
    row = db.scalars(select(BrandDomain).where(BrandDomain.brand_id == brand_id)).first()
    if row is None:
        return []
    item = _item(row, now)
    return [] if item is None else [item]


def _item(row: BrandDomain, now: datetime) -> AttentionItem | None:
    def make(kind: str, due: datetime | None) -> AttentionItem:
        return AttentionItem(
            kind=kind,
            due_on=None if due is None else india_date(due),
            campaign_id=None,
            campaign_title=None,
            domain=row.domain,
        )

    if row.status == "lapsed":
        return make("domain_lapsed", None)
    if row.status == "pending":
        if now >= row.token_expires_at:
            return make("domain_claim_expired", None)
        if row.last_result in ("absent", "unknown", "taken"):
            return make("fix_domain_record", row.token_expires_at)
        return None
    if row.consecutive_absent > 0 and row.last_checked_at is not None:
        checks_left = MAX_ABSENT_CHECKS - row.consecutive_absent
        return make(
            "fix_domain_record", row.last_checked_at + checks_left * RECHECK_AFTER
        )
    return None
