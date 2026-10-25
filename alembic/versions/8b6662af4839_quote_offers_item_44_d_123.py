"""quote offers (item 44, D-123)

Counter-offers on a quote, approved by Adhi on 25 October 2026 (D-123:
both sides counter, at most 3 offers each per application; an agreed figure
pre-fills the memo, which stays the contract; the offers kept in their own
table and both exports, not sealed). This migration:

- creates `quote_offer`, new and empty, so its checks and indexes are made
  whole. ON DELETE RESTRICT on `application_id`: an offer is a record of a
  negotiation, as the application is of what happened, and neither may
  vanish as a side effect. The foreign key's index is the history index
  `(application_id, made_at)`; a partial unique index keeps one open offer
  per application;
- widens the notification types with `offer_received`, `offer_accepted`,
  `offer_declined` and `offer_withdrawn`, and the types a person may mute
  with the same four, each check swapped NOT VALID and validated after the
  transaction, so writes are never blocked.

Data impact: none on existing rows.

Downgrade: refuses while any offer exists, since dropping the table would
destroy both sides' record of what they offered. Otherwise it deletes the
four kinds of notification and takes them out of anyone's muted list,
restores the narrower lists and drops the table.

Revision ID: 8b6662af4839
Revises: b7e026caa4a9
Create Date: 2026-10-25 15:41:41.346392

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b6662af4839"
down_revision: Union[str, None] = "b7e026caa4a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
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
    "content_withheld",
    "content_restored",
    "admin_signed_in",
    "admin_second_factor_refused",
    "admin_second_factor_changed",
    "upi_change_pending",
    "upi_change_cancelled",
    "data_exported",
    "logged_out_everywhere",
    "phone_change_requested",
    "phone_change_cancelled",
    "phone_changed",
    "phone_change_failed",
    "data_export_ready",
    "data_export_failed",
    "passkey_added",
    "passkey_removed",
    "passkey_reset_requested",
    "passkey_reset_cancelled",
    "passkey_only_changed",
    "session_ended",
    "deletion_requested",
    "deletion_cancelled",
    "deletion_held_by_deals",
)
ADDED_TYPES = ("offer_received", "offer_accepted", "offer_declined", "offer_withdrawn")
NEW_TYPES = OLD_TYPES + ADDED_TYPES
TYPE_CHECK = "ck_notification_type_allowed"
# The four are about one's own negotiation, and may be muted like the other
# deal notices (D-079), so the preferences' list widens with them.
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
    "content_restored",
)
NEW_MUTABLE = OLD_MUTABLE + ADDED_TYPES
MUTED_CHECK = "ck_notification_preference_muted_types_allowed"


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap_types(types: tuple[str, ...], mutable: tuple[str, ...]) -> None:
    """Replace both lists' checks, NOT VALID, then validate after the transaction."""
    checks = (
        ("notification", TYPE_CHECK, f"notification_type IN {types}"),
        ("notification_preference", MUTED_CHECK, f"muted_types <@ {_array(mutable)}"),
    )
    for table, name, condition in checks:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
    with op.get_context().autocommit_block():
        for table, name, _ in checks:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    op.create_table(
        "quote_offer",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency", sa.String(length=3), server_default=sa.text("'INR'"), nullable=False
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(length=10), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("currency = 'INR'", name=op.f("ck_quote_offer_currency_allowed")),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('accepted', 'declined', 'replaced', 'withdrawn')",
            name=op.f("ck_quote_offer_outcome_allowed"),
        ),
        sa.CheckConstraint("side IN ('brand', 'creator')", name=op.f("ck_quote_offer_side_allowed")),
        sa.CheckConstraint(
            "(outcome IS NULL) = (answered_at IS NULL)",
            name=op.f("ck_quote_offer_answered_with_its_time"),
        ),
        sa.CheckConstraint("amount_paise > 0", name=op.f("ck_quote_offer_amount_positive")),
        sa.CheckConstraint(
            "answered_at IS NULL OR answered_at >= made_at",
            name=op.f("ck_quote_offer_answered_after_made"),
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND 500",
            name=op.f("ck_quote_offer_note_length"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["application.id"],
            name=op.f("fk_quote_offer_application_id_application"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quote_offer")),
    )
    op.create_index(
        "ix_quote_offer_application_id_made_at",
        "quote_offer",
        ["application_id", "made_at"],
        unique=False,
    )
    op.create_index(
        "uq_quote_offer_one_open",
        "quote_offer",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("outcome IS NULL"),
    )
    _swap_types(NEW_TYPES, NEW_MUTABLE)


def downgrade() -> None:
    offers = op.get_bind().execute(sa.text("SELECT count(*) FROM quote_offer")).scalar_one()
    if offers:
        raise RuntimeError(
            f"{offers} quote offers exist. They are both sides' record of what "
            "they offered each other, and dropping the table would destroy it; "
            "remove them deliberately, as the owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {ADDED_TYPES}")
    for kind in ADDED_TYPES:
        op.execute(
            "UPDATE notification_preference"
            f" SET muted_types = array_remove(muted_types, '{kind}')"
            f" WHERE '{kind}' = ANY (muted_types)"
        )
    _swap_types(OLD_TYPES, OLD_MUTABLE)
    op.drop_index(
        "uq_quote_offer_one_open",
        table_name="quote_offer",
        postgresql_where=sa.text("outcome IS NULL"),
    )
    op.drop_index("ix_quote_offer_application_id_made_at", table_name="quote_offer")
    op.drop_table("quote_offer")
