"""add memo notification types

Revision ID: 304a0b04912a
Revises: a41ce4028df6
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '304a0b04912a'
down_revision: Union[str, None] = 'a41ce4028df6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Written by hand: autogenerate does not detect a changed CHECK constraint.
APPLICATION_TYPES = (
    "application_received",
    "application_withdrawn",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
)
MEMO_TYPES = (
    "memo_sent",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "memo_cancelled",
)
CONSTRAINT = "ck_notification_type_allowed"


def _check(types: tuple[str, ...]) -> str:
    return f"notification_type IN {types}"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "notification", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT), "notification", _check(APPLICATION_TYPES + MEMO_TYPES)
    )


def downgrade() -> None:
    # Rows of the new types cannot satisfy the old rule, so they go with it.
    # They are notifications, not records of what happened: the deal memo
    # itself keeps the history.
    op.execute(
        "DELETE FROM notification WHERE notification_type IN "
        f"{MEMO_TYPES}"
    )
    op.drop_constraint(op.f(CONSTRAINT), "notification", type_="check")
    op.create_check_constraint(op.f(CONSTRAINT), "notification", _check(APPLICATION_TYPES))
