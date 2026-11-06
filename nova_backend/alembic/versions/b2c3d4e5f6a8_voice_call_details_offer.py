"""Sara's offer to send a booking's details on WhatsApp (press 3).

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-10-23 15:00:00.000000

A column on `voice_calls`, which already has forced RLS.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a8"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add voice_calls.details_offer_booking_id."""
    op.add_column(
        "voice_calls",
        sa.Column("details_offer_booking_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    """Drop voice_calls.details_offer_booking_id."""
    op.drop_column("voice_calls", "details_offer_booking_id")
