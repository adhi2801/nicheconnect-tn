"""draft first (item 27, D-140)

Approved by Adhi on 26 October 2026 ("all as recommended": a memo term the
brand turns on per memo; silence approves by the clock). This migration:

- creates `content_draft`, new and empty, so its checks and indexes are
  made whole. ON DELETE RESTRICT on the memo: what was shown and approved
  is part of the deal's record. Its unique `(deal_memo_id, round)` is the
  foreign key's index; partial unique indexes allow one draft waiting and
  one approved per memo;
- adds `deal_memo.draft_review`, false on every existing memo. A constant
  default rewrites nothing;
- moves the terms version to 3 for new memos, whose seal covers
  `draft_review`; every existing memo keeps its version and its seal. The
  allowed-versions check is swapped NOT VALID and validated after the
  transaction, with the record's kinds, the notification types and the
  types a person may mute (the approvals; a draft waiting and a request for
  changes are urgent).

Data impact: existing memos read `draft_review` false; nothing else.

Downgrade: refuses while any memo is version 3 (its sealed terms include
`draft_review` and could no longer be verified), any draft exists, or any
draft entry is on a record; otherwise it reverses each step.

Revision ID: bbddb2e7bb0d
Revises: 2de4ccbd813c
Create Date: 2026-10-27 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bbddb2e7bb0d"
down_revision: Union[str, None] = "2de4ccbd813c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION_CHECK = "ck_deal_memo_terms_version_known"
NEW_KINDS = ("draft_submitted", "draft_approved", "draft_auto_approved", "draft_changes_requested")
URGENT = ("draft_submitted", "draft_changes_requested")
MUTED_OK = ("draft_approved", "draft_auto_approved")

# Frozen here, rather than read from the models, so this migration means the
# same thing forever.
OLD_KINDS = (
    "record_started",
    "memo_sent",
    "memo_change_requested",
    "memo_accepted",
    "memo_declined",
    "memo_cancelled",
    "proof_submitted",
    "proof_approved",
    "proof_auto_approved",
    "proof_revision_requested",
    "proof_file_cleaned",
    "proof_results_read",
    "payment_opened",
    "payment_marked_paid",
    "payment_confirmed",
    "dispute_opened",
    "dispute_entry_added",
    "dispute_closed",
    "note_added",
    "product_shipped",
    "product_received",
    "feedback_given",
)

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
    "offer_received",
    "offer_accepted",
    "offer_declined",
    "offer_withdrawn",
    "note_added",
    "campaign_alert",
    "product_shipped",
    "product_received",
    "connection_expired",
    "feedback_received",
    "agent_token_created",
)

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
    "offer_received",
    "offer_accepted",
    "offer_declined",
    "offer_withdrawn",
    "note_added",
    "campaign_alert",
    "product_shipped",
    "product_received",
    "connection_expired",
    "feedback_received",
)


def _array(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ", ".join(f"'{value}'" for value in values) + "]::varchar[]"


def _swap_lists(
    versions: str, kinds: tuple[str, ...], types: tuple[str, ...], mutable: tuple[str, ...]
) -> None:
    """Replace the four checks, NOT VALID, then validate after the transaction."""
    checks = (
        ("deal_memo", VERSION_CHECK, f"terms_version IN {versions}"),
        ("deal_record_entry", "ck_deal_record_entry_kind_allowed", f"kind IN {kinds}"),
        ("notification", "ck_notification_type_allowed", f"notification_type IN {types}"),
        (
            "notification_preference",
            "ck_notification_preference_muted_types_allowed",
            f"muted_types <@ {_array(mutable)}",
        ),
    )
    for table, name, condition in checks:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
    with op.get_context().autocommit_block():
        for table, name, _ in checks:
            op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('content_draft',
    sa.Column('id', sa.UUID(), server_default=sa.text('uuidv7()'), nullable=False),
    sa.Column('deal_memo_id', sa.UUID(), nullable=False),
    sa.Column('round', sa.SmallInteger(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('content_url', sa.String(length=500), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), server_default=sa.text("'submitted'"), nullable=False),
    sa.Column('changes_note', sa.Text(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('auto_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'approved') = (approved_at IS NOT NULL)", name=op.f('ck_content_draft_approved_at_matches_status')),
    sa.CheckConstraint("(status = 'changes_requested') = (changes_note IS NOT NULL)", name=op.f('ck_content_draft_changes_note_matches_status')),
    sa.CheckConstraint("NOT auto_approved OR status = 'approved'", name=op.f('ck_content_draft_auto_approved_is_approved')),
    sa.CheckConstraint("content_url IS NULL OR (content_url ~ '^https://' AND char_length(content_url) <= 500)", name=op.f('ck_content_draft_content_url_https')),
    sa.CheckConstraint("status IN ('submitted', 'approved', 'changes_requested')", name=op.f('ck_content_draft_status_allowed')),
    sa.CheckConstraint('changes_note IS NULL OR char_length(btrim(changes_note)) BETWEEN 5 AND 1000', name=op.f('ck_content_draft_changes_note_length')),
    sa.CheckConstraint('char_length(btrim(body)) BETWEEN 1 AND 5000', name=op.f('ck_content_draft_body_length')),
    sa.CheckConstraint('note IS NULL OR char_length(note) <= 1000', name=op.f('ck_content_draft_note_length')),
    sa.CheckConstraint('round >= 1', name=op.f('ck_content_draft_round_positive')),
    sa.ForeignKeyConstraint(['deal_memo_id'], ['deal_memo.id'], name=op.f('fk_content_draft_deal_memo_id_deal_memo'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_content_draft'))
    )
    op.create_index('uq_content_draft_approved', 'content_draft', ['deal_memo_id'], unique=True, postgresql_where=sa.text("status = 'approved'"))
    op.create_index('uq_content_draft_open', 'content_draft', ['deal_memo_id'], unique=True, postgresql_where=sa.text("status = 'submitted'"))
    op.create_index('uq_content_draft_round', 'content_draft', ['deal_memo_id', 'round'], unique=True)
    op.add_column('deal_memo', sa.Column('draft_review', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    # ### end Alembic commands ###
    op.execute("ALTER TABLE deal_memo ALTER COLUMN terms_version SET DEFAULT 3")
    _swap_lists("(1, 2, 3)", OLD_KINDS + NEW_KINDS, OLD_TYPES + NEW_KINDS, OLD_MUTABLE + MUTED_OK)


def downgrade() -> None:
    bind = op.get_bind()
    version_three = bind.execute(
        sa.text("SELECT count(*) FROM deal_memo WHERE terms_version = 3")
    ).scalar_one()
    drafts = bind.execute(sa.text("SELECT count(*) FROM content_draft")).scalar_one()
    sealed = bind.execute(
        sa.text(f"SELECT count(*) FROM deal_record_entry WHERE kind IN {NEW_KINDS}")
    ).scalar_one()
    if version_three or drafts or sealed:
        raise RuntimeError(
            f"{version_three} memos sealed with terms version 3, {drafts} drafts and "
            f"{sealed} sealed draft entries exist. Version 3 seals cover the draft "
            "review and could no longer be verified, drafts are part of each deal's "
            "record, and the record's entries cannot be removed at all; settle them "
            "deliberately, as the owner, if that is really intended."
        )
    op.execute(f"DELETE FROM notification WHERE notification_type IN {NEW_KINDS}")
    op.execute(
        "UPDATE notification_preference"
        " SET muted_types = array_remove(array_remove(muted_types, 'draft_approved'),"
        " 'draft_auto_approved')"
        " WHERE muted_types && ARRAY['draft_approved', 'draft_auto_approved']::varchar[]"
    )
    _swap_lists("(1, 2)", OLD_KINDS, OLD_TYPES, OLD_MUTABLE)
    op.execute("ALTER TABLE deal_memo ALTER COLUMN terms_version SET DEFAULT 2")
    op.drop_column("deal_memo", "draft_review")
    op.drop_index("uq_content_draft_round", table_name="content_draft")
    op.drop_index("uq_content_draft_open", table_name="content_draft")
    op.drop_index("uq_content_draft_approved", table_name="content_draft")
    op.drop_table("content_draft")
