"""Domain events for the discovery module."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class MarketplaceReferralRecorded(DomainEvent):
    """A customer opened a storefront from the marketplace.

    Emitted for the question the commercial model turns on — how many clicks a
    listing converts — which bookings alone cannot answer, because a click that
    never books leaves no other trace.
    """

    tenant_id: UUID
    business_id: UUID
    referral_id: UUID
