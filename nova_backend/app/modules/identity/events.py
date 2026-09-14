"""Domain events for the identity module.

Emitted through `app.core.events.publish_event`, which writes them to the
transactional outbox in the same transaction as the change they describe.
"""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class TenantCreated(DomainEvent):
    tenant_id: UUID


@dataclass(frozen=True)
class CustomerRegistered(DomainEvent):
    tenant_id: UUID
    customer_id: UUID
    phone: str
