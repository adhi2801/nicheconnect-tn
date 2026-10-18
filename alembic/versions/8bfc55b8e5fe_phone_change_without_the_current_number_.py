"""phone change without the current number: a lost number's 7-day wait (D-110)

Someone whose current number is already gone had no way to move their
account: the change needed a code from that number. Approved by Adhi on 18
October 2026 (D-110): from a login at least 30 days old, with a code from the
new number, a change may be asked for without the current number's; it waits
7 days, and any login with the current number meanwhile cancels it. Then "One
new column" to how the table records it. This migration:

- adds `account_phone_change.without_current_number`, false unless the change
  was asked for that way. A constant default, so adding it rewrites nothing;
- replaces the wait's rule: `takes_effect_at` is exactly 72 hours after
  `requested_at`, or exactly 7 days when `without_current_number`. The new
  check is added NOT VALID beside the old, the old dropped, and the new one
  validated after the transaction commits, so writes are never blocked
  (database.md section 6, Squawk).

Data impact: none; every existing row is a 72-hour change and stays valid.

Downgrade: refuses while any change made without the current number waits,
since dropping the column would turn its 7 days into a broken 72-hour row.
Otherwise it restores the 72-hour rule and drops the column.

Revision ID: 8bfc55b8e5fe
Revises: d18c285488f0
Create Date: 2026-10-18 21:02:11.447120

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8bfc55b8e5fe"
down_revision: Union[str, None] = "d18c285488f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_CHECK = "ck_account_phone_change_takes_effect_three_days_after_request"
NEW_CHECK = "ck_account_phone_change_takes_effect_after_its_wait"
OLD_RULE = "takes_effect_at = requested_at + interval '72 hours'"
NEW_RULE = (
    "takes_effect_at = requested_at + CASE WHEN without_current_number "
    "THEN interval '7 days' ELSE interval '72 hours' END"
)


def _swap(drop: str, add: str, rule: str) -> None:
    """Add `add` NOT VALID, drop `drop`, then validate after the transaction."""
    op.execute(
        f"ALTER TABLE account_phone_change ADD CONSTRAINT {add} CHECK ({rule}) NOT VALID"
    )
    op.execute(f"ALTER TABLE account_phone_change DROP CONSTRAINT {drop}")
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE account_phone_change VALIDATE CONSTRAINT {add}")


def upgrade() -> None:
    op.add_column(
        "account_phone_change",
        sa.Column(
            "without_current_number",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    _swap(OLD_CHECK, NEW_CHECK, NEW_RULE)


def downgrade() -> None:
    waiting = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM account_phone_change WHERE without_current_number"
            )
        )
        .scalar_one()
    )
    if waiting:
        raise RuntimeError(
            f"{waiting} accounts are waiting to move to a new phone number without "
            "a code from their current one, which they say is lost. Dropping the "
            "column would leave each a broken 72-hour change; remove them "
            "deliberately, as the owner, if that is really intended."
        )
    _swap(NEW_CHECK, OLD_CHECK, OLD_RULE)
    op.drop_column("account_phone_change", "without_current_number")
