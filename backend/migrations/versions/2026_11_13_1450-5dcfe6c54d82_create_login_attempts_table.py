"""create login attempts table

Revision ID: 5dcfe6c54d82
Revises: 113dfac7accf
Create Date: 2026-11-13 14:50:12.688485

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5dcfe6c54d82"
down_revision: str | Sequence[str] | None = "113dfac7accf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Issue #46 (FR-A4): failed logins per email and demo-logins per visitor IP, counted per
    # window. The email or IP is stored only as its SHA-256 hash, never in plain text. Rows
    # whose window has ended are deleted when new attempts are written.
    op.create_table(
        "login_attempts",
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('login', 'demo')", name=op.f("ck_login_attempts_kind")),
        sa.CheckConstraint("attempt_count >= 0", name=op.f("ck_login_attempts_attempt_count")),
        sa.PrimaryKeyConstraint("kind", "key_hash", name=op.f("pk_login_attempts")),
    )
    op.create_index(
        op.f("ix_login_attempts_window_start"), "login_attempts", ["window_start"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_login_attempts_window_start"), table_name="login_attempts")
    op.drop_table("login_attempts")
