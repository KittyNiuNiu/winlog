"""create global AI usage table

Revision ID: 113dfac7accf
Revises: e6c4db2b6d3c
Create Date: 2026-11-09 09:05:25.591233

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "113dfac7accf"
down_revision: str | Sequence[str] | None = "e6c4db2b6d3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Issue #15: the global daily AI cap is counted here, one row per UTC day. No user id and
    # no other personal data, so deleting an account does not lower the day's count.
    op.create_table(
        "ai_usage_global",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("request_count >= 0", name=op.f("ck_ai_usage_global_request_count")),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_ai_usage_global")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ai_usage_global")
