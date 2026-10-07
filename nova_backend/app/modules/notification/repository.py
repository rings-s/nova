"""notification · PERSISTENCE layer — queries.

Layer rule: models + `app.db`. Must not import service, router, or fastapi.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantScopedRepository
from app.modules.notification.domain import NotificationStatus
from app.modules.notification.models import NotificationRecord


class NotificationRepository(TenantScopedRepository[NotificationRecord]):
    model = NotificationRecord

    async def find_by_dedupe_key(self, dedupe_key: str) -> NotificationRecord | None:
        """The check that stops a redelivered event sending twice."""
        stmt = self._scope(
            select(NotificationRecord).where(NotificationRecord.dedupe_key == dedupe_key)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_customer(
        self, customer_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[NotificationRecord]:
        stmt = (
            self._scope(
                select(NotificationRecord).where(NotificationRecord.customer_id == customer_id)
            )
            .order_by(NotificationRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_due(self, *, now: datetime, limit: int = 100) -> list[NotificationRecord]:
        """Every message that is ready to go out.

        This predicate used to carry `scheduled_for IS NOT NULL`, and that one
        clause is why no notification has ever been delivered: `enqueue` sets
        `scheduled_for` only when quiet hours hold a *marketing* message back,
        so every transactional row — every booking confirmation, queue call and
        payment receipt — stored NULL and was excluded here forever.

        `scheduled_for` is now non-nullable and always means "not before", so
        the single comparison covers all three populations: send-now, held by
        quiet hours, and waiting out a retry backoff.

        Ordered by `created_at`, not `scheduled_for`, so a backlog drains
        oldest-first: after an outage the customer who has been waiting longest
        hears back first.
        """
        stmt = (
            self._scope(
                select(NotificationRecord).where(
                    NotificationRecord.status == NotificationStatus.PENDING,
                    NotificationRecord.scheduled_for <= now,
                )
            )
            .order_by(NotificationRecord.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_provider_message_id(
        self, provider_message_id: str
    ) -> NotificationRecord | None:
        stmt = self._scope(
            select(NotificationRecord).where(
                NotificationRecord.provider_message_id == provider_message_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class UnscopedNotificationRepository:
    """Cross-tenant reads for the delivery sweep (`deliver_pending_notifications`).

    Mirrors `NotificationRepository.list_due`'s predicate across every tenant;
    change one and change the other. Callers must have set `app.bypass_rls`
    (`db.session.bypass_tenant_scope`), or RLS correctly returns nothing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_due(self, *, now: datetime, limit: int) -> list[tuple[UUID, UUID]]:
        """`(notification_id, tenant_id)`, oldest first."""
        stmt = (
            select(NotificationRecord.id, NotificationRecord.tenant_id)
            .where(
                NotificationRecord.status == NotificationStatus.PENDING,
                NotificationRecord.scheduled_for <= now,
            )
            .order_by(NotificationRecord.created_at)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]
