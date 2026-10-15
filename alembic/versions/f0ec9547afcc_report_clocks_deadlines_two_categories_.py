"""report clocks: deadlines, two categories, warnings (item 51)

The IT Rules, as amended on 10 February 2026, give every report a clock:
2 hours for impersonation and intimate content, 36 hours for content the
rules prohibit, 7 days for any other grievance (legal.md section 3.3;
app/modules/admin/report_clocks.py). Approved by Adhi on 15 October 2026,
option A (D-103). This migration:

- adds two report categories, `impersonation` and `intimate_content`, to the
  one list that reports and suspensions share (D-061): report.category and
  account.suspension_reason;
- adds report.due_at, the deadline fixed when a report is filed, backfilled
  for existing reports from their category by the same table as the code,
  frozen here; then NOT NULL;
- adds report.due_soon_alerted_at and report.overdue_alerted_at: when the
  admins were warned. NULL means not (yet);
- adds two checks: a deadline after filing and at most 7 days after it, the
  law's longest clock; and a late warning only once the deadline has passed;
- replaces ix_report_status_created_at with ix_report_status_due_at: the
  queue is now nearest deadline first, and the warning job searches open
  reports by deadline. Nothing else read the old index;
- adds three notification types: `report_received` (to the reporter, may be
  muted like report_resolved) and `report_due_soon` and `report_overdue` (to
  the admins, never mutable: a deadline runs against them).

How, so writes are never blocked (database.md section 6, Squawk, D-050):
every new or widened check is added NOT VALID in the first transaction and
validated after it commits; due_at becomes NOT NULL by validating a
`due_at IS NOT NULL` check first, which lets PostgreSQL skip the scan, then
dropping that check; the indexes are built and dropped CONCURRENTLY. Nothing
is deployed yet, so no older code runs against the new column between the
steps (expand, migrate, contract: not yet needed).

No foreign keys, so no ON DELETE.

Data impact: existing reports get the deadline their category would have
had; nothing else changes.

Downgrade: refuses while any report or suspension uses one of the two new
categories. Mapping a report of impersonation onto another category would
rewrite what a person told us, so it must be done deliberately, not by a
rollback. Otherwise it deletes the three new kinds of notification (each
restates a report's id, category and deadline, all still in the report
table), takes report_received out of muted lists, restores the narrower
checks and the old index, and drops the three columns. The deadlines can be
worked out again from the categories; when the admins were warned is also
in the logs, kept 180 days.

Revision ID: f0ec9547afcc
Revises: 0dbcaacb1030
Create Date: 2026-10-15 22:53:57.596581

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0ec9547afcc"
down_revision: Union[str, None] = "0dbcaacb1030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
OLD_CATEGORIES = ("fake_profile", "spam", "abuse", "non_payment", "other")
NEW_CATEGORIES = OLD_CATEGORIES + ("impersonation", "intimate_content")

OLD_TYPES = (
    "application_received",
    "application_withdrawn",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "proof_submitted",
    "invitation_accepted",
    "invitation_declined",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "memo_sent",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "payment_marked_paid",
    "invitation_received",
    "invitation_withdrawn",
    "memo_cancelled",
    "payment_confirmed",
    "report_resolved",
)
NEW_TYPES = OLD_TYPES + ("report_received", "report_due_soon", "report_overdue")
OLD_MUTABLE = (
    "application_received",
    "application_withdrawn",
    "memo_accepted",
    "memo_declined",
    "memo_change_requested",
    "invitation_accepted",
    "invitation_declined",
    "application_shortlisted",
    "application_accepted",
    "application_rejected",
    "proof_approved",
    "proof_auto_approved",
    "invitation_received",
    "invitation_withdrawn",
    "memo_cancelled",
    "payment_confirmed",
    "report_resolved",
)
NEW_MUTABLE = OLD_MUTABLE + ("report_received",)

# report_clocks.ANSWER_WITHIN on 15 October 2026, for the backfill.
CLOCKS = {
    "impersonation": "2 hours",
    "intimate_content": "2 hours",
    "abuse": "36 hours",
    "fake_profile": "36 hours",
    "spam": "36 hours",
    "other": "36 hours",
    "non_payment": "7 days",
}

LIST_CHECKS = (
    ("report", "ck_report_category_allowed"),
    ("account", "ck_account_suspension_reason_allowed"),
    ("notification", "ck_notification_type_allowed"),
    ("notification_preference", "ck_notification_preference_muted_types_allowed"),
)
REPORT_CHECKS = (
    (
        "ck_report_due_within_seven_days",
        "due_at > created_at AND due_at <= created_at + interval '7 days'",
    ),
    (
        "ck_report_overdue_alert_once_due",
        "overdue_alerted_at IS NULL OR overdue_alerted_at > due_at",
    ),
)
NOT_NULL_STEP = "ck_report_due_at_not_null"
NEW_TYPES_SQL = "('report_received', 'report_due_soon', 'report_overdue')"


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap_lists(
    categories: tuple[str, ...], types: tuple[str, ...], mutable: tuple[str, ...]
) -> None:
    """Replace the four allowed-value checks, NOT VALID, in the migration's transaction."""
    conditions = (
        f"category IN {categories}",
        f"suspension_reason IS NULL OR suspension_reason IN {categories}",
        f"notification_type IN {types}",
        f"muted_types <@ {_array(mutable)}",
    )
    for (table, name), condition in zip(LIST_CHECKS, conditions, strict=True):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
        )


def upgrade() -> None:
    op.add_column(
        "report", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "report",
        sa.Column("due_soon_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "report",
        sa.Column("overdue_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )
    _swap_lists(NEW_CATEGORIES, NEW_TYPES, NEW_MUTABLE)
    cases = " ".join(
        f"WHEN '{category}' THEN interval '{within}'"
        for category, within in CLOCKS.items()
    )
    op.execute(f"UPDATE report SET due_at = created_at + CASE category {cases} END")
    op.execute(
        f"ALTER TABLE report ADD CONSTRAINT {NOT_NULL_STEP} CHECK (due_at IS NOT NULL) NOT VALID"
    )
    for name, condition in REPORT_CHECKS:
        op.execute(
            f"ALTER TABLE report ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
        )

    with op.get_context().autocommit_block():
        for table, name in LIST_CHECKS:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
        for name in (NOT_NULL_STEP, *(name for name, _ in REPORT_CHECKS)):
            op.execute(f"ALTER TABLE report VALIDATE CONSTRAINT {name}")
        op.create_index(
            "ix_report_status_due_at",
            "report",
            ["status", "due_at"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_report_status_created_at",
            table_name="report",
            postgresql_concurrently=True,
        )

    # The validated check proves no NULL is left, so this skips the scan.
    op.alter_column("report", "due_at", nullable=False)
    op.execute(f"ALTER TABLE report DROP CONSTRAINT {NOT_NULL_STEP}")


def downgrade() -> None:
    kept = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM report"
                " WHERE category IN ('impersonation', 'intimate_content'))"
                " + (SELECT count(*) FROM account"
                " WHERE suspension_reason IN ('impersonation', 'intimate_content'))"
            )
        )
        .scalar_one()
    )
    if kept:
        raise RuntimeError(
            f"{kept} reports or suspensions are for impersonation or intimate "
            "content, categories the older schema does not have. Recategorising "
            "them would rewrite what a person reported; do it deliberately first "
            "if losing the distinction is intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {NEW_TYPES_SQL}")
    op.execute(
        "UPDATE notification_preference "
        "SET muted_types = array_remove(muted_types, 'report_received') "
        "WHERE 'report_received' = ANY (muted_types)"
    )
    _swap_lists(OLD_CATEGORIES, OLD_TYPES, OLD_MUTABLE)
    for name, _ in REPORT_CHECKS:
        op.execute(f"ALTER TABLE report DROP CONSTRAINT {name}")
    with op.get_context().autocommit_block():
        for table, name in LIST_CHECKS:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")
        op.create_index(
            "ix_report_status_created_at",
            "report",
            ["status", "created_at"],
            unique=False,
            postgresql_concurrently=True,
        )
        op.drop_index(
            "ix_report_status_due_at", table_name="report", postgresql_concurrently=True
        )
    op.drop_column("report", "overdue_alerted_at")
    op.drop_column("report", "due_soon_alerted_at")
    op.drop_column("report", "due_at")
