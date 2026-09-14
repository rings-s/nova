"""notification · PERSISTENCE layer — table shape.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.notification.domain import (
    MessageTemplate,
    NotificationChannel,
    NotificationStatus,
)


class NotificationRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """One outbound message and what became of it."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_notifications_tenant_status", "tenant_id", "status"),
        Index("ix_notifications_scheduled", "status", "scheduled_for"),
        # The idempotency key for delivery. The outbox delivers at-least-once,
        # so the same BookingConfirmed can arrive twice; without this the
        # customer gets two identical WhatsApp messages.
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_notifications_tenant_dedupe"),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel", native_enum=False, length=32),
        nullable=False,
        default=NotificationChannel.WHATSAPP,
    )
    template: Mapped[MessageTemplate] = mapped_column(
        Enum(MessageTemplate, name="notification_template", native_enum=False, length=64),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status", native_enum=False, length=32),
        nullable=False,
        default=NotificationStatus.PENDING,
    )

    #: Template variables only — never the whole event context. See
    #: `domain.render_template_params` for why.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    #: Stable per (event, customer, template), so a redelivered event maps to
    #: the same row instead of a second message.
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)

    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The earliest this message may go out. Always set — `now` for an ordinary
    #: transactional message, the opening of the window for one quiet hours
    #: held back, and `now + backoff` while a failed send is being retried.
    #:
    #: It used to be nullable and set *only* by the quiet-hours branch, which
    #: meant every transactional row stored NULL while the only reader filtered
    #: `scheduled_for IS NOT NULL`. Nothing was ever delivered. A nullable
    #: column carrying two meanings is what made that possible, so it now
    #: carries one. No `server_default`: the application is the sole writer, and
    #: a default would both hide a missing assignment and make autogenerate
    #: propose it forever.
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
