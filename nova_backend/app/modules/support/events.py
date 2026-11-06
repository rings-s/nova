"""Domain events for the support module."""

from dataclasses import dataclass
from uuid import UUID

from app.core.events import DomainEvent


@dataclass(frozen=True)
class FollowUpOpened(DomainEvent):
    """A person now owes a customer a reply: a new follow-up, or a resolved one reopened.

    Carries no summary or message: the outbox is not the place to copy free
    text a customer wrote. A reaction reads the follow-up itself.
    """

    tenant_id: UUID
    follow_up_id: UUID
    business_id: UUID | None
    source: str
    reason: str
