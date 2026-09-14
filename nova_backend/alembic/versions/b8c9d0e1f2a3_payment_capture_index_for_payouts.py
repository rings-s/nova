"""index payments by capture time, for the daily payout job

docs/11 section 8 settles each business daily, which means one query per day
asking for every payment captured yesterday across the whole platform. Without
this index that query is a sequential scan of every payment NOVA has ever
taken, growing forever while the job's work stays constant.

Partial on `captured_at IS NOT NULL`: the rows the payout never wants — every
pending, authorized and failed payment ever attempted — are precisely the ones
with no capture time, so they are kept out of the index rather than filtered
out of the scan.

Index only. No table, column, or data is touched, so this is safe to run
forwards and backwards on a live database.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-16

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_payments_captured_at",
        "payments",
        ["captured_at"],
        unique=False,
        postgresql_where="captured_at IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_payments_captured_at", table_name="payments")
