"""payment · DOMAIN layer — domain events.

Amounts are carried as strings, not floats or Decimals: the outbox payload is
JSONB, and a Decimal serialised through JSON becomes a float somewhere along
the way. Money that round-trips through a binary float is money that quietly
loses fils.
"""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class PaymentIntentCreated(DomainEvent):
    tenant_id: UUID
    payment_id: UUID
    booking_id: UUID | None
    amount: str
    currency: str


@dataclass(frozen=True)
class PaymentCaptured(DomainEvent):
    """The event that confirms a booking. Only ever raised after verification."""

    tenant_id: UUID
    payment_id: UUID
    booking_id: UUID | None
    amount: str
    currency: str


@dataclass(frozen=True)
class PaymentFailed(DomainEvent):
    tenant_id: UUID
    payment_id: UUID
    booking_id: UUID | None
    failure_code: str | None


@dataclass(frozen=True)
class PaymentRefunded(DomainEvent):
    tenant_id: UUID
    payment_id: UUID
    booking_id: UUID | None
    amount: str
    currency: str
