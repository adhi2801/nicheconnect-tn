"""city rate report (item 84, D-200)

Approved by Adhi on 19 November 2026 (D-200, option A on all three points:
agreed fees built and switched off, the floors of Decision 2, and this
table, locked on publish), and amended in place before it was merged, on
his approval of 22 November 2026 (D-201: correctable quarters, the seal
widened, an admin read logged). This migration:

- creates `city_rate_report`, new and empty, so its checks and indexes are
  made whole: one row a quarter and method version (`quarter,
  method_version` UNIQUE, which is what makes a second build of a quarter a
  no-op), its aggregate body, the body's SHA-256, when it was built, who
  published it and when, whether it was withdrawn and why (never before it
  was published), and the withdrawn report of the same quarter it corrects
  (`supersedes_id`, unique: a report is corrected at most once; the unique
  index is the key's index). ON DELETE RESTRICT on the publishing admin, as
  on the admin log: who published a cited figure never vanishes as a side
  effect. That key is indexed (`ix_city_rate_report_published_by_account_id`);
- adds a trigger, `city_rate_report_sealed`, after D-057's seal: once a
  report is published, any change to what it says, to its id or what it
  corrects, or to when and by whom it was published, is refused, and so is
  deleting it; the one change left is withdrawing it, once, with a reason.
  TRUNCATE is refused always, since it would take published reports with it;
- adds a trigger, `city_rate_report_supersedes`, refusing a second row for a
  quarter unless it supersedes that quarter's newest version, which must be
  withdrawn, under a higher method version (a row of the same quarter and
  version is let through, for the unique constraint to answer);
- widens the admin log's actions with `publish_rate_report`,
  `withdraw_rate_report`, `view_rate_report` and `rebuild_rate_report`,
  swapped NOT VALID and validated after the transaction (database.md
  section 6).

Data impact: none on existing rows.

Downgrade: refuses while any report is published, or while the admin log
records publishing or withdrawing one: a cited figure, and the log of who
published it, are never lost by a rollback. With none, it narrows the admin
log's actions back, and drops the triggers, their functions and the table
(unpublished drafts go with it; the daily job builds them again).

Revision ID: c84a7e2d5b19
Revises: 578a45512fe0
Create Date: 2026-11-20 18:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c84a7e2d5b19"
down_revision: Union[str, None] = "578a45512fe0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ACTIONS = (
    "view_account",
    "suspend",
    "restore",
    "resolve_report",
    "withhold",
    "lift_withhold",
    "clear_brand_name",
    "withdraw_brand_name_clearance",
)
ADDED_ACTIONS = (
    "publish_rate_report",
    "withdraw_rate_report",
    "view_rate_report",
    "rebuild_rate_report",
)
NEW_ACTIONS = OLD_ACTIONS + ADDED_ACTIONS
ACTION_CHECK = "ck_admin_action_action_allowed"

SEAL_FUNCTION = """
CREATE FUNCTION city_rate_report_seal() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'city_rate_report_sealed: TRUNCATE refused'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.published_at IS NULL THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'city_rate_report_sealed: % is published, DELETE refused',
            OLD.quarter USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
        OR NEW.quarter IS DISTINCT FROM OLD.quarter
        OR NEW.supersedes_id IS DISTINCT FROM OLD.supersedes_id
        OR NEW.method_version IS DISTINCT FROM OLD.method_version
        OR NEW.body IS DISTINCT FROM OLD.body
        OR NEW.body_sha256 IS DISTINCT FROM OLD.body_sha256
        OR NEW.built_at IS DISTINCT FROM OLD.built_at
        OR NEW.published_at IS DISTINCT FROM OLD.published_at
        OR NEW.published_by_account_id IS DISTINCT FROM OLD.published_by_account_id
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'city_rate_report_sealed: % is published, its figures cannot change',
            OLD.quarter USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.withdrawn_at IS NOT NULL AND (
        NEW.withdrawn_at IS DISTINCT FROM OLD.withdrawn_at
        OR NEW.withdrawn_reason IS DISTINCT FROM OLD.withdrawn_reason
    ) THEN
        RAISE EXCEPTION 'city_rate_report_sealed: % was withdrawn, and stays withdrawn',
            OLD.quarter USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$
"""


SUPERSEDES_FUNCTION = """
CREATE FUNCTION city_rate_report_supersede_check() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    newest city_rate_report%ROWTYPE;
BEGIN
    -- FOR UPDATE below locks nothing when the quarter has no row yet, so two
    -- first builds under different versions would both pass: serialise on
    -- the quarter itself, held to the end of the transaction.
    PERFORM pg_advisory_xact_lock(hashtext('city_rate_report:' || NEW.quarter));
    IF EXISTS (
        SELECT 1 FROM city_rate_report
        WHERE quarter = NEW.quarter AND method_version = NEW.method_version
            AND id IS DISTINCT FROM NEW.id
    ) THEN
        RETURN NEW;  -- the unique constraint answers (ON CONFLICT DO NOTHING)
    END IF;
    SELECT * INTO newest FROM city_rate_report
    WHERE quarter = NEW.quarter AND id IS DISTINCT FROM NEW.id
    ORDER BY method_version DESC
    LIMIT 1
    FOR UPDATE;
    IF NOT FOUND THEN
        IF NEW.supersedes_id IS NOT NULL THEN
            RAISE EXCEPTION 'city_rate_report_supersedes: % has no report to supersede',
                NEW.quarter USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.supersedes_id IS DISTINCT FROM newest.id
        OR newest.withdrawn_at IS NULL
        OR NEW.method_version <= newest.method_version
    THEN
        RAISE EXCEPTION 'city_rate_report_supersedes: a new % report must supersede its newest, withdrawn version under a higher method version',
            NEW.quarter USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$
"""


def _swap_actions(values: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE admin_action DROP CONSTRAINT {ACTION_CHECK}")
    op.execute(
        f"ALTER TABLE admin_action ADD CONSTRAINT {ACTION_CHECK} "
        f"CHECK (action IN {values}) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE admin_action VALIDATE CONSTRAINT {ACTION_CHECK}")


def upgrade() -> None:
    op.create_table(
        "city_rate_report",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("quarter", sa.String(length=7), nullable=False),
        sa.Column("method_version", sa.SmallInteger(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "published_by_account_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "quarter ~ '^[0-9]{4}-Q[1-4]$'",
            name=op.f("ck_city_rate_report_quarter_shape"),
        ),
        sa.CheckConstraint(
            "method_version >= 1",
            name=op.f("ck_city_rate_report_method_version_positive"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(body) = 'object'",
            name=op.f("ck_city_rate_report_body_is_object"),
        ),
        sa.CheckConstraint(
            "body_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_city_rate_report_body_sha256_shape"),
        ),
        sa.CheckConstraint(
            "(published_at IS NULL) = (published_by_account_id IS NULL)",
            name=op.f("ck_city_rate_report_published_with_its_admin"),
        ),
        sa.CheckConstraint(
            "(withdrawn_at IS NULL) = (withdrawn_reason IS NULL)",
            name=op.f("ck_city_rate_report_withdrawn_with_its_reason"),
        ),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR published_at IS NOT NULL",
            name=op.f("ck_city_rate_report_withdrawn_only_once_published"),
        ),
        sa.CheckConstraint(
            "withdrawn_reason IS NULL OR char_length(btrim(withdrawn_reason))"
            " BETWEEN 10 AND 500",
            name=op.f("ck_city_rate_report_withdrawn_reason_length"),
        ),
        sa.CheckConstraint(
            "withdrawn_at IS NULL OR withdrawn_at >= published_at",
            name=op.f("ck_city_rate_report_withdrawn_after_published"),
        ),
        sa.ForeignKeyConstraint(
            ["published_by_account_id"],
            ["account.id"],
            name=op.f("fk_city_rate_report_published_by_account_id_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["city_rate_report.id"],
            name=op.f("fk_city_rate_report_supersedes_id_city_rate_report"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_city_rate_report")),
        sa.UniqueConstraint(
            "quarter",
            "method_version",
            name=op.f("uq_city_rate_report_quarter_method_version"),
        ),
    )
    op.create_index(
        "uq_city_rate_report_supersedes_id",
        "city_rate_report",
        ["supersedes_id"],
        unique=True,
    )
    op.create_index(
        "ix_city_rate_report_published_by_account_id",
        "city_rate_report",
        ["published_by_account_id"],
        unique=False,
    )
    op.execute(SEAL_FUNCTION)
    op.execute(
        "CREATE TRIGGER city_rate_report_sealed "
        "BEFORE UPDATE OR DELETE ON city_rate_report "
        "FOR EACH ROW EXECUTE FUNCTION city_rate_report_seal()"
    )
    op.execute(
        "CREATE TRIGGER city_rate_report_no_truncate "
        "BEFORE TRUNCATE ON city_rate_report "
        "FOR EACH STATEMENT EXECUTE FUNCTION city_rate_report_seal()"
    )
    op.execute(SUPERSEDES_FUNCTION)
    op.execute(
        "CREATE TRIGGER city_rate_report_supersedes "
        "BEFORE INSERT OR UPDATE OF quarter, method_version, supersedes_id "
        "ON city_rate_report "
        "FOR EACH ROW EXECUTE FUNCTION city_rate_report_supersede_check()"
    )
    _swap_actions(NEW_ACTIONS)


def downgrade() -> None:
    bind = op.get_bind()
    published = bind.execute(
        sa.text("SELECT count(*) FROM city_rate_report WHERE published_at IS NOT NULL")
    ).scalar_one()
    if published:
        raise RuntimeError(
            f"{published} quarterly rate reports are published, and may have been "
            "quoted. Dropping them would lose what was cited; withdraw and remove "
            "each deliberately, as the owner, if that is really intended."
        )
    logged = bind.execute(
        sa.text("SELECT count(*) FROM admin_action WHERE action IN :kinds").bindparams(
            sa.bindparam("kinds", expanding=True)
        ),
        {"kinds": list(ADDED_ACTIONS)},
    ).scalar_one()
    if logged:
        raise RuntimeError(
            f"{logged} admin log entries record publishing, withdrawing, reading "
            "or building again a rate report. The log is append-only and cannot lose them; the narrower "
            "list of actions cannot hold them."
        )
    _swap_actions(OLD_ACTIONS)
    op.execute("DROP TRIGGER city_rate_report_supersedes ON city_rate_report")
    op.execute("DROP FUNCTION city_rate_report_supersede_check()")
    op.execute("DROP TRIGGER city_rate_report_no_truncate ON city_rate_report")
    op.execute("DROP TRIGGER city_rate_report_sealed ON city_rate_report")
    op.execute("DROP FUNCTION city_rate_report_seal()")
    op.drop_index("uq_city_rate_report_supersedes_id", table_name="city_rate_report")
    op.drop_index(
        "ix_city_rate_report_published_by_account_id", table_name="city_rate_report"
    )
    op.drop_table("city_rate_report")
