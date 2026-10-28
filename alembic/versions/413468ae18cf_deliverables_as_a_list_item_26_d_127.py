"""deliverables as a list (item 26, D-127)

Approved by Adhi on 26 October 2026 (D-127: lists on campaigns and memos,
the campaign's pre-filling the memo's; proof still per deal; the free text
kept as the summary). This migration:

- creates `campaign_deliverable` and `memo_deliverable`, new and empty, so
  their checks and indexes are made whole. ON DELETE CASCADE on the
  campaign, whose brief they are; RESTRICT on the memo, a record of what was
  agreed. Each `(parent, position)` unique rule is also its foreign key's
  index;
- adds `deal_memo.terms_version`, which says what the deal record's
  fingerprint covers. Added with default 1, so every existing memo is
  version 1 and keeps the fingerprint it was sealed with, forever; the
  default then becomes 2 for new memos. Adding a column with a constant
  default rewrites nothing. Its check is added NOT VALID and validated
  after the transaction.

Data impact: existing memos read as version 1 with no list; nothing else.

Downgrade: refuses while any memo is version 2, since its sealed terms
include its list and could no longer be verified, or any deliverable row
exists; otherwise drops the column and both tables.

Revision ID: 413468ae18cf
Revises: 3cab62503c56
Create Date: 2026-10-26 00:26:53.295274

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "413468ae18cf"
down_revision: Union[str, None] = "3cab62503c56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VERSION_CHECK = "ck_deal_memo_terms_version_known"


def _deliverables(table: str, parent: str, parent_table: str, on_delete: str) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(parent, sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "format IN ('post', 'reel', 'story', 'short', 'video', 'live', 'other')",
            name=op.f(f"ck_{table}_format_allowed"),
        ),
        sa.CheckConstraint(
            "platform IN ('instagram', 'youtube')", name=op.f(f"ck_{table}_platform_allowed")
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(btrim(note)) BETWEEN 1 AND 200",
            name=op.f(f"ck_{table}_note_length"),
        ),
        sa.CheckConstraint("position BETWEEN 0 AND 9", name=op.f(f"ck_{table}_position_range")),
        sa.CheckConstraint("quantity BETWEEN 1 AND 20", name=op.f(f"ck_{table}_quantity_range")),
        sa.ForeignKeyConstraint(
            [parent],
            [f"{parent_table}.id"],
            name=op.f(f"fk_{table}_{parent}_{parent_table}"),
            ondelete=on_delete,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint(parent, "position", name=f"uq_{table}_place"),
    )


def upgrade() -> None:
    _deliverables("campaign_deliverable", "campaign_id", "campaign", "CASCADE")
    _deliverables("memo_deliverable", "deal_memo_id", "deal_memo", "RESTRICT")
    op.add_column(
        "deal_memo",
        sa.Column("terms_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
    )
    op.execute("ALTER TABLE deal_memo ALTER COLUMN terms_version SET DEFAULT 2")
    op.execute(
        f"ALTER TABLE deal_memo ADD CONSTRAINT {VERSION_CHECK}"
        " CHECK (terms_version IN (1, 2)) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE deal_memo VALIDATE CONSTRAINT {VERSION_CHECK}")


def downgrade() -> None:
    bind = op.get_bind()
    version_two = bind.execute(
        sa.text("SELECT count(*) FROM deal_memo WHERE terms_version = 2")
    ).scalar_one()
    rows = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM memo_deliverable)"
            " + (SELECT count(*) FROM campaign_deliverable)"
        )
    ).scalar_one()
    if version_two or rows:
        raise RuntimeError(
            f"{version_two} memos carry terms version 2 and {rows} deliverable rows "
            "exist. A version 2 memo's sealed terms include its list, so without "
            "it the deal record could no longer prove those terms; settle them "
            "deliberately, as the owner, if that is really intended."
        )
    op.execute(f"ALTER TABLE deal_memo DROP CONSTRAINT {VERSION_CHECK}")
    op.drop_column("deal_memo", "terms_version")
    op.drop_table("memo_deliverable")
    op.drop_table("campaign_deliverable")
