"""push tokens follow their session (D-116)

Ending a session (D-114) left its phone registered for push, so once push
is delivered (E1) a phone logged out from elsewhere would keep showing the
account's deals and payments. Approved by Adhi on 24 October 2026 (D-116).
This migration:

- adds `device_token.session_id`, the family id of the session that last
  registered the token. Nullable, no default, so adding it rewrites
  nothing; tokens registered before it stay NULL until their phone
  registers again, which the apps do on every start. Not a foreign key: a
  session family is not a row of its own;
- indexes it, only where it is set, built CONCURRENTLY outside the
  transaction, so writes to the table are never blocked.

Data impact: none on existing rows.

Downgrade: drops the index and the column. The link is lost and tokens fall
back to being removed only on logging out of that phone or everywhere,
which is how they behaved before; nothing a person gave us is lost.

Revision ID: ecb64002aa29
Revises: de322e936678
Create Date: 2026-10-24 21:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ecb64002aa29"
down_revision: Union[str, None] = "de322e936678"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ix_device_token_session_id"


def upgrade() -> None:
    op.add_column("device_token", sa.Column("session_id", sa.UUID(), nullable=True))
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "device_token",
            ["session_id"],
            unique=False,
            postgresql_where=sa.text("session_id IS NOT NULL"),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            INDEX, table_name="device_token", postgresql_concurrently=True, if_exists=True
        )
    op.drop_column("device_token", "session_id")
