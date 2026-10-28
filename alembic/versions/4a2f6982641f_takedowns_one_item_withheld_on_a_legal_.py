"""takedowns: one item withheld on a legal order (item 52)

The IT Rules, as amended on 10 February 2026, give a platform 3 hours from a
court order or a government notice to remove or disable access to the
content it names (rule 3(1)(d); legal.md section 3.3). Suspending the whole
account was the only tool. Approved by Adhi on 16 October 2026, with option
A: no automatic hiding on a report (D-104). This migration:

- creates `takedown`: one creator profile, brand or campaign withheld from
  everyone but its owner, on an order (who issued it, its number, the law it
  cites, whether it is sealed, when it reached us) or on a report; the
  deadline (3 hours for an order, the report's own for a report), when it
  was withheld and by whom, when it was lifted and by whom, and `preserved`,
  the item's visible text as it stood, which the IT Rules keep for 180 days
  (rule 3(1)(g)). Its checks hold the clock, the order details only for
  orders, the order received before it was acted on and at most 30 days
  before, a lift always by someone, and one active takedown per item;
- revokes DELETE on it from app_writer: the app adds and lifts takedowns,
  never removes one. Only the owner role could;
- adds `withhold` and `lift_withhold` to the admin log's actions;
- adds two notification types, `content_withheld` (never mutable: nobody
  should learn by finding it gone) and `content_restored` (mutable).

New, empty table: its constraints and indexes are created whole (database.md
section 6). The three widened lists are swapped NOT VALID in the
migration's transaction and validated after it commits, so writes are never
blocked (Squawk, D-050).

ON DELETE: `report_id` SET NULL, since a takedown outlives the report if
the reporter's account goes; the two admins RESTRICT, as in the admin log,
so an admin who acted can never be deleted out from under the record. No
foreign key to the item or its owner: the record must outlive both.

Data impact: none on existing rows.

Downgrade: refuses while any takedown exists, or the admin log holds a
withhold or lift, since the law asks us to keep the first and the log can
never lose an entry. On an empty table it deletes the two new kinds of
notification (each restates a takedown that no longer exists), takes
content_restored out of muted lists, restores the narrower lists and drops
the table.

Revision ID: 4a2f6982641f
Revises: f0ec9547afcc
Create Date: 2026-10-16 02:37:17.704317

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "4a2f6982641f"
down_revision: Union[str, None] = "f0ec9547afcc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
OLD_ACTIONS = ("view_account", "suspend", "restore", "resolve_report")
NEW_ACTIONS = OLD_ACTIONS + ("withhold", "lift_withhold")

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
    "report_received",
    "report_due_soon",
    "report_overdue",
)
NEW_TYPES = OLD_TYPES + ("content_withheld", "content_restored")
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
    "report_received",
)
NEW_MUTABLE = OLD_MUTABLE + ("content_restored",)

LIST_CHECKS = (
    ("admin_action", "ck_admin_action_action_allowed"),
    ("notification", "ck_notification_type_allowed"),
    ("notification_preference", "ck_notification_preference_muted_types_allowed"),
)
NEW_TYPES_SQL = "('content_withheld', 'content_restored')"
APP_WRITER = "app_writer"


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap_lists(
    actions: tuple[str, ...], types: tuple[str, ...], mutable: tuple[str, ...]
) -> None:
    """Replace the three allowed-value checks, NOT VALID, in the migration's transaction."""
    conditions = (
        f"action IN {actions}",
        f"notification_type IN {types}",
        f"muted_types <@ {_array(mutable)}",
    )
    for (table, name), condition in zip(LIST_CHECKS, conditions, strict=True):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
        )


def _validate_lists() -> None:
    with op.get_context().autocommit_block():
        for table, name in LIST_CHECKS:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    op.create_table(
        "takedown",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("subject_kind", sa.String(length=20), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("owner_account_id", sa.UUID(), nullable=False),
        sa.Column("basis", sa.String(length=20), nullable=False),
        sa.Column("issued_by", sa.String(length=200), nullable=True),
        sa.Column("order_reference", sa.String(length=200), nullable=True),
        sa.Column("legal_provision", sa.String(length=200), nullable=True),
        sa.Column(
            "reference_sealed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("report_id", sa.UUID(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withheld_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withheld_by_account_id", sa.UUID(), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifted_by_account_id", sa.UUID(), nullable=True),
        sa.Column("preserved", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(basis = 'report') = (issued_by IS NULL)"
            " AND (basis = 'report') = (order_reference IS NULL)"
            " AND (basis <> 'report' OR legal_provision IS NULL)"
            " AND (basis <> 'report' OR NOT reference_sealed)",
            name=op.f("ck_takedown_order_details_only_for_orders"),
        ),
        sa.CheckConstraint(
            "basis <> 'report'"
            " OR (due_at > received_at AND due_at <= received_at + interval '7 days')",
            name=op.f("ck_takedown_report_due_within_seven_days"),
        ),
        sa.CheckConstraint(
            "basis = 'report' OR due_at = received_at + interval '3 hours'",
            name=op.f("ck_takedown_order_due_in_three_hours"),
        ),
        sa.CheckConstraint(
            "basis IN ('court_order', 'government_notice', 'report')",
            name=op.f("ck_takedown_basis_allowed"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(preserved) = 'object'"
            " AND char_length(preserved::text) <= 20000",
            name=op.f("ck_takedown_preserved_small_object"),
        ),
        sa.CheckConstraint(
            "received_at <= withheld_at"
            " AND (basis = 'report' OR received_at >= withheld_at - interval '30 days')",
            name=op.f("ck_takedown_received_before_withheld"),
        ),
        sa.CheckConstraint(
            "subject_kind IN ('creator', 'brand', 'campaign')",
            name=op.f("ck_takedown_subject_kind_allowed"),
        ),
        sa.CheckConstraint(
            "(lifted_at IS NULL) = (lifted_by_account_id IS NULL)",
            name=op.f("ck_takedown_lifted_by_someone"),
        ),
        sa.CheckConstraint(
            "issued_by IS NULL OR char_length(issued_by) BETWEEN 3 AND 200",
            name=op.f("ck_takedown_issued_by_length"),
        ),
        sa.CheckConstraint(
            "legal_provision IS NULL OR char_length(legal_provision) BETWEEN 3 AND 200",
            name=op.f("ck_takedown_legal_provision_length"),
        ),
        sa.CheckConstraint(
            "lifted_at IS NULL OR lifted_at >= withheld_at",
            name=op.f("ck_takedown_lifted_after_withheld"),
        ),
        sa.CheckConstraint(
            "order_reference IS NULL OR char_length(order_reference) BETWEEN 1 AND 200",
            name=op.f("ck_takedown_order_reference_length"),
        ),
        sa.ForeignKeyConstraint(
            ["lifted_by_account_id"],
            ["account.id"],
            name=op.f("fk_takedown_lifted_by_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["report.id"],
            name=op.f("fk_takedown_report_id_report"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["withheld_by_account_id"],
            ["account.id"],
            name=op.f("fk_takedown_withheld_by_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_takedown")),
    )
    op.create_index("ix_takedown_created_at", "takedown", ["created_at"], unique=False)
    op.create_index(
        "ix_takedown_lifted_by_account_id",
        "takedown",
        ["lifted_by_account_id"],
        unique=False,
        postgresql_where=sa.text("lifted_by_account_id IS NOT NULL"),
    )
    op.create_index(
        "ix_takedown_owner_account_id_created_at",
        "takedown",
        ["owner_account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_takedown_report_id",
        "takedown",
        ["report_id"],
        unique=False,
        postgresql_where=sa.text("report_id IS NOT NULL"),
    )
    op.create_index(
        "ix_takedown_withheld_by_account_id",
        "takedown",
        ["withheld_by_account_id"],
        unique=False,
    )
    op.create_index(
        "uq_takedown_active_subject",
        "takedown",
        ["subject_kind", "subject_id"],
        unique=True,
        postgresql_where=sa.text("lifted_at IS NULL"),
    )
    # The default privileges gave app_writer every row right; a takedown is
    # added and lifted, never removed (rule 3(1)(g)).
    op.execute(f"REVOKE DELETE, TRUNCATE ON takedown FROM {APP_WRITER}")
    _swap_lists(NEW_ACTIONS, NEW_TYPES, NEW_MUTABLE)
    _validate_lists()


def downgrade() -> None:
    kept = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT (SELECT count(*) FROM takedown)"
                " + (SELECT count(*) FROM admin_action"
                " WHERE action IN ('withhold', 'lift_withhold'))"
            )
        )
        .scalar_one()
    )
    if kept:
        raise RuntimeError(
            f"{kept} takedowns or admin log entries about them exist. The IT "
            "Rules ask us to keep what was withheld and its record, and the "
            "admin log never loses an entry; remove them deliberately, as the "
            "owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {NEW_TYPES_SQL}")
    op.execute(
        "UPDATE notification_preference "
        "SET muted_types = array_remove(muted_types, 'content_restored') "
        "WHERE 'content_restored' = ANY (muted_types)"
    )
    _swap_lists(OLD_ACTIONS, OLD_TYPES, OLD_MUTABLE)
    _validate_lists()
    # Its indexes go with it.
    op.drop_table("takedown")
