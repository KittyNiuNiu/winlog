"""create tokens table

Revision ID: ec3f02a4af39
Revises: 47ee88806d80
Create Date: 2026-11-08 19:01:26.173687

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec3f02a4af39"
down_revision: str | Sequence[str] | None = "47ee88806d80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Login tokens (issue #7). Only the SHA-256 hash of each token is stored.
    op.create_table(
        "tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_tokens_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_tokens_token_hash")),
    )
    op.create_index(op.f("ix_tokens_user_id"), "tokens", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_tokens_user_id"), table_name="tokens")
    op.drop_table("tokens")
