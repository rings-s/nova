"""review · PERSISTENCE layer — the reviews table.

Layer rule: sqlalchemy and `app.db` only. No fastapi, no service, no domain.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin


class Review(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """One customer's rating of one completed booking."""

    __tablename__ = "reviews"
    __table_args__ = (
        # One review per visit. The service checks first for a clear error;
        # this is what holds under two concurrent submissions.
        Index("uq_reviews_booking_id", "booking_id", unique=True),
        # The staff list: a business's reviews, newest first.
        Index("ix_reviews_tenant_business_created", "tenant_id", "business_id", "created_at"),
        # "Which of my bookings have I rated?" for the customer's list.
        Index("ix_reviews_tenant_customer", "tenant_id", "customer_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: Staff-only. See the module docstring for why it is never public.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
