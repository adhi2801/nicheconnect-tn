"""files on drafts (item 27, piece 2)

Approved by Adhi on 29 October 2026 ("carry on", to the proposal for piece 2
of D-140): a creator attaches images to a draft through the same cleaned
upload pipeline as proof (D-065). This migration:

- adds `proof_file.draft_id`, nullable (NULL: pending, or on a proof), so
  existing rows are untouched. ON DELETE RESTRICT on the draft: what a brand
  approved stays with the draft it approved, as a proof keeps its files;
- adds the unique `(draft_id, position)`: two files never share a place on a
  draft, and it is the new foreign key's index. Built CONCURRENTLY, then made
  a constraint from the index, so writes to `proof_file` are never blocked;
- adds the foreign key NOT VALID, validated after the transaction;
- replaces `pending_is_unattached` (a pending upload is on no draft either)
  and `attached_has_proof` (an attached file is on a proof or a draft), and
  adds `one_parent` (never both), each NOT VALID, validated afterwards;
- adds `draft_file_cleaned` to the deal record's kinds, swapped the same way;
- adds `proof_file.purpose` ('proof' or 'draft', default 'proof'): what an
  upload was asked for, so each joins only its own kind (Adhi, after the
  independent review, 29 October 2026). A constant default, so no rewrite;
- adds `content_draft.images_ready_at`: when every image on a draft was
  cleaned or refused. The brand's 2-day minimum counts from it and nothing
  approves before it (Adhi, the same day). Existing drafts have no images,
  so each is filled with the moment it was shown.

Data impact: every existing file is pending or on a proof, so each is a
proof upload; every existing entry keeps its kind; every existing draft's
images were ready when it was shown, as it has none.

Downgrade: refuses while any file is on a draft, any upload was made for a
draft (without `purpose` it could become proof), or any draft file's
cleaning is sealed on a record (the record's entries can never be removed);
otherwise it reverses each step.

Revision ID: 2d1e67a96a45
Revises: bbddb2e7bb0d
Create Date: 2026-10-29 17:19:29.467816

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d1e67a96a45"
down_revision: Union[str, None] = "bbddb2e7bb0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_KIND = "draft_file_cleaned"
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
    "draft_submitted",
    "draft_approved",
    "draft_auto_approved",
    "draft_changes_requested",
)

OLD_PENDING = "status <> 'pending' OR (proof_id IS NULL AND attached_at IS NULL)"
NEW_PENDING = (
    "status <> 'pending' OR (proof_id IS NULL AND draft_id IS NULL AND attached_at IS NULL)"
)
OLD_ATTACHED = (
    "status NOT IN ('attached', 'cleaned') OR (proof_id IS NOT NULL AND attached_at IS NOT NULL)"
)
NEW_ATTACHED = (
    "status NOT IN ('attached', 'cleaned') "
    "OR ((proof_id IS NOT NULL OR draft_id IS NOT NULL) AND attached_at IS NOT NULL)"
)
ONE_PARENT = "proof_id IS NULL OR draft_id IS NULL"
PURPOSES = "purpose IN ('proof', 'draft')"
PARENT_PURPOSE = (
    "(proof_id IS NULL OR purpose = 'proof') AND (draft_id IS NULL OR purpose = 'draft')"
)
READY_AFTER_SHOWN = "images_ready_at IS NULL OR images_ready_at >= created_at"
APPROVED_WHEN_READY = "status <> 'approved' OR images_ready_at IS NOT NULL"


def _replace_checks(checks: tuple[tuple[str, str, str | None], ...]) -> None:
    """Drop each named check and, where a condition is given, add it back NOT VALID;
    validate after the transaction, so no write waits on a full scan."""
    for table, name, condition in checks:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        if condition is not None:
            op.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID"
            )
    with op.get_context().autocommit_block():
        for table, name, condition in checks:
            if condition is not None:
                op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def upgrade() -> None:
    op.add_column("proof_file", sa.Column("draft_id", sa.UUID(), nullable=True))
    op.add_column(
        "proof_file",
        sa.Column(
            "purpose", sa.String(length=10), server_default=sa.text("'proof'"), nullable=False
        ),
    )
    op.add_column(
        "content_draft",
        sa.Column("images_ready_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE content_draft SET images_ready_at = created_at")
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_proof_file_draft_id"
            " ON proof_file (draft_id, position)"
        )
    op.execute(
        "ALTER TABLE proof_file ADD CONSTRAINT uq_proof_file_draft_id"
        " UNIQUE USING INDEX uq_proof_file_draft_id"
    )
    op.execute(
        "ALTER TABLE proof_file ADD CONSTRAINT fk_proof_file_draft_id_content_draft"
        " FOREIGN KEY (draft_id) REFERENCES content_draft (id) ON DELETE RESTRICT NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TABLE proof_file VALIDATE CONSTRAINT fk_proof_file_draft_id_content_draft"
        )
    _replace_checks(
        (
            ("proof_file", "ck_proof_file_pending_is_unattached", NEW_PENDING),
            ("proof_file", "ck_proof_file_attached_has_proof", NEW_ATTACHED),
            ("proof_file", "ck_proof_file_one_parent", ONE_PARENT),
            ("proof_file", "ck_proof_file_purpose_allowed", PURPOSES),
            ("proof_file", "ck_proof_file_parent_matches_purpose", PARENT_PURPOSE),
            ("content_draft", "ck_content_draft_images_ready_after_shown", READY_AFTER_SHOWN),
            ("content_draft", "ck_content_draft_approved_when_images_ready", APPROVED_WHEN_READY),
            (
                "deal_record_entry",
                "ck_deal_record_entry_kind_allowed",
                f"kind IN {OLD_KINDS + (NEW_KIND,)}",
            ),
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    on_drafts = bind.execute(
        sa.text("SELECT count(*) FROM proof_file WHERE draft_id IS NOT NULL")
    ).scalar_one()
    draft_uploads = bind.execute(
        sa.text("SELECT count(*) FROM proof_file WHERE purpose = 'draft'")
    ).scalar_one()
    sealed = bind.execute(
        sa.text("SELECT count(*) FROM deal_record_entry WHERE kind = :kind"),
        {"kind": NEW_KIND},
    ).scalar_one()
    if on_drafts or sealed or draft_uploads:
        raise RuntimeError(
            f"{on_drafts} files are on drafts, {draft_uploads} uploads were made for "
            f"drafts, and {sealed} draft file cleanings are "
            "sealed on deal records. A brand approved those files with their drafts, "
            "an upload for a draft must never become proof, "
            "and the record's entries cannot be removed at all; settle them "
            "deliberately, as the owner, if that is really intended."
        )
    _replace_checks(
        (
            (
                "deal_record_entry",
                "ck_deal_record_entry_kind_allowed",
                f"kind IN {OLD_KINDS}",
            ),
            ("proof_file", "ck_proof_file_one_parent", None),
            ("proof_file", "ck_proof_file_purpose_allowed", None),
            ("proof_file", "ck_proof_file_parent_matches_purpose", None),
            ("content_draft", "ck_content_draft_images_ready_after_shown", None),
            ("content_draft", "ck_content_draft_approved_when_images_ready", None),
            ("proof_file", "ck_proof_file_attached_has_proof", OLD_ATTACHED),
            ("proof_file", "ck_proof_file_pending_is_unattached", OLD_PENDING),
        )
    )
    op.drop_constraint("fk_proof_file_draft_id_content_draft", "proof_file", type_="foreignkey")
    op.drop_constraint("uq_proof_file_draft_id", "proof_file", type_="unique")
    op.drop_column("content_draft", "images_ready_at")
    op.drop_column("proof_file", "purpose")
    op.drop_column("proof_file", "draft_id")
