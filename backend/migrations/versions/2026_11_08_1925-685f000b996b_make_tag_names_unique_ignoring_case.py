"""make tag names unique ignoring case

Revision ID: 685f000b996b
Revises: ec3f02a4af39
Create Date: 2026-11-08 19:25:58.116482

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "685f000b996b"
down_revision: str | Sequence[str] | None = "ec3f02a4af39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Issue #8: tag names are unique per user regardless of case, so `python` and `Python`
    # are the same tag. Lookups compare lower(name) in the same way. The index also enforces
    # the old exact-name rule, so the old unique constraint is dropped.
    op.create_index(
        "uq_tags_user_id_lower_name",
        "tags",
        ["user_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.drop_constraint(op.f("uq_tags_user_id_name"), "tags", type_="unique")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint(op.f("uq_tags_user_id_name"), "tags", ["user_id", "name"])
    op.drop_index("uq_tags_user_id_lower_name", table_name="tags")
