"""queue · DOMAIN layer — domain events.

Queue never imports notification. It publishes a fact; the notification module
reacts to it (see nova_backend/README.md, "Cross-module calls").
"""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class QueueEntryJoined(DomainEvent):
    tenant_id: UUID
    queue_id: UUID
    entry_id: UUID
    customer_id: UUID
    source: str


@dataclass(frozen=True)
class CustomerCalled(DomainEvent):
    """The one event a customer genuinely wants pushed to their phone."""

    tenant_id: UUID
    queue_id: UUID
    entry_id: UUID
    customer_id: UUID
    position: int


@dataclass(frozen=True)
class CustomerCheckedIn(DomainEvent):
    tenant_id: UUID
    queue_id: UUID
    entry_id: UUID
    customer_id: UUID


@dataclass(frozen=True)
class QueueEntryMissed(DomainEvent):
    tenant_id: UUID
    queue_id: UUID
    entry_id: UUID
    customer_id: UUID


@dataclass(frozen=True)
class TicketIssued(DomainEvent):
    tenant_id: UUID
    ticket_id: UUID
    booking_id: UUID | None
    queue_entry_id: UUID | None
