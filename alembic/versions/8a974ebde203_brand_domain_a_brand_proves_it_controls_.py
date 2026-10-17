"""brand domain: a brand proves it controls its website's domain (item 74)

Fake brands start the scams that hurt creators most (trust-and-safety.md
section 2). Approved by Adhi on 17 October 2026, option A: proof by a DNS
TXT record now, by email once our own sender domain exists (D-106). This
migration creates `brand_domain`, one per brand:

- the domain (the registrable one, lower case, no punycode, held by its
  check) and the token the brand publishes at
  `_nicheconnect-challenge.<domain>`, good for 7 days;
- its state: pending, verified, or lapsed after three daily checks in a row
  found the record gone, with each pairing held by a check (verified_at once
  verified, lapsed_at exactly when lapsed, a result with every check);
- the check queue (`check_requested_at`) and the lease a running check holds
  (`checking_since`);
- what creators are shown: since when, whether the answers were
  DNSSEC-validated, and when the registry says the domain was registered.

One verified holder per domain: a partial unique index. Two more partial
indexes serve the checking job: checks asked for, and verified domains by
when they were last checked.

New, empty table: its constraints and indexes are created whole (database.md
section 6).

ON DELETE: `brand_id` CASCADE, since the claim is the brand's own; its
unique constraint is the index the foreign key needs.

Data impact: none on existing rows.

Downgrade: refuses while any domain is verified, since dropping the table
would take a fact creators rely on off every campaign without anyone
deciding to; with none verified, it drops the table, its indexes with it.

Revision ID: 8a974ebde203
Revises: 90b4db0fd32a
Create Date: 2026-10-17 12:59:50.178355

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a974ebde203"
down_revision: Union[str, None] = "90b4db0fd32a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_domain",
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("token", sa.String(length=26), nullable=False),
        sa.Column(
            "status",
            sa.String(length=10),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checking_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", sa.String(length=10), nullable=True),
        sa.Column(
            "consecutive_absent",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lapsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dnssec_validated", sa.Boolean(), nullable=True),
        sa.Column("registered_on", sa.Date(), nullable=True),
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
            "(status = 'lapsed') = (lapsed_at IS NOT NULL)",
            name=op.f("ck_brand_domain_lapsed_at_when_lapsed"),
        ),
        sa.CheckConstraint(
            "(status = 'pending') = (verified_at IS NULL)",
            name=op.f("ck_brand_domain_verified_at_once_verified"),
        ),
        sa.CheckConstraint(
            "domain = lower(domain) AND char_length(domain) <= 253"
            " AND domain ~ '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]([a-z0-9-]{0,61}[a-z0-9])?$'"
            " AND domain NOT LIKE '%xn--%'",
            name=op.f("ck_brand_domain_domain_format"),
        ),
        sa.CheckConstraint(
            "last_result IS NULL OR last_result IN ('found', 'absent', 'unknown', 'taken')",
            name=op.f("ck_brand_domain_last_result_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'lapsed')",
            name=op.f("ck_brand_domain_status_allowed"),
        ),
        sa.CheckConstraint(
            "token ~ '^[a-z2-7]{26}$'", name=op.f("ck_brand_domain_token_format")
        ),
        sa.CheckConstraint(
            "token_expires_at = claimed_at + interval '7 days'",
            name=op.f("ck_brand_domain_token_lasts_seven_days"),
        ),
        sa.CheckConstraint(
            "(last_checked_at IS NULL) = (last_result IS NULL)",
            name=op.f("ck_brand_domain_checked_with_a_result"),
        ),
        sa.CheckConstraint(
            "consecutive_absent BETWEEN 0 AND 3",
            name=op.f("ck_brand_domain_consecutive_absent_range"),
        ),
        sa.CheckConstraint(
            "lapsed_at IS NULL OR lapsed_at >= verified_at",
            name=op.f("ck_brand_domain_lapsed_after_verified"),
        ),
        sa.CheckConstraint(
            "verified_at IS NULL OR verified_at >= claimed_at",
            name=op.f("ck_brand_domain_verified_after_claimed"),
        ),
        sa.ForeignKeyConstraint(
            ["brand_id"],
            ["brand.id"],
            name=op.f("fk_brand_domain_brand_id_brand"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brand_domain")),
        sa.UniqueConstraint("brand_id", name=op.f("uq_brand_domain_brand_id")),
    )
    op.create_index(
        "ix_brand_domain_check_requested_at",
        "brand_domain",
        ["check_requested_at"],
        unique=False,
        postgresql_where=sa.text("check_requested_at IS NOT NULL"),
    )
    op.create_index(
        "ix_brand_domain_verified_last_checked_at",
        "brand_domain",
        ["last_checked_at"],
        unique=False,
        postgresql_where=sa.text("status = 'verified'"),
    )
    op.create_index(
        "uq_brand_domain_verified_domain",
        "brand_domain",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("status = 'verified'"),
    )


def downgrade() -> None:
    verified = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM brand_domain WHERE status = 'verified'"))
        .scalar_one()
    )
    if verified:
        raise RuntimeError(
            f"{verified} brands have a verified domain that creators see on "
            "their campaigns. Dropping it would take that away without anyone "
            "deciding to; remove them deliberately, as the owner, if that is "
            "really intended."
        )
    # Its indexes go with it.
    op.drop_table("brand_domain")
