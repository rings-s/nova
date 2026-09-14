"""billing · DOMAIN layer — domain events.

The eight events docs/11 section 5 names. Billing publishes facts about money;
notification decides whether a WhatsApp message goes out (docs/11 section 7
step 5 wants one on every dunning attempt), and nothing here imports it.
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class SubscriptionActivated(DomainEvent):
    tenant_id: UUID
    subscription_id: UUID
    business_id: UUID
    tier: str


@dataclass(frozen=True)
class PlanChanged(DomainEvent):
    tenant_id: UUID
    subscription_id: UUID
    business_id: UUID
    previous_tier: str
    tier: str


@dataclass(frozen=True)
class SubscriptionCancelled(DomainEvent):
    tenant_id: UUID
    subscription_id: UUID
    business_id: UUID
    #: False when the salon cancelled immediately rather than at period end.
    access_until: date | None


@dataclass(frozen=True)
class CommissionAccrued(DomainEvent):
    """One booking's commission decision was recorded.

    Published for every completed booking, including the free ones — a salon
    asking "why was I not charged for that?" needs the same audit trail as one
    asking "why was I charged?".
    """

    tenant_id: UUID
    line_id: UUID
    business_id: UUID
    booking_id: UUID
    commission_class: str
    amount: str
    currency: str


@dataclass(frozen=True)
class CommissionReversed(DomainEvent):
    tenant_id: UUID
    line_id: UUID
    reverses_line_id: UUID
    business_id: UUID
    booking_id: UUID
    amount: str
    currency: str


@dataclass(frozen=True)
class InvoiceIssued(DomainEvent):
    tenant_id: UUID
    invoice_id: UUID
    business_id: UUID
    period_start: date
    period_end: date
    total_amount: str
    currency: str


@dataclass(frozen=True)
class InvoicePaid(DomainEvent):
    tenant_id: UUID
    invoice_id: UUID
    business_id: UUID
    total_amount: str
    currency: str


@dataclass(frozen=True)
class InvoiceOverdue(DomainEvent):
    """Carries the attempt number so the notification can say which reminder
    this is — docs/11 section 7 retries on days 3, 7 and 14."""

    tenant_id: UUID
    invoice_id: UUID
    business_id: UUID
    attempt: int
    listing_hidden: bool


@dataclass(frozen=True)
class PayoutSettled(DomainEvent):
    tenant_id: UUID
    payout_id: UUID
    business_id: UUID
    payout_date: date
    net_amount: str
    currency: str
