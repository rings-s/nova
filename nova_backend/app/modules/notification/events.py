"""notification · DOMAIN layer — domain events."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class NotificationSent(DomainEvent):
    tenant_id: UUID
    notification_id: UUID
    customer_id: UUID
    template: str


@dataclass(frozen=True)
class NotificationSuppressed(DomainEvent):
    """A message we were not permitted to send.

    Emitted so consent suppression is visible in analytics rather than looking
    like a delivery gap — a salon seeing 40% of its reminders suppressed has a
    consent-collection problem, not a WhatsApp problem.
    """

    tenant_id: UUID
    notification_id: UUID
    customer_id: UUID
    reason: str
