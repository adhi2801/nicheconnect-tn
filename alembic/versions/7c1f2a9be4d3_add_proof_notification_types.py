"""add proof notification types

Revision ID: 7c1f2a9be4d3
Revises: 29632d604015
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c1f2a9be4d3'
down_revision: Union[str, None] = '29632d604015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# By hand: alembic does not detect a changed CHECK, and both the drop and the
# create need op.f(), or the naming convention prefixes the name a second time.
EXISTING_TYPES = (
    "application_received",
    "application_withdrawn",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "memo_sent",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "memo_cancelled",
)
PROOF_TYPES = (
    "proof_submitted",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
)
CONSTRAINT = "ck_notification_type_allowed"


def _check(types: tuple[str, ...]) -> str:
    return f"notification_type IN {types}"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "notification", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "notification", _check(EXISTING_TYPES + PROOF_TYPES)
    )


def downgrade() -> None:
    # Rows of the new types cannot satisfy the old rule; the proof records
    # themselves keep the history, so only the notifications go.
    op.execute(f"DELETE FROM notification WHERE notification_type IN {PROOF_TYPES}")
    op.drop_constraint(op.f(CONSTRAINT), "notification", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "notification", _check(EXISTING_TYPES))
