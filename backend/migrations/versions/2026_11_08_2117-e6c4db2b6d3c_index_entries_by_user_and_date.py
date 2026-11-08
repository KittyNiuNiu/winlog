"""index entries by user and date

Revision ID: e6c4db2b6d3c
Revises: 685f000b996b
Create Date: 2026-11-08 21:17:00.441378

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c4db2b6d3c"
down_revision: str | Sequence[str] | None = "685f000b996b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Issue #11: listing and filtering select one user's entries by period, so filtering
    # stays fast as entries grow.
    op.create_index(op.f("ix_entries_user_id_date"), "entries", ["user_id", "date"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_entries_user_id_date"), table_name="entries")
