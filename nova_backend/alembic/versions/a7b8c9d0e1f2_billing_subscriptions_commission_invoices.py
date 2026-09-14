"""create the billing tables: subscriptions, commission, invoices, payouts

Implements docs/11 section 10. Five tables, all tenant-scoped and all under the
same RLS policy as everything else — a salon must never read another salon's
invoices, and billing data is the most sensitive thing on the platform.

Three indexes here are load-bearing rather than performance tuning:

  - `uq_first_booking_business_customer` is what makes "a customer is charged
    as new exactly once, per business, forever" (docs/11 section 3) true under
    concurrency. The accrual path INSERTs against it and reads the row count
    for its answer; a SELECT-then-INSERT would lose the race that docs/11
    section 11 explicitly tests for.
  - `uq_invoices_business_period` makes the monthly close idempotent per
    (business, period), which section 10 requires by name.
  - `uq_commission_lines_booking` is partial on `is_reversal = false`, so one
    booking accrues at most one commission line while still leaving room for
    its reversal row. Without it a redelivered `BookingCompleted` from the
    at-least-once outbox bills the same appointment twice.

Money is NUMERIC(12, 2) and rates NUMERIC(5, 2), per section 10. Never floats.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(12, 2)
_RATE = sa.Numeric(5, 2)

#: Every table here carries tenant_id and needs the policy from d4e5f6a7b8c9.
_TENANT_TABLES = (
    "subscriptions",
    "customer_business_first_bookings",
    "commission_lines",
    "invoices",
    "payouts",
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_period_start", sa.Date(), nullable=False),
        sa.Column("current_period_end", sa.Date(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("locations", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("annual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("trial_ends_at", sa.Date(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("negotiated_monthly_price", _MONEY, nullable=True),
        sa.Column(
            "marketplace_listing_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_subscriptions"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_subscriptions_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("business_id", name="uq_subscriptions_business"),
        sa.CheckConstraint("seats >= 1", name="ck_subscriptions_seats_positive"),
        sa.CheckConstraint("locations >= 1", name="ck_subscriptions_locations_positive"),
    )
    op.create_index(op.f("ix_subscriptions_tenant_id"), "subscriptions", ["tenant_id"])
    op.create_index(
        "ix_subscriptions_tenant_status", "subscriptions", ["tenant_id", "status"]
    )

    # The "new exactly once" gate. This table exists for its unique constraint.
    op.create_table(
        "customer_business_first_bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("first_completed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_customer_business_first_bookings"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_customer_business_first_bookings_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "business_id", "customer_id", name="uq_first_booking_business_customer"
        ),
    )
    op.create_index(
        op.f("ix_customer_business_first_bookings_tenant_id"),
        "customer_business_first_bookings",
        ["tenant_id"],
    )
    op.create_index(
        "ix_first_bookings_tenant_business",
        "customer_business_first_bookings",
        ["tenant_id", "business_id"],
    )

    # Invoices before commission_lines: the line carries an FK into it.
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("subscription_amount", _MONEY, nullable=False, server_default="0"),
        # Deliberately allowed to be negative: a month whose only activity was
        # reversing last month's bookings owes less than nothing in commission.
        sa.Column("commission_amount", _MONEY, nullable=False, server_default="0"),
        sa.Column("processing_amount", _MONEY, nullable=False, server_default="0"),
        sa.Column("vat_amount", _MONEY, nullable=False, server_default="0"),
        sa.Column("total_amount", _MONEY, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="SAR"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dunning_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gateway_payment_id", sa.String(length=255), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_invoices_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("business_id", "period_start", name="uq_invoices_business_period"),
        sa.CheckConstraint("period_end > period_start", name="ck_invoices_period_end_after_start"),
        sa.CheckConstraint("total_amount >= 0", name="ck_invoices_total_non_negative"),
    )
    op.create_index(op.f("ix_invoices_tenant_id"), "invoices", ["tenant_id"])
    op.create_index("ix_invoices_tenant_status", "invoices", ["tenant_id", "status"])
    op.create_index("ix_invoices_status_due", "invoices", ["status", "due_at"])

    op.create_table(
        "commission_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("commission_class", sa.String(length=32), nullable=False),
        sa.Column("base_amount", _MONEY, nullable=False),
        sa.Column("rate_pct", _RATE, nullable=False),
        sa.Column("amount", _MONEY, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="SAR"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reversed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_reversal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reverses_line_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accrued_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_commission_lines"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_commission_lines_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reverses_line_id"],
            ["commission_lines.id"],
            name="fk_commission_lines_reverses_line_id_commission_lines",
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            name="fk_commission_lines_invoice_id_invoices",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_commission_lines_amount_non_negative"),
        sa.CheckConstraint("rate_pct >= 0", name="ck_commission_lines_rate_non_negative"),
    )
    op.create_index(op.f("ix_commission_lines_tenant_id"), "commission_lines", ["tenant_id"])
    op.create_index(
        "ix_commission_lines_tenant_invoice", "commission_lines", ["tenant_id", "invoice_id"]
    )
    op.create_index(
        "ix_commission_lines_tenant_business_status",
        "commission_lines",
        ["tenant_id", "business_id", "status"],
    )
    # Partial: one accrual per booking, while the reversal row stays insertable.
    op.create_index(
        "uq_commission_lines_booking",
        "commission_lines",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("is_reversal = false"),
    )

    op.create_table(
        "payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payout_date", sa.Date(), nullable=False),
        sa.Column("collected_amount", _MONEY, nullable=False),
        sa.Column("processing_fee", _MONEY, nullable=False),
        sa.Column("commission_netted", _MONEY, nullable=False),
        sa.Column("net_amount", _MONEY, nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="SAR"),
        sa.Column(
            "booking_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_payouts"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_payouts_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("business_id", "payout_date", name="uq_payouts_business_date"),
    )
    op.create_index(op.f("ix_payouts_tenant_id"), "payouts", ["tenant_id"])
    op.create_index("ix_payouts_tenant_date", "payouts", ["tenant_id", "payout_date"])

    # Same RLS policy as every other tenant-owned table (d4e5f6a7b8c9).
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                current_setting('app.bypass_rls', true) = 'on'
                OR tenant_id::text = current_setting('app.current_tenant_id', true)
            )
            WITH CHECK (
                current_setting('app.bypass_rls', true) = 'on'
                OR tenant_id::text = current_setting('app.current_tenant_id', true)
            )
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.drop_table("payouts")
    op.drop_table("commission_lines")
    op.drop_table("invoices")
    op.drop_table("customer_business_first_bookings")
    op.drop_table("subscriptions")
