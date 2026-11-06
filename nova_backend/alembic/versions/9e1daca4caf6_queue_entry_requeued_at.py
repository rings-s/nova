"""When a missed queue entry was put back in line.

Revision ID: 9e1daca4caf6
Revises: b2c3d4e5f6a8
Create Date: 2026-10-28 11:59:57.700411

A column on `queue_entries`, which already has forced RLS. The line is ordered
from it for a requeued entry, so it goes to the back instead of where it was.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e1daca4caf6"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add queue_entries.requeued_at."""
    op.add_column(
        "queue_entries",
        sa.Column("requeued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop queue_entries.requeued_at."""
    op.drop_column("queue_entries", "requeued_at")
