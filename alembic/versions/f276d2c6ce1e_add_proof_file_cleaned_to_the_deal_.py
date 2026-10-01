"""add proof_file_cleaned to the deal record (D-065)

When a proof file is cleaned of location and hidden data, the brand sees the
clean copy and the original is deleted. This kind seals the clean copy's
fingerprint, so every file a brand sees stays provable (approved by Adhi in
session, 1 October 2026).

Alembic does not compare CHECK constraints, so this is written by hand. The
widened check is added NOT VALID and validated after the transaction
commits: validating inside it would scan deal_record_entry while blocking
writes (Squawk, D-050). The old check is dropped only once its replacement
is in place, so no moment admits an unknown kind.

The downgrade refuses while any entry of the new kind exists: the record is
append-only, so those entries can never be removed, and narrowing the check
under them would fail halfway.

Revision ID: f276d2c6ce1e
Revises: c45a9831e0c9
Create Date: 2026-10-01 02:49:08.832389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f276d2c6ce1e'
down_revision: Union[str, None] = 'c45a9831e0c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KINDS = (
    "record_started",
    "memo_sent",
    "memo_change_requested",
    "memo_accepted",
    "memo_declined",
    "memo_cancelled",
    "proof_submitted",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_opened",
    "payment_marked_paid",
    "payment_confirmed",
    "dispute_opened",
    "dispute_entry_added",
    "dispute_closed",
)
NEW_KINDS = OLD_KINDS[:10] + ("proof_file_cleaned",) + OLD_KINDS[10:]

NAME = "ck_deal_record_entry_kind_allowed"
STAGING = "ck_deal_record_entry_kind_allowed_next"


def _in(kinds: tuple[str, ...]) -> str:
    return "kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE deal_record_entry ADD CONSTRAINT {STAGING} "
        f"CHECK ({_in(NEW_KINDS)}) NOT VALID"
    )
    op.execute(f"ALTER TABLE deal_record_entry DROP CONSTRAINT {NAME}")
    op.execute(f"ALTER TABLE deal_record_entry RENAME CONSTRAINT {STAGING} TO {NAME}")
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE deal_record_entry VALIDATE CONSTRAINT {NAME}")


def downgrade() -> None:
    cleaned = op.get_bind().execute(
        sa.text("SELECT count(*) FROM deal_record_entry WHERE kind = 'proof_file_cleaned'")
    ).scalar_one()
    if cleaned:
        raise RuntimeError(
            f"{cleaned} proof_file_cleaned record entries exist. The record is "
            "append-only, so they cannot be removed; this downgrade will not run."
        )
    op.execute(
        f"ALTER TABLE deal_record_entry ADD CONSTRAINT {STAGING} "
        f"CHECK ({_in(OLD_KINDS)}) NOT VALID"
    )
    op.execute(f"ALTER TABLE deal_record_entry DROP CONSTRAINT {NAME}")
    op.execute(f"ALTER TABLE deal_record_entry RENAME CONSTRAINT {STAGING} TO {NAME}")
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE deal_record_entry VALIDATE CONSTRAINT {NAME}")
