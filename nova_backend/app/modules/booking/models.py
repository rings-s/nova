"""booking · PERSISTENCE layer — table shape.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.

Named `BookingRecord`, not `Booking`, to keep it unmistakably distinct from the
domain entity `domain.Booking`. The repository maps between the two; nothing
else should touch this class.
"""

import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.booking.domain import BookingSource, BookingStatus


class BookingRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_tenant_provider_start", "tenant_id", "provider_id", "starts_at"),
        Index("ix_bookings_tenant_customer", "tenant_id", "customer_id"),
        Index("ix_bookings_tenant_location_start", "tenant_id", "location_id", "starts_at"),
        CheckConstraint("ends_at > starts_at", name="end_after_start"),
    )

    # Not ForeignKeys into catalog: booking reaches catalog through
    # CatalogService, never by joining its tables. A hard FK here would also
    # block soft-deleting a retired service that historical bookings reference.
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Price is captured at booking time. If the salon later reprices the
    # service, past bookings must keep what the customer actually agreed to.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")

    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False, length=32),
        nullable=False,
        default=BookingStatus.DRAFT,
        index=True,
    )
    #: The commission-bearing channel (docs/11 section 4), captured at creation
    #: and never updated. Deliberately unindexed for now: the only reader will
    #: be a monthly billing rollup that does not exist yet, and docs/08 section
    #: 18 warns against indexing ahead of a real query plan.
    source: Mapped[BookingSource] = mapped_column(
        Enum(BookingSource, name="booking_source", native_enum=False, length=32),
        nullable=False,
        default=BookingSource.DIRECT_LINK,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Free-text from the customer ("I'd like the same stylist as last time").
    #: docs/08 section 10 lists this column; it was missing.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderScheduleRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A provider's recurring weekly working hours.

    The `Schedule` aggregate from docs/03 section 3. Availability cannot be
    generated without it — before this table existed there was nothing to say
    when a salon was even open.

    Times are local wall-clock minutes from midnight, interpreted in the
    *location's* timezone (`catalog.Location.timezone`). Storing UTC here would
    be wrong: "we open at 9am" stays true across a DST change, while a stored
    UTC offset silently does not.
    """

    __tablename__ = "provider_schedules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider_id",
            "weekday",
            "start_minute",
            name="uq_provider_schedules_slot",
        ),
        Index("ix_provider_schedules_tenant_provider", "tenant_id", "provider_id"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint(
            "start_minute >= 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name="window",
        ),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: Monday = 0, matching `datetime.weekday()`.
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)


class ScheduleExceptionRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A date that overrides the weekly pattern — Eid, a holiday, an afternoon off.

    `is_closed` and a window pair are mutually exclusive in practice: closed
    means no windows, open-with-different-hours means one row per replacement
    window. Replacement rows *replace* the weekly pattern for that date rather
    than adding to it, so "closed 14:00-16:00" is expressed as two open windows.
    """

    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        Index("ix_schedule_exceptions_tenant_provider_date", "tenant_id", "provider_id", "on_date"),
        CheckConstraint(
            "is_closed OR (start_minute IS NOT NULL AND end_minute IS NOT NULL "
            "AND end_minute > start_minute)",
            name="window",
        ),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    on_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SlotHoldRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A short-lived reservation on a slot while a customer completes checkout.

    docs/04 section 2A and docs/10 section 5 require `hold_slot` before an agent
    or a payment flow can proceed — without it, two customers can both reach the
    payment step for the same 3pm appointment and one of them is refunded and
    annoyed.

    Deviation from docs/08 section 1, which lists holds under Redis: this is a
    Postgres table for the same reason `idempotency_keys` is. A hold that
    evaporates when Redis restarts sells the same slot twice, and the hold has
    to be checked in the same transaction as the insert that consumes it.

    Expiry is by timestamp rather than deletion, so an expired hold leaves
    evidence for debugging "why did my slot disappear"; the dispatcher sweeps
    them later.
    """

    __tablename__ = "slot_holds"
    __table_args__ = (
        UniqueConstraint("hold_token", name="uq_slot_holds_token"),
        Index("ix_slot_holds_tenant_provider_window", "tenant_id", "provider_id", "starts_at"),
        Index("ix_slot_holds_expiry", "expires_at"),
        Index("ix_slot_holds_tenant_held_by", "tenant_id", "held_by", "expires_at"),
        CheckConstraint("ends_at > starts_at", name="end_after_start"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: Null for an anonymous PWA checkout that has not identified itself yet.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: Who took the hold: the principal's subject id. A customer may hold only a
    #: few slots at a tenant at once (`BookingService.hold_slot`), so one
    #: account cannot keep a salon's calendar blocked. Null only on holds taken
    #: before holders were recorded (migration `f1a2b3c4d5e6`).
    held_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Opaque bearer token. Whoever holds it may convert the hold into a booking.
    hold_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
