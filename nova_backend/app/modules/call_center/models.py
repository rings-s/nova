"""call_center · PERSISTENCE layer — phone lines and the calls on them.

Both tables are tenant-owned under forced RLS (migration `9c8d7e6f5a4b`).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.db.types import EnumValue
from app.modules.call_center.domain import CallDirection, CallOutcome, CallPurpose, CallStatus


class PhoneLineRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A Unifonic number that rings one business, and the agent who answers it."""

    __tablename__ = "phone_lines"
    __table_args__ = (UniqueConstraint("number_e164"),)

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    number_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ar")
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Bumped to revoke the line's webhook URL (`CallCenterService.rotate_line`).
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class VoiceCallRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    __tablename__ = "voice_calls"
    __table_args__ = (
        UniqueConstraint("tenant_id", "gateway_call_id"),
        # One reminder call per booking, however often the sweep runs.
        Index(
            "uq_voice_calls_reminder_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("purpose = 'reminder'"),
        ),
    )

    line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phone_lines.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gateway_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    direction: Mapped[CallDirection] = mapped_column(
        EnumValue(CallDirection, length=16), nullable=False
    )
    purpose: Mapped[CallPurpose] = mapped_column(EnumValue(CallPurpose, length=16), nullable=False)
    status: Mapped[CallStatus] = mapped_column(EnumValue(CallStatus, length=16), nullable=False)
    outcome: Mapped[CallOutcome | None] = mapped_column(
        EnumValue(CallOutcome, length=32), nullable=True
    )
    caller_e164: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: `domain.code_digest` of the code sent to the customer's WhatsApp.
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_cancellation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    details_offer_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reminder_answered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The last webhook delivery answered, and the answer, for a retried POST.
    last_answer_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
