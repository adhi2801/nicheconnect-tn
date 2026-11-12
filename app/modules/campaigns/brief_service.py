"""Campaign briefs drafted from a brand's own words (item 40, D-156).

A brand (its owner, an admin or a campaign manager) asks with a few
sentences; the request stores them and returns at once. A job drafts each
waiting request with `brief_drafter` and stores the fields, or why it could
not. The brand reads the draft, edits it and creates the campaign itself:
nothing here creates or changes a campaign.

- **Never on the request path** (CLAUDE.md section 3): the request writes a
  row; the job calls the model.
- **No network call inside a transaction** (database.md section 7): a
  draft is claimed with a Postgres advisory lock on a connection of its own,
  the model is called with no transaction open, and the result is written in
  one short transaction, only if the draft still waits.
- **A ceiling on the bill**: drafts stop at `brief_drafting_daily_limit` a
  day, across every brand; at most three wait per brand at once.
- A failed call is tried again up to three times; a refusal or an answer
  that does not fit is final.
- Drafts are kept a week, then deleted by the job.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deadline import Deadline
from app.core.export import MAX_ROWS_PER_SECTION, ExportedSection, allow, build_section
from app.core.job_runs import within_budget
from app.modules.auth.brand_access import BrandAccess
from app.modules.auth.models.account import Account
from app.modules.campaigns.brief_drafter import BriefDrafter, Drafted
from app.modules.campaigns.brief_models import BRIEF_KEPT_DAYS, CampaignBriefDraft
from app.modules.campaigns.exceptions import BriefDraftNotFound, BriefDraftsWaiting

logger = logging.getLogger(__name__)

EXPORTED_TABLES = frozenset({"campaign_brief_draft"})
EXPORT_FIELDS = allow(
    "id", "idea", "status", "draft", "failure", "drafted_at", "created_at"
)

MAX_WAITING_PER_BRAND = 3
MAX_ATTEMPTS = 3
PER_RUN = 10
# Its own namespace, so a draft's advisory lock never meets a proof file's.
LOCK_NAMESPACE = 40
RETRYABLE = frozenset({"api_error", "max_tokens"})


@dataclass(frozen=True)
class DraftRun:
    drafted: int
    failed: int
    skipped: int
    stopped_at_limit: bool
    deleted: int


def ask(
    db: Session, access: BrandAccess, account: Account, idea: str, now: datetime
) -> CampaignBriefDraft:
    """Store a brand's words for the job to draft. Commits.

    Raises BriefDraftsWaiting when three of the brand's drafts still wait.
    Counted under the brand's lock, so two asks at once cannot pass it.
    """
    from app.modules.auth.models.brand import Brand

    db.scalars(
        select(Brand.id).where(Brand.id == access.brand.id).with_for_update()
    ).one()
    waiting = db.scalar(
        select(func.count()).where(
            CampaignBriefDraft.brand_id == access.brand.id,
            CampaignBriefDraft.status == "waiting",
        )
    )
    if (waiting or 0) >= MAX_WAITING_PER_BRAND:
        db.rollback()
        raise BriefDraftsWaiting()
    draft = CampaignBriefDraft(
        brand_id=access.brand.id,
        requested_by_account_id=account.id,
        idea=idea,
        status="waiting",
        created_at=now,
        updated_at=now,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def get(
    db: Session, access: BrandAccess, draft_id: uuid.UUID, now: datetime
) -> CampaignBriefDraft:
    """One of the brand's drafts, still within its week. Raises BriefDraftNotFound."""
    found = db.scalars(
        select(CampaignBriefDraft).where(
            CampaignBriefDraft.id == draft_id,
            CampaignBriefDraft.brand_id == access.brand.id,
            CampaignBriefDraft.created_at > now - timedelta(days=BRIEF_KEPT_DAYS),
        )
    ).first()
    if found is None:
        raise BriefDraftNotFound()
    return found


def drafted_in_last_day(db: Session, now: datetime) -> int:
    count = db.scalar(
        select(func.count()).where(
            CampaignBriefDraft.drafted_at > now - timedelta(days=1)
        )
    )
    return count or 0


def save(db: Session, draft_id: uuid.UUID, drafted: Drafted, now: datetime) -> str:
    """Write what one call produced, only if the draft still waits. Commits."""
    found = db.scalars(
        select(CampaignBriefDraft)
        .where(CampaignBriefDraft.id == draft_id, CampaignBriefDraft.status == "waiting")
        .with_for_update()
    ).first()
    if found is None:
        db.rollback()
        return "skipped"
    found.attempts += 1
    found.model = drafted.model
    found.input_tokens = drafted.input_tokens
    found.output_tokens = drafted.output_tokens
    found.drafted_at = now
    found.updated_at = now
    if drafted.fields is not None:
        found.status = "ready"
        found.draft = drafted.fields.model_dump(mode="json")
        outcome = "drafted"
    elif drafted.failure in RETRYABLE and found.attempts < MAX_ATTEMPTS:
        outcome = "failed"
    else:
        found.status = "failed"
        found.failure = drafted.failure or "api_error"
        outcome = "failed"
    db.commit()
    return outcome


def draft_one(
    db: Session, drafter: BriefDrafter, draft_id: uuid.UUID, now: datetime
) -> str:
    """Claim, draft and save one. Returns what happened."""
    lock_key = func.hashtext(str(draft_id))
    with db.get_bind().engine.connect() as lock:
        claimed = lock.scalar(select(func.pg_try_advisory_lock(LOCK_NAMESPACE, lock_key)))
        lock.commit()
        if not claimed:
            return "skipped"
        try:
            idea = db.scalar(
                select(CampaignBriefDraft.idea).where(
                    CampaignBriefDraft.id == draft_id,
                    CampaignBriefDraft.status == "waiting",
                )
            )
            # Nothing held open while the model is asked.
            db.rollback()
            if idea is None:
                return "skipped"
            return save(db, draft_id, drafter.draft(idea), now)
        finally:
            lock.execute(select(func.pg_advisory_unlock(LOCK_NAMESPACE, lock_key)))
            lock.commit()


def run(
    db: Session,
    drafter: BriefDrafter | None,
    now: datetime,
    *,
    limit: int = PER_RUN,
    budget: Deadline | None = None,
) -> DraftRun:
    """One run of the job: delete drafts past their week, then draft the oldest waiting.

    With drafting switched off (no drafter) nothing is drafted; old drafts still go.
    Once `budget` is spent no further draft is started (item 118, D-186); the
    rest stay waiting for the next run.
    """
    deleted = delete_old(db, now)
    if drafter is None:
        return DraftRun(0, 0, 0, False, deleted)
    allowance = settings.brief_drafting_daily_limit - drafted_in_last_day(db, now)
    if allowance <= 0:
        db.rollback()
        logger.warning("brief drafting stopped: the daily limit is reached")
        return DraftRun(0, 0, 0, True, deleted)
    queue = list(
        db.scalars(
            select(CampaignBriefDraft.id)
            .where(CampaignBriefDraft.status == "waiting")
            .order_by(CampaignBriefDraft.created_at, CampaignBriefDraft.id)
            .limit(min(limit, allowance))
        ).all()
    )
    db.rollback()
    outcomes = [
        draft_one(db, drafter, draft_id, now)
        for draft_id in within_budget(queue, budget, "brief_drafts.run")
    ]
    return DraftRun(
        drafted=outcomes.count("drafted"),
        failed=outcomes.count("failed"),
        skipped=outcomes.count("skipped"),
        stopped_at_limit=False,
        deleted=deleted,
    )


def delete_old(db: Session, now: datetime) -> int:
    """Drafts past their week. Commits. Returns how many went."""
    gone = db.execute(
        delete(CampaignBriefDraft)
        .where(CampaignBriefDraft.created_at <= now - timedelta(days=BRIEF_KEPT_DAYS))
        .returning(CampaignBriefDraft.id)
    ).all()
    db.commit()
    return len(gone)


def export_for_account(db: Session, account_id: uuid.UUID) -> list[ExportedSection]:
    """The drafts this person asked for, with what they wrote."""
    rows = list(
        db.scalars(
            select(CampaignBriefDraft)
            .where(CampaignBriefDraft.requested_by_account_id == account_id)
            .order_by(CampaignBriefDraft.created_at, CampaignBriefDraft.id)
            .limit(MAX_ROWS_PER_SECTION + 1)
        ).all()
    )
    if not rows:
        return []
    return [
        build_section(
            "campaign_brief_drafts",
            table="campaign_brief_draft",
            purpose=(
                "Campaign briefs you asked us to draft from your own words, and "
                "the drafts, kept a week."
            ),
            objects=rows,
            fields=EXPORT_FIELDS,
        )
    ]


def erase_for_brand(db: Session, brand_id: uuid.UUID) -> None:
    """On deleting the brand's account (D-122): every draft of the brand. Never commits."""
    db.execute(delete(CampaignBriefDraft).where(CampaignBriefDraft.brand_id == brand_id))


def erase_for_account(db: Session, account_id: uuid.UUID) -> None:
    """On deleting a team member's account: their name leaves the brand's drafts. Never commits."""
    db.execute(
        update(CampaignBriefDraft)
        .where(CampaignBriefDraft.requested_by_account_id == account_id)
        .values(requested_by_account_id=None)
    )
