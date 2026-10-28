"""add memo declined_at and change_request_message, application first_answered_at (items 24, 25, 28)

From the website wireframes' backend requests (docs/BACKEND_COMPLETE.md
section 3.7), approved by Adhi on 12 October 2026 as one migration (D-089):

- deal_memo.declined_at: the deal pass shows when each step happened, and a
  decline had no date.
- deal_memo.change_request_message: the memo editor's banner shows what the
  creator asked to change; it reached the brand only as a notification.
- application.first_answered_at: when the brand first shortlisted, accepted
  or rejected an application, so how fast brands reply can be measured
  (D-077 could not).

All three are nullable with no default. Adding them rewrites nothing and
locks each table only for an instant. No foreign key, so no ON DELETE.

Data impact: existing rows keep NULL. Nothing is backfilled, because a date
or a message that was never recorded cannot be honestly invented: a decline
before today has no declined_at, and an answer before today no
first_answered_at.

Three CHECKs, so the database holds each rule whatever the code does:
- a decline date only on a declined memo;
- a change request message only on a memo that was sent back, 5 to 1,000
  characters once trimmed;
- a first answer only on an application someone applied for (never an
  invitation), and never while it still waits.
Alembic does not compare CHECKs, so they are written by hand: added
NOT VALID, then validated after the transaction commits, so the existing
rows are scanned without blocking writes (Squawk, D-050).

The downgrade refuses while any of the three holds a value: once dropped,
those dates and words can never be recovered (database.md section 6).
Clearing them first is then a deliberate act, not a side effect of a
rollback.

Revision ID: 429278d02ad2
Revises: e591b300cca7
Create Date: 2026-10-12 15:55:29.719676

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '429278d02ad2'
down_revision: Union[str, None] = 'e591b300cca7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "deal_memo",
        "ck_deal_memo_declined_at_only_if_declined",
        "declined_at IS NULL OR status = 'declined'",
    ),
    (
        "deal_memo",
        "ck_deal_memo_change_request_message_needs_request",
        "change_request_message IS NULL OR (revision_count > 0"
        " AND char_length(btrim(change_request_message)) BETWEEN 5 AND 1000)",
    ),
    (
        "application",
        "ck_application_first_answered_at_only_if_answered",
        "first_answered_at IS NULL OR (origin = 'applied' AND status <> 'submitted')",
    ),
)


def upgrade() -> None:
    op.add_column('application', sa.Column('first_answered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deal_memo', sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('deal_memo', sa.Column('change_request_message', sa.Text(), nullable=True))
    for table, name, rule in CHECKS:
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({rule}) NOT VALID")
    with op.get_context().autocommit_block():
        for table, name, _ in CHECKS:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def downgrade() -> None:
    kept = op.get_bind().execute(
        sa.text(
            "SELECT (SELECT count(*) FROM deal_memo"
            " WHERE declined_at IS NOT NULL OR change_request_message IS NOT NULL)"
            " + (SELECT count(*) FROM application WHERE first_answered_at IS NOT NULL)"
        )
    ).scalar_one()
    if kept:
        raise RuntimeError(
            f"{kept} rows hold a decline date, a change request message or a first "
            "answer, which cannot be recovered once dropped. Clear those columns "
            "deliberately first if losing them is intended."
        )
    for table, name, _ in CHECKS:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.drop_column('deal_memo', 'change_request_message')
    op.drop_column('deal_memo', 'declined_at')
    op.drop_column('application', 'first_answered_at')
