"""payment gateway invoice id

`payments.gateway_invoice_id`: the Moyasar invoice (hosted checkout) a payment
was opened as. A checkout is paid by a Moyasar *payment* whose id NOVA learns
only when it arrives, so the invoice id is how a `payment_paid` webhook, or a
payer returning from checkout, finds its way back to the row.

Unique where set and not tenant-scoped, like `gateway_payment_id`: the webhook
looks it up before it knows the tenant. The table already has its forced
`tenant_isolation` policy; adding a column does not change it.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-23 05:07:40
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("gateway_invoice_id", sa.String(length=255), nullable=True))
    op.create_index(
        "uq_payments_gateway_invoice_id",
        "payments",
        ["gateway_invoice_id"],
        unique=True,
        postgresql_where=sa.text("gateway_invoice_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_payments_gateway_invoice_id",
        table_name="payments",
        postgresql_where=sa.text("gateway_invoice_id IS NOT NULL"),
    )
    op.drop_column("payments", "gateway_invoice_id")
