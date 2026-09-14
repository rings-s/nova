"""record who holds a slot, so a customer's holds can be capped

SEC-05 of the 2026-09-15 security audit. `POST /bookings/holds` recorded no
holder, and nothing limited how many slots one account held: a customer could
keep a salon's calendar blocked by re-holding every slot as its hold expired.

`held_by` is the principal's subject id. `BookingService.hold_slot` counts a
customer's live holds at a business by it, under an advisory lock per holder.
It is null only on holds taken before this migration, which expire within
minutes.

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-09-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("slot_holds", sa.Column("held_by", sa.UUID(), nullable=True))
    op.create_index(
        "ix_slot_holds_tenant_held_by", "slot_holds", ["tenant_id", "held_by", "expires_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_slot_holds_tenant_held_by", table_name="slot_holds")
    op.drop_column("slot_holds", "held_by")
