"""index the four foreign keys without a usable index (item 98)

Reading the migrated schema on 14 October 2026 found three foreign keys with
no index starting with their column (docs/standards/database.md gap 2,
approved by Adhi the same day, D-100):

- notification.campaign_id and notification.application_id, both
  ON DELETE CASCADE: deleting a draft campaign or an application scanned
  the whole notification table to find the rows to remove.
- admin_action.admin_account_id, ON DELETE RESTRICT: deleting an account
  scanned the whole admin log to check none pointed at it.

A fourth was found the same day, once the schema test stopped counting a
partial index that leaves out more than NULLs: report.reporter_account_id
(ON DELETE CASCADE) had only the index of open reports, which cannot find a
closed one. Its new index is (reporter_account_id, created_at), which also
serves a reporter's own list of reports, newest first (item 102).

The two notification indexes are partial (WHERE ... IS NOT NULL): many
notifications carry no campaign or application, and a lookup by one value
never needs the empty rows. PostgreSQL uses a partial index for an equality
on the column, because the equality implies the column is not NULL.

Each is built CONCURRENTLY, outside the migration's transaction, so writes
to these tables carry on while it builds (Squawk, D-050). IF NOT EXISTS and
IF EXISTS make a rerun safe: a concurrent build that fails leaves its index
behind, as 608541cc4a4e also allows for. No data changes;
the downgrade drops the indexes, CONCURRENTLY too, and loses nothing.

Revision ID: 1a04f9d7e1fe
Revises: bf0081ce7ced
Create Date: 2026-10-14 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a04f9d7e1fe'
down_revision: Union[str, None] = 'bf0081ce7ced'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES: tuple[tuple[str, str, str, str | None], ...] = (
    ("ix_notification_campaign_id", "notification", "campaign_id", "campaign_id IS NOT NULL"),
    (
        "ix_notification_application_id",
        "notification",
        "application_id",
        "application_id IS NOT NULL",
    ),
    ("ix_admin_action_admin_account_id", "admin_action", "admin_account_id", None),
)
# (name, table, columns): the reporter's index has a second column.
REPORTER_INDEX = ("ix_report_reporter_created_at", "report", ["reporter_account_id", "created_at"])


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, column, where in INDEXES:
            op.create_index(
                name,
                table,
                [column],
                unique=False,
                postgresql_where=sa.text(where) if where else None,
                postgresql_concurrently=True,
                if_not_exists=True,
            )
        name, table, columns = REPORTER_INDEX
        op.create_index(
            name, table, columns, unique=False, postgresql_concurrently=True, if_not_exists=True
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            REPORTER_INDEX[0],
            table_name=REPORTER_INDEX[1],
            postgresql_concurrently=True,
            if_exists=True,
        )
        for name, table, _, _ in INDEXES:
            op.drop_index(name, table_name=table, postgresql_concurrently=True, if_exists=True)
