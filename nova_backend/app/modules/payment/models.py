"""payment · PERSISTENCE layer — table shape.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.payment.domain import PaymentStatus


class PaymentRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """Money owed or taken, per docs/08 section 14."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_payments_tenant_status", "tenant_id", "status"),
        # Not tenant-scoped: the webhook handler arrives knowing only the
        # gateway's own id and has to find the payment before it knows which
        # tenant it belongs to. Unique because two payments sharing one gateway
        # id would make that lookup ambiguous — and ambiguity here means
        # crediting the wrong booking.
        Index(
            "uq_payments_gateway_payment_id",
            "gateway_payment_id",
            unique=True,
            postgresql_where=text("gateway_payment_id IS NOT NULL"),
        ),
        # The daily payout job (docs/11 section 8) asks for one day's captures
        # across every tenant. Partial, because the rows it never wants — every
        # pending and failed payment ever attempted — are exactly the ones with
        # no capture time.
        Index(
            "ix_payments_captured_at",
            "captured_at",
            postgresql_where=text("captured_at IS NOT NULL"),
        ),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= amount",
            name="refund_within_amount",
        ),
    )

    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00")
    )

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False, length=32),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    gateway: Mapped[str] = mapped_column(String(50), nullable=False, default="moyasar")
    gateway_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: True only once a *signature-verified* webhook moved this payment. A
    #: client-side redirect claiming success never sets it.
    webhook_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_code: Mapped[str | None] = mapped_column(String(255), nullable=True)

    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefundRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """One refund. Separate rows, never a mutation of the payment.

    docs/07 section 8 requires this: overwriting the original amount destroys
    the record of what the customer was actually charged, which is exactly what
    a chargeback dispute needs.
    """

    __tablename__ = "payment_refunds"
    __table_args__ = (
        Index("ix_payment_refunds_tenant_payment", "tenant_id", "payment_id"),
        UniqueConstraint("gateway_refund_id", name="uq_payment_refunds_gateway_id"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    gateway_refund_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class WebhookEventRecord(Base, UUIDPKMixin):
    """Every inbound webhook, stored raw, per docs/08 section 17.

    Deliberately NOT tenant-owned: a webhook arrives before we know which
    tenant it concerns, and the unique constraint that makes delivery
    idempotent has to be global. The tenant is recorded once resolved.

    The unique (provider, external_event_id) index is the actual dedupe
    mechanism — Moyasar retries, and without it a retried `payment.captured`
    would refund-cycle or double-confirm a booking.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        Index(
            "ix_webhook_provider_external_id",
            "provider",
            "external_event_id",
            unique=True,
        ),
        Index("ix_webhook_events_unprocessed", "processed_at"),
    )

    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
