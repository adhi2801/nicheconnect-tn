"""sign-in acknowledged (D-120)

A new sign-in leads the owner's attention list for 7 days (D-114), even
when it was the owner's own; they had no "it was me". Approved by Adhi on
24 October 2026 (D-120). This migration adds
`auth_session.sign_in_acknowledged_at`: when the owner said the sign-in was
theirs, from a session that signed in before it. Nullable, no default, so
adding it rewrites nothing.

Data impact: none on existing rows.

Downgrade: drops the column. Sign-ins already acknowledged would show again
for the rest of their 7 days; nothing a person gave us is lost.

Revision ID: c80694db3a26
Revises: 82bb81b5eed4
Create Date: 2026-10-24 23:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c80694db3a26"
down_revision: Union[str, None] = "82bb81b5eed4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_session",
        sa.Column("sign_in_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_session", "sign_in_acknowledged_at")
