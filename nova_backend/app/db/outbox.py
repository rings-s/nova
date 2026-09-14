"""The transactional outbox table and its dispatcher queries.

Lives in `app/db/` rather than a module because every module publishes into it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPKMixin

#: Retry backoff per attempt, in seconds. After the last entry the event is
#: parked as `failed` for a human to look at rather than retried forever.
_BACKOFF_SECONDS = (10, 60, 300, 1800, 7200)
MAX_ATTEMPTS = len(_BACKOFF_SECONDS)


class OutboxEvent(Base, UUIDPKMixin):
    """One domain event, awaiting delivery.

    Not `TenantOwnedMixin`: `tenant_id` is nullable here (some events are
    platform-level) and there must be no FK cascade — deleting a tenant must
    not silently erase the audit trail of what happened to it.
    """

    __tablename__ = "domain_events"
    __table_args__ = (
        # The dispatcher's hot path: unpublished events that are due.
        Index(
            "ix_domain_events_pending",
            "available_at",
            # `text()`, not `Text()` — the latter is the column type and only
            # rendered correctly here by accident.
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_domain_events_tenant", "tenant_id"),
    )

    event_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: When the dispatcher may next attempt this event.
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def schedule_retry(self, error: str) -> None:
        self.attempts += 1
        self.last_error = error[:2000]
        if self.attempts < MAX_ATTEMPTS:
            delay = _BACKOFF_SECONDS[self.attempts - 1]
            self.available_at = datetime.now(UTC) + timedelta(seconds=delay)
        else:
            # Park it far in the future rather than deleting: the row is the
            # evidence, and a human can reset available_at to replay it.
            self.available_at = datetime.now(UTC) + timedelta(days=3650)

    def mark_published(self) -> None:
        self.published_at = datetime.now(UTC)
        self.last_error = None

    @property
    def is_dead_lettered(self) -> bool:
        return self.published_at is None and self.attempts >= MAX_ATTEMPTS


async def claim_pending_events(session: AsyncSession, *, limit: int = 100) -> list[OutboxEvent]:
    """Claims a batch for this dispatcher instance.

    `FOR UPDATE SKIP LOCKED` is what makes multiple dispatcher processes safe:
    each claims a disjoint batch instead of contending or double-delivering.
    """
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.available_at <= datetime.now(UTC),
            OutboxEvent.attempts < MAX_ATTEMPTS,
        )
        .order_by(OutboxEvent.occurred_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def purge_published_before(session: AsyncSession, *, cutoff: datetime) -> int:
    """Housekeeping so the table does not grow without bound."""
    stmt = (
        update(OutboxEvent)
        .where(OutboxEvent.published_at.is_not(None), OutboxEvent.published_at < cutoff)
        .values(payload={})
    )
    result = await session.execute(stmt)
    # execute() of an UPDATE/DELETE returns a CursorResult at runtime; the
    # statically declared Result type does not expose rowcount.
    return result.rowcount or 0  # type: ignore[attr-defined]
