"""businesses.hidden_by_billing

Day 21 of an unpaid invoice hides a salon from the marketplace (docs/11 section
8). Billing recorded that decision on the subscription, but nothing carried it
to the listing, so an unpaid salon stayed listed. The worker now mirrors it
here, and the marketplace's public predicate tests it.

Its own column rather than `is_listed`, which is the owner's choice: paying a
bill must not re-advertise a business its owner hid. The `public_discovery`
policies are unchanged — they keep unpublished rows confidential, and a
business behind on its bill was published.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "businesses",
        sa.Column("hidden_by_billing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("businesses", "hidden_by_billing")
