"""support · PERSISTENCE layer — the follow_ups table.

Tenant-owned under forced RLS (migration `a1b2c3d4e5f7`).

Layer rule: sqlalchemy and `app.db` only. No fastapi, no service.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.db.types import EnumValue
from app.modules.support.domain import FollowUpReason, FollowUpSource, FollowUpStatus


class FollowUp(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A customer an agent promised a person would get back to."""

    __tablename__ = "follow_ups"
    __table_args__ = (
        # One per conversation or call: a second handoff updates it.
        UniqueConstraint("tenant_id", "source", "source_ref"),
        # The inbox: open ones first, newest first.
        Index("ix_follow_ups_tenant_status_opened", "tenant_id", "status", "opened_at"),
    )

    source: Mapped[FollowUpSource] = mapped_column(
        EnumValue(FollowUpSource, length=16), nullable=False
    )
    #: The call's id, or `domain.chat_reference` for a conversation.
    source_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[FollowUpReason] = mapped_column(
        EnumValue(FollowUpReason, length=32), nullable=False
    )
    status: Mapped[FollowUpStatus] = mapped_column(
        EnumValue(FollowUpStatus, length=16), nullable=False
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: Erasing the customer erases what they asked for help with.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: The agent's own summary of the problem, when it wrote one.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The last thing the customer said before the handoff, in their words.
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: When it was opened, or last reopened.
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The staff user who resolved it.
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
