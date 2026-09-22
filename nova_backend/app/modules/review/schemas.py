"""review · DELIVERY layer — request and response shapes."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.review.domain import MAX_COMMENT_LENGTH, MAX_RATING, MIN_RATING


class SubmitReviewRequest(ApiSchema):
    booking_id: UUID
    rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)


class MyReviewOut(ApiSchema):
    """What a customer sees of their own review."""

    id: UUID
    booking_id: UUID
    business_id: UUID
    rating: int
    comment: str | None
    created_at: datetime


class ReviewOut(MyReviewOut):
    """The staff view, with where and by whom the visit happened."""

    location_id: UUID
    provider_id: UUID
    customer_id: UUID
