"""support · PERSISTENCE layer — follow-up queries.

Layer rule: models and `app.db` only. No fastapi, no service.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.repository import TenantScopedRepository
from app.modules.support.domain import FollowUpStatus
from app.modules.support.models import FollowUp

#: Kept from the earlier handoff when the new one does not say: a call that
#: hands off twice keeps the caller's number and the first summary.
_KEEP_IF_UNSAID = (
    "business_id",
    "customer_id",
    "booking_id",
    "contact_name",
    "contact_phone",
    "contact_email",
    "summary",
    "customer_message",
)


class FollowUpRepository(TenantScopedRepository[FollowUp]):
    model = FollowUp

    async def open(self, *, values: dict[str, Any], now: datetime) -> tuple[UUID, bool]:
        """Opens the follow-up for its source, or updates (and reopens) the one there is.

        Returns its id, and whether it is newly open: inserted or reopened now,
        rather than an open one updated. One statement, so a redelivered or
        concurrent handoff for the same call or conversation lands on one row
        rather than racing to insert two. `updated_at` is set by hand:
        `onupdate` does not reach an ON CONFLICT SET.
        """
        insert = pg_insert(FollowUp).values(
            tenant_id=self.tenant_id, status=FollowUpStatus.OPEN, opened_at=now, **values
        )
        excluded = insert.excluded
        set_: dict[str, Any] = {
            name: func.coalesce(getattr(excluded, name), getattr(FollowUp, name))
            for name in _KEEP_IF_UNSAID
        }
        set_.update(
            reason=excluded.reason,
            status=FollowUpStatus.OPEN,
            # Reopening starts the clock again; another handoff while open does not.
            opened_at=case(
                (FollowUp.status == FollowUpStatus.RESOLVED, excluded.opened_at),
                else_=FollowUp.opened_at,
            ),
            resolved_at=None,
            resolved_by=None,
            updated_at=func.now(),
        )
        stmt = insert.on_conflict_do_update(
            index_elements=["tenant_id", "source", "source_ref"], set_=set_
        ).returning(FollowUp.id, FollowUp.opened_at)
        follow_up_id, opened_at = (await self.session.execute(stmt)).one()
        return follow_up_id, opened_at == now

    async def list_by_status(
        self, status: FollowUpStatus | None, *, limit: int, offset: int
    ) -> list[FollowUp]:
        stmt = self._scope(self._base_select())
        if status is not None:
            stmt = stmt.where(FollowUp.status == status)
        stmt = (
            stmt.order_by(FollowUp.opened_at.desc(), FollowUp.id.desc()).limit(limit).offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def count_open(self) -> int:
        stmt = self._scope(
            select(func.count()).select_from(FollowUp).where(FollowUp.status == FollowUpStatus.OPEN)
        )
        return int((await self.session.execute(stmt)).scalar_one())
