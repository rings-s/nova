"""billing · PERSISTENCE layer — table shape.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.

Money is `NUMERIC(12, 2)` and rates are `NUMERIC(5, 2)`, per docs/11 section
10. Wider than the `NUMERIC(10, 2)` used for a single booking's price because
these columns hold a whole month of a chain's takings.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.billing.domain import (
    CommissionClass,
    CommissionLineStatus,
    InvoiceStatus,
    PlanTier,
    SubscriptionStatus,
)

_MONEY = Numeric(12, 2)
_RATE = Numeric(5, 2)


class SubscriptionRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """What plan a business is on (docs/11 section 5)."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        # "A subscription belongs to exactly one tenant" — and one business.
        # Unique rather than merely indexed: two subscriptions for one business
        # means two answers to "what rate does this booking accrue at".
        UniqueConstraint("business_id", name="uq_subscriptions_business"),
        Index("ix_subscriptions_tenant_status", "tenant_id", "status"),
        CheckConstraint("seats >= 1", name="seats_positive"),
        CheckConstraint("locations >= 1", name="locations_positive"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tier: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier", native_enum=False, length=32), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False, length=32),
        nullable=False,
        default=SubscriptionStatus.TRIALING,
    )

    current_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    current_period_end: Mapped[date] = mapped_column(Date, nullable=False)

    seats: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    locations: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    annual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    trial_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: A negotiated Chain rate. Null means the published price list applies.
    negotiated_monthly_price: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)

    #: docs/11 section 7 step 6 — the ONLY consequence of non-payment.
    marketplace_listing_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CustomerBusinessFirstBookingRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """The row that makes "new exactly once" true.

    docs/11 section 10 asks for this by name: "Unique index on (business_id,
    customer_id) ... this is what makes 'new exactly once' enforceable at the
    database level, not just in code."

    That wording is the whole design. A `SELECT ... IF NOT EXISTS INSERT` loses
    the race docs/11 section 11 explicitly tests for — "two concurrent first
    bookings for the same customer produce exactly one billable line". The
    accrual path therefore *attempts the insert* and treats the
    `UniqueViolation` as the answer, rather than asking first.
    """

    __tablename__ = "customer_business_first_bookings"
    __table_args__ = (
        UniqueConstraint("business_id", "customer_id", name="uq_first_booking_business_customer"),
        Index("ix_first_bookings_tenant_business", "tenant_id", "business_id"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    #: Which booking claimed the slot, kept so a disputed charge can be traced
    #: to the appointment that caused it.
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    first_completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommissionLineRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """One booking's commission decision. Append-only (docs/11 section 10)."""

    __tablename__ = "commission_lines"
    __table_args__ = (
        # One accrual per booking. A redelivered `BookingCompleted` from the
        # at-least-once outbox must not bill the same appointment twice.
        # Partial, so the reversal row for that booking is still insertable.
        Index(
            "uq_commission_lines_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("is_reversal = false"),
        ),
        Index("ix_commission_lines_tenant_invoice", "tenant_id", "invoice_id"),
        Index("ix_commission_lines_tenant_business_status", "tenant_id", "business_id", "status"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("rate_pct >= 0", name="rate_non_negative"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    #: The `BookingSource` in force at completion, copied rather than joined —
    #: this row must stay readable when the booking is long archived.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    commission_class: Mapped[CommissionClass] = mapped_column(
        Enum(CommissionClass, name="commission_class", native_enum=False, length=32),
        nullable=False,
    )

    base_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(_RATE, nullable=False)
    amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")

    status: Mapped[CommissionLineStatus] = mapped_column(
        Enum(CommissionLineStatus, name="commission_line_status", native_enum=False, length=32),
        nullable=False,
        default=CommissionLineStatus.DRAFT,
    )

    reversed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_reversal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reverses_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commission_lines.id"), nullable=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True
    )
    accrued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InvoiceRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A closed month. Immutable once issued (docs/11 section 5)."""

    __tablename__ = "invoices"
    __table_args__ = (
        # docs/11 section 10: "Unique index on (business_id, period_start)".
        # This is also what makes issuance idempotent — a monthly close that
        # runs twice inserts once.
        UniqueConstraint("business_id", "period_start", name="uq_invoices_business_period"),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
        Index("ix_invoices_status_due", "status", "due_at"),
        CheckConstraint("period_end > period_start", name="period_end_after_start"),
        CheckConstraint("total_amount >= 0", name="total_non_negative"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status", native_enum=False, length=32),
        nullable=False,
        default=InvoiceStatus.DRAFT,
    )

    subscription_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=Decimal("0.00")
    )
    #: Can be negative: a month whose only activity was reversing last month's
    #: bookings owes less than nothing in commission. The other three columns
    #: cannot.
    commission_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=Decimal("0.00")
    )
    processing_amount: Mapped[Decimal] = mapped_column(
        _MONEY, nullable=False, default=Decimal("0.00")
    )
    vat_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dunning_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: The Moyasar payment collecting this invoice (docs/11 section 7 step 4).
    gateway_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PayoutRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """One day's settlement to a business (docs/11 section 8)."""

    __tablename__ = "payouts"
    __table_args__ = (
        # Daily payouts: one per business per day, which also makes the daily
        # job idempotent if it runs twice.
        UniqueConstraint("business_id", "payout_date", name="uq_payouts_business_date"),
        Index("ix_payouts_tenant_date", "tenant_id", "payout_date"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payout_date: Mapped[date] = mapped_column(Date, nullable=False)

    collected_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    processing_fee: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    commission_netted: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")

    #: "Every payout references its bookings and is exportable as CSV for the
    #: business's accountant" (docs/11 section 8). An array rather than a join
    #: table: it is written once, read whole, and never queried by element.
    booking_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
