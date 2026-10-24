"""brand name clearance (D-119)

Item 75 (D-118) holds a brand whose name looks like a protected brand's
until it verifies that brand's domain; a genuine shop with a close name and
no website had no way through. Approved by Adhi on 24 October 2026 (D-119),
as the schema request named it. This migration:

- adds `brand.name_cleared` (the exact name an admin cleared),
  `brand.name_cleared_at` and `brand.name_cleared_by_account_id` (SET NULL:
  the clearance outlives the admin's account, and the admin log keeps who
  it was). Nullable, no default, so adding them rewrites nothing;
- holds them together by two checks, and the admin by a foreign key, each
  added NOT VALID and validated after the transaction; indexes the key
  CONCURRENTLY, so writes to `brand` are never blocked;
- widens the admin log's actions with `clear_brand_name` and
  `withdraw_brand_name_clearance`, swapped NOT VALID and validated after.

Data impact: none on existing rows.

Downgrade: refuses while any brand holds a clearance, since dropping it
would silently put an admin-cleared brand back on hold. Otherwise it
restores the narrower list of admin actions (the log cannot hold one of the
new kinds then, so it refuses while any exists too) and drops the columns.

Revision ID: 82bb81b5eed4
Revises: ecb64002aa29
Create Date: 2026-10-24 22:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "82bb81b5eed4"
down_revision: Union[str, None] = "ecb64002aa29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ACTIONS = (
    "view_account",
    "suspend",
    "restore",
    "resolve_report",
    "withhold",
    "lift_withhold",
)
ADDED_ACTIONS = ("clear_brand_name", "withdraw_brand_name_clearance")
NEW_ACTIONS = OLD_ACTIONS + ADDED_ACTIONS
ACTION_CHECK = "ck_admin_action_action_allowed"
CHECKS = {
    "ck_brand_name_cleared_with_its_time": "(name_cleared IS NULL) = (name_cleared_at IS NULL)",
    "ck_brand_name_cleared_by_only_with_a_clearance": (
        "name_cleared_by_account_id IS NULL OR name_cleared IS NOT NULL"
    ),
}
FOREIGN_KEY = "fk_brand_name_cleared_by_account_id_account"
INDEX = "ix_brand_name_cleared_by_account_id"


def _swap_actions(values: tuple[str, ...]) -> None:
    op.execute(f"ALTER TABLE admin_action DROP CONSTRAINT {ACTION_CHECK}")
    op.execute(
        f"ALTER TABLE admin_action ADD CONSTRAINT {ACTION_CHECK} "
        f"CHECK (action IN {values}) NOT VALID"
    )
    with op.get_context().autocommit_block():
        op.execute(f"ALTER TABLE admin_action VALIDATE CONSTRAINT {ACTION_CHECK}")


def upgrade() -> None:
    op.add_column("brand", sa.Column("name_cleared", sa.String(length=150), nullable=True))
    op.add_column(
        "brand", sa.Column("name_cleared_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("brand", sa.Column("name_cleared_by_account_id", sa.UUID(), nullable=True))
    for name, condition in CHECKS.items():
        op.execute(f"ALTER TABLE brand ADD CONSTRAINT {name} CHECK ({condition}) NOT VALID")
    op.execute(
        f"ALTER TABLE brand ADD CONSTRAINT {FOREIGN_KEY} "
        "FOREIGN KEY (name_cleared_by_account_id) REFERENCES account (id) "
        "ON DELETE SET NULL NOT VALID"
    )
    _swap_actions(NEW_ACTIONS)
    with op.get_context().autocommit_block():
        for name in (*CHECKS, FOREIGN_KEY):
            op.execute(f"ALTER TABLE brand VALIDATE CONSTRAINT {name}")
        op.create_index(
            INDEX,
            "brand",
            ["name_cleared_by_account_id"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    cleared = bind.execute(
        sa.text("SELECT count(*) FROM brand WHERE name_cleared IS NOT NULL")
    ).scalar_one()
    if cleared:
        raise RuntimeError(
            f"{cleared} brands hold an admin's clearance of their name. Dropping it "
            "would silently put them back on hold; withdraw each clearance "
            "deliberately, as the owner, if that is really intended."
        )
    logged = bind.execute(
        sa.text("SELECT count(*) FROM admin_action WHERE action IN :kinds").bindparams(
            sa.bindparam("kinds", expanding=True)
        ),
        {"kinds": list(ADDED_ACTIONS)},
    ).scalar_one()
    if logged:
        raise RuntimeError(
            f"{logged} admin log entries record clearing brand names. The log is "
            "append-only and cannot lose them; the narrower list of actions "
            "cannot hold them."
        )
    _swap_actions(OLD_ACTIONS)
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="brand", postgresql_concurrently=True, if_exists=True)
    op.execute(f"ALTER TABLE brand DROP CONSTRAINT {FOREIGN_KEY}")
    for name in CHECKS:
        op.execute(f"ALTER TABLE brand DROP CONSTRAINT {name}")
    op.drop_column("brand", "name_cleared_by_account_id")
    op.drop_column("brand", "name_cleared_at")
    op.drop_column("brand", "name_cleared")
