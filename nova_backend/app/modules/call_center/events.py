"""call_center · DOMAIN layer — domain events."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class BookingDetailsRequested(DomainEvent):
    """Send the caller the details of a booking Sara made: when, where, the
    ticket link, and that the business will confirm it.

    Published only once the customer has WhatsApp consent, recorded in the same
    transaction when the caller pressed 3 for it. The notification module still
    checks consent when it enqueues the message.
    """

    tenant_id: UUID
    call_id: UUID
    booking_id: UUID
    customer_id: UUID


@dataclass(frozen=True)
class CallbackRequested(DomainEvent):
    """Sara promised a call back from the business, and opened the follow-up for it.

    No summary: the outbox is not the place to copy what a caller said. The
    follow-up (`support`) holds it.
    """

    tenant_id: UUID
    call_id: UUID
    business_id: UUID
    customer_id: UUID | None
    follow_up_id: UUID
    reason: str
