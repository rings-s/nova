"""notification · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only.
"""

from datetime import datetime
from uuid import UUID

from app.core.schemas import ApiSchema
from app.modules.notification.domain import (
    MessageTemplate,
    NotificationChannel,
    NotificationStatus,
)


class NotificationOut(ApiSchema):
    id: UUID
    customer_id: UUID
    channel: NotificationChannel
    template: MessageTemplate
    status: NotificationStatus
    #: Present when quiet hours held a marketing message back.
    scheduled_for: datetime | None
    sent_at: datetime | None
    error: str | None
    created_at: datetime

    # No `payload`: it holds the customer's name and appointment details, and
    # this endpoint is a delivery log, not a message archive.
