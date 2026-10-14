"""the app's own database role, rows only (item 97)

Until 14 October 2026 the app connected as the table owner, and an owner can
ALTER TABLE ... DISABLE TRIGGER, so the app's own credentials could switch
off the seals on the deal record, the admin log and dispute events (D-057,
item 99), or drop any table. Approved by Adhi the same day as option A of
item 97 (D-100).

This makes app_writer, a group role with no login, and gives it exactly what
the running app needs:

- USAGE on the public schema, and nothing that creates objects in it;
- SELECT, INSERT, UPDATE and DELETE on every table;
- on the five sealed tables, only SELECT and INSERT, so a change is refused
  by permission before the triggers are even reached: protected twice;
- on alembic_version, only SELECT (the readiness and migration checks read
  it; only the release step writes it);
- no TRUNCATE, REFERENCES or TRIGGER anywhere, and no ownership.

Tables made by later migrations get the same row rights by default (ALTER
DEFAULT PRIVILEGES for the role running the migrations). A later sealed table
must revoke UPDATE and DELETE itself; tests/test_app_role.py fails if one
does not.

The login the app uses, nicheconnect_app, is a member of app_writer, made
and given its password by the release step (app/db/prepare.py), because a
password has no place in a migration.

Roles belong to the whole PostgreSQL server, not to one database, so the
role is made only if it does not exist, and the downgrade takes away every
right it was given here but leaves the role: another database on the same
server (a laptop's test database) may still use it. No data changes.

Revision ID: 0dbcaacb1030
Revises: 068ad68f4079
Create Date: 2026-10-14 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0dbcaacb1030'
down_revision: Union[str, None] = '068ad68f4079'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE = "app_writer"
# Frozen here: the sealed tables as of this migration.
SEALED = (
    "admin_action",
    "deal_record_checkpoint",
    "deal_record_entry",
    "deal_record_timestamp",
    "dispute_event",
)


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ROLE}")
    op.execute(f"REVOKE UPDATE, DELETE ON {', '.join(SEALED)} FROM {ROLE}")
    op.execute(f"REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM {ROLE}")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ROLE}"
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
