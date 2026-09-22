"""Domain events for the review module."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class ReviewSubmitted(DomainEvent):
    """A customer rated a completed visit.

    Carries the rating but not the comment: the outbox is not the place to
    copy free text a customer wrote about a person.
    """

    tenant_id: UUID
    review_id: UUID
    business_id: UUID
    booking_id: UUID
    provider_id: UUID
    rating: int
