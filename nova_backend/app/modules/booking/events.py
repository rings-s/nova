"""booking · DOMAIN layer — domain events.

These are how booking talks to the rest of the system. Booking never imports
notification or payment; it publishes a fact and they react (see
nova_backend/README.md, "Cross-module calls").
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class BookingCreated(DomainEvent):
    tenant_id: UUID
    booking_id: UUID
    customer_id: UUID
    starts_at: datetime


@dataclass(frozen=True)
class BookingConfirmed(DomainEvent):
    tenant_id: UUID
    booking_id: UUID
    customer_id: UUID
    starts_at: datetime


@dataclass(frozen=True)
class BookingCancelled(DomainEvent):
    tenant_id: UUID
    booking_id: UUID
    customer_id: UUID
    reason: str | None


@dataclass(frozen=True)
class BookingRescheduled(DomainEvent):
    """Carries the old time as well as the new one.

    The notification template needs both — "moved from 3pm to 5pm" is useful,
    "moved to 5pm" makes the customer go and look it up.
    """

    tenant_id: UUID
    booking_id: UUID
    customer_id: UUID
    previous_starts_at: datetime
    starts_at: datetime


@dataclass(frozen=True)
class BookingCompleted(DomainEvent):
    tenant_id: UUID
    booking_id: UUID
    customer_id: UUID


@dataclass(frozen=True)
class BookingNoShow(DomainEvent):
    tenant_id: UUID
    booking_id: UUID
    customer_id: UUID


@dataclass(frozen=True)
class SlotReleased(DomainEvent):
    """A blocking booking became terminal, so its time is bookable again."""

    tenant_id: UUID
    provider_id: UUID
    starts_at: datetime
    ends_at: datetime
