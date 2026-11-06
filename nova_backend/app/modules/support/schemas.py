"""support · DELIVERY layer — request and response shapes."""

from datetime import datetime
from uuid import UUID

from app.core.schemas import ApiSchema


class FollowUpOut(ApiSchema):
    id: UUID
    source: str
    reason: str
    status: str
    business_id: UUID | None
    customer_id: UUID | None
    booking_id: UUID | None
    contact_name: str | None
    contact_phone: str | None
    contact_email: str | None
    summary: str | None
    customer_message: str | None
    opened_at: datetime
    resolved_at: datetime | None


class FollowUpCountOut(ApiSchema):
    open: int
