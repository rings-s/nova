"""review · PERSISTENCE layer — review queries.

Layer rule: models and `app.db` only. No fastapi, no service.
"""

from uuid import UUID

from app.db.repository import TenantScopedRepository
from app.modules.review.models import Review


class ReviewRepository(TenantScopedRepository[Review]):
    model = Review

    async def get_by_booking(self, booking_id: UUID) -> Review | None:
        stmt = self._scope(self._base_select().where(Review.booking_id == booking_id))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_customer(self, customer_id: UUID, *, limit: int = 100) -> list[Review]:
        stmt = (
            self._scope(self._base_select().where(Review.customer_id == customer_id))
            .order_by(Review.created_at.desc(), Review.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_business(
        self, business_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Review]:
        stmt = (
            self._scope(self._base_select().where(Review.business_id == business_id))
            .order_by(Review.created_at.desc(), Review.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
