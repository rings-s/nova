"""queue · PERSISTENCE layer — table shape.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.

Named `...Record` to stay unmistakably distinct from the domain entities in
`domain.py`. The repository maps between the two.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.queue.domain import QueueEntrySource, QueueEntryStatus, TicketStatus


class QueueRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """A live queue at one branch, per docs/08 section 11."""

    __tablename__ = "queues"
    __table_args__ = (
        Index("ix_queues_tenant_location", "tenant_id", "location_id"),
        # One open queue per location per name: two queues called "Main Queue"
        # at one branch is always a mistake, and it silently splits the line.
        UniqueConstraint("tenant_id", "location_id", "name_en", name="uq_queues_tenant_loc_name"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False, default="Main Queue")
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False, default="الطابور الرئيسي")
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    #: Feeds the customer-facing wait estimate. Per-queue rather than global —
    #: a barber queue and a spa queue move at very different speeds.
    average_service_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)


class QueueEntryRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """One customer's place in a queue, per docs/08 section 12."""

    __tablename__ = "queue_entries"
    __table_args__ = (
        Index(
            "ix_queue_entries_tenant_queue_status_position",
            "tenant_id",
            "queue_id",
            "status",
            "position",
        ),
        Index("ix_queue_entries_tenant_customer", "tenant_id", "customer_id"),
        UniqueConstraint("queue_id", "position", name="uq_queue_entries_queue_position"),
        CheckConstraint("party_size BETWEEN 1 AND 20", name="party_size"),
    )

    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    #: Set when the entry came from an appointment, so the two share one
    #: timeline (docs/03 section 4) instead of being tracked separately.
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[QueueEntryStatus] = mapped_column(
        Enum(QueueEntryStatus, name="queue_entry_status", native_enum=False, length=32),
        nullable=False,
        default=QueueEntryStatus.WAITING,
        index=True,
    )
    source: Mapped[QueueEntrySource] = mapped_column(
        Enum(QueueEntrySource, name="queue_entry_source", native_enum=False, length=32),
        nullable=False,
        default=QueueEntrySource.WALK_IN,
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A virtual QR ticket, per docs/08 section 13.

    `qr_token_hash` — never the token itself. Someone who reads this table
    cannot reconstruct a working QR code, which is the whole point of hashing
    it (docs/08 section 1: "do not store raw QR secrets in plain text").
    """

    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("ticket_code", name="uq_tickets_code"),
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_tickets_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_tickets_tenant_queue_entry", "tenant_id", "queue_entry_id"),
        CheckConstraint(
            "booking_id IS NOT NULL OR queue_entry_id IS NOT NULL",
            name="has_subject",
        ),
    )

    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    queue_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queue_entries.id", ondelete="CASCADE"), nullable=True
    )

    #: Short, human-readable, safe to call out across a salon floor.
    ticket_code: Mapped[str] = mapped_column(String(100), nullable=False)
    qr_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status", native_enum=False, length=32),
        nullable=False,
        default=TicketStatus.ACTIVE,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
