"""who asked for a waiting change (D-176)

D-176 keeps an owner's login alive past its 30 days (D-174) while a phone
change or the account's deletion waits, so the owner can always cancel a SIM
swapper's request from a session they already have. The independent review
of 8 November found that the hold also kept alive the login that asked: a
thief holding a stolen session could ask, and ask again before each wait
ended, and their session never ended. So each request now records the
login that made it, by its session family, and that login is never held:

- `account.deletion_requested_by_session`, set with `deletion_requested_at`
  and cleared with it (`ck_account_deletion_asker_only_with_a_request`);
- `account_phone_change.requested_by_session`, replaced with the row when
  a change is asked for again.

Neither is a foreign key: a session family is many `auth_session` rows, and
no one row is it. NULL means the token that asked named no session (signed
before D-114), or, on `account`, that no deletion is asked for.

The new check on `account` is added NOT VALID and validated after the
transaction, so it never holds a lock on the table while it scans
(database.md section 6). Both columns are nullable with no default, which
PostgreSQL adds without rewriting the table.

Data impact: none. Requests already waiting keep NULL, which holds every
login that was alive when they were made, as D-176 did before this.

Downgrade: drops the check and both columns. Nothing that cannot be
recovered is lost: without them, D-176's hold reverts to holding every login
alive at the request, the asker's included, the weakness this closes.

Revision ID: 578a45512fe0
Revises: e65f3516f952
Create Date: 2026-11-11 13:45:24.044959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '578a45512fe0'
down_revision: Union[str, None] = 'e65f3516f952'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ASKER_CHECK = "ck_account_deletion_asker_only_with_a_request"


def upgrade() -> None:
    op.add_column(
        "account",
        sa.Column(
            "deletion_requested_by_session", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "account_phone_change",
        sa.Column("requested_by_session", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        f"ALTER TABLE account ADD CONSTRAINT {ASKER_CHECK} "
        "CHECK (deletion_requested_by_session IS NULL OR deletion_requested_at IS NOT NULL) "
        "NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE account VALIDATE CONSTRAINT {ASKER_CHECK}")


def downgrade() -> None:
    op.execute(f"ALTER TABLE account DROP CONSTRAINT {ASKER_CHECK}")
    op.drop_column("account_phone_change", "requested_by_session")
    op.drop_column("account", "deletion_requested_by_session")
