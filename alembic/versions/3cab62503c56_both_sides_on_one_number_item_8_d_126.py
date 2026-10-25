"""both sides on one number (item 8, D-126)

Approved by Adhi on 25 October 2026 (D-126, option B): a phone number may
hold a brand account and a creator account of one person, each exactly as
before. This migration replaces `uq_account_phone` (one account a number)
with `uq_account_phone_role` (one account a role a number):

- the new unique index is built CONCURRENTLY, outside the transaction, so
  logins are never blocked while it builds, then adopted as the constraint;
- the old constraint is dropped after, so the number is never unguarded.

Phone first in the index, so every lookup by number still uses it. NULL
phones (deleted accounts, D-122) never collide, as before.

Data impact: none; every existing number holds one account.

Downgrade: refuses while any number holds two accounts, since the old rule
could not hold and one of them would have to go; otherwise it restores
`uq_account_phone` the same way and drops the new rule.

Revision ID: 3cab62503c56
Revises: 8b6662af4839
Create Date: 2026-10-25 23:02:32.621630

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3cab62503c56"
down_revision: Union[str, None] = "8b6662af4839"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "uq_account_phone"
NEW = "uq_account_phone_role"


def _adopt(name: str, columns: str) -> None:
    """Build a unique index without blocking writes, then make it the constraint."""
    with op.get_context().autocommit_block():
        op.execute(f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {name} ON account ({columns})")
        op.execute(f"ALTER TABLE account ADD CONSTRAINT {name} UNIQUE USING INDEX {name}")


def upgrade() -> None:
    _adopt(NEW, "phone, role")
    # Raw SQL, by the exact name: op.drop_constraint would add the naming
    # convention's prefix a second time.
    op.execute(f"ALTER TABLE account DROP CONSTRAINT {OLD}")


def downgrade() -> None:
    shared = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM (SELECT phone FROM account WHERE phone IS NOT NULL"
                " GROUP BY phone HAVING count(*) > 1) AS shared"
            )
        )
        .scalar_one()
    )
    if shared:
        raise RuntimeError(
            f"{shared} phone numbers hold both a brand and a creator account. One "
            "account a number cannot hold while they do, and one of each pair "
            "would have to be removed; do that deliberately, as the owner, if it "
            "is really intended."
        )
    _adopt(OLD, "phone")
    op.execute(f"ALTER TABLE account DROP CONSTRAINT {NEW}")
