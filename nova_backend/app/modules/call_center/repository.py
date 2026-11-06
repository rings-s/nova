"""call_center · PERSISTENCE layer — queries and the `Call` <-> row mapping.

Layer rule: models + `app.db` + this module's domain. `VoiceCallRecord` never
escapes this file; callers get `domain.Call`.
"""

from dataclasses import fields
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantScopedRepository
from app.modules.call_center.domain import (
    Call,
    CallDirection,
    CallOutcome,
    CallPurpose,
    CallStatus,
)
from app.modules.call_center.models import PhoneLineRecord, VoiceCallRecord

_CALL_FIELDS = [f.name for f in fields(Call)]


class PhoneLineRepository(TenantScopedRepository[PhoneLineRecord]):
    model = PhoneLineRecord

    async def number_in_use(self, number_e164: str) -> bool:
        """Within this tenant. The unique constraint answers for every other."""
        stmt = self._scope(self._base_select().where(PhoneLineRecord.number_e164 == number_e164))
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def active_for_business(self, business_id: UUID) -> PhoneLineRecord | None:
        stmt = self._scope(
            self._base_select()
            .where(PhoneLineRecord.business_id == business_id, PhoneLineRecord.is_active)
            .order_by(PhoneLineRecord.created_at)
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> list[PhoneLineRecord]:
        stmt = self._scope(self._base_select().order_by(PhoneLineRecord.created_at))
        return list((await self.session.execute(stmt)).scalars())


class VoiceCallRepository(TenantScopedRepository[VoiceCallRecord]):
    model = VoiceCallRecord

    @staticmethod
    def _to_domain(record: VoiceCallRecord) -> Call:
        return Call(**{name: getattr(record, name) for name in _CALL_FIELDS})

    async def get_call(self, call_id: UUID, *, for_update: bool = False) -> Call | None:
        """Locked for update on a turn: two deliveries for one call take turns."""
        stmt = self._scope(self._base_select().where(VoiceCallRecord.id == call_id))
        if for_update:
            stmt = stmt.with_for_update()
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(record) if record is not None else None

    async def by_gateway_id(self, gateway_call_id: str) -> Call | None:
        stmt = self._scope(
            self._base_select().where(VoiceCallRecord.gateway_call_id == gateway_call_id)
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(record) if record is not None else None

    async def reminder_for(self, booking_id: UUID) -> Call | None:
        stmt = self._scope(
            self._base_select().where(
                VoiceCallRecord.booking_id == booking_id,
                VoiceCallRecord.purpose == CallPurpose.REMINDER,
            )
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        return self._to_domain(record) if record is not None else None

    async def outbound_since(self, since: datetime) -> int:
        stmt = self._scope(
            select(func.count())
            .select_from(VoiceCallRecord)
            .where(
                VoiceCallRecord.direction == CallDirection.OUTBOUND,
                VoiceCallRecord.started_at >= since,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def recent(self, *, limit: int, offset: int) -> list[Call]:
        stmt = self._scope(
            self._base_select()
            .order_by(VoiceCallRecord.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_domain(r) for r in (await self.session.execute(stmt)).scalars()]

    async def add_call(self, call: Call) -> Call:
        self.add(VoiceCallRecord(**{name: getattr(call, name) for name in _CALL_FIELDS}))
        await self.session.flush()
        return call

    async def save_call(self, call: Call) -> Call:
        stmt = self._scope(self._base_select().where(VoiceCallRecord.id == call.id))
        record = (await self.session.execute(stmt)).scalar_one()
        for name in _CALL_FIELDS:
            setattr(record, name, getattr(call, name))
        await self.session.flush()
        return call

    async def delete_call(self, call_id: UUID) -> None:
        """Only for a reminder that never rang (`CallCenterService.record_dial`)."""
        await self.session.execute(
            delete(VoiceCallRecord).where(
                VoiceCallRecord.tenant_id == self.tenant_id, VoiceCallRecord.id == call_id
            )
        )


#: What a call keeps about the person once its retention ends: none of these.
_PERSONAL_FIELDS = ("caller_e164", "last_reply", "last_answer_key", "code_hash", "code_expires_at")


class UnscopedCallRepository:
    """Cross-tenant writes for the call-log retention sweep.

    Callers must have set `app.bypass_rls` (`db.session.bypass_tenant_scope`).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def scrub_started_before(self, cutoff: datetime, *, limit: int) -> int:
        """Clears the caller's number and Sara's words from up to `limit` calls
        that started before `cutoff`. Returns how many it cleared."""
        columns = [getattr(VoiceCallRecord, name) for name in _PERSONAL_FIELDS]
        due = (
            select(VoiceCallRecord.id)
            .where(
                VoiceCallRecord.started_at < cutoff,
                or_(*(column.is_not(None) for column in columns)),
            )
            .limit(limit)
            .scalar_subquery()
        )
        result = await self.session.execute(
            update(VoiceCallRecord)
            .where(VoiceCallRecord.id.in_(due))
            .values({name: None for name in _PERSONAL_FIELDS})
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def end_idle_since(self, last_activity_before: datetime, *, limit: int) -> int:
        """Ends up to `limit` calls still in progress whose row last changed
        before the cutoff. Returns how many it ended.

        `updated_at` is the call's last turn, so it is also when it ended. A
        reminder that never had a turn was not answered (`CallOutcome.NO_ANSWER`);
        any other call keeps what it achieved, or none.
        """
        due = (
            select(VoiceCallRecord.id)
            .where(
                VoiceCallRecord.status == CallStatus.IN_PROGRESS,
                VoiceCallRecord.updated_at < last_activity_before,
            )
            .limit(limit)
            .scalar_subquery()
        )
        unanswered = and_(
            VoiceCallRecord.outcome.is_(None),
            VoiceCallRecord.purpose == CallPurpose.REMINDER,
            VoiceCallRecord.turns == 0,
        )
        result = await self.session.execute(
            update(VoiceCallRecord)
            .where(VoiceCallRecord.id.in_(due))
            .values(
                status=CallStatus.ENDED,
                # Read before this UPDATE sets a new `updated_at`.
                ended_at=func.coalesce(VoiceCallRecord.ended_at, VoiceCallRecord.updated_at),
                outcome=case(
                    (unanswered, str(CallOutcome.NO_ANSWER)), else_=VoiceCallRecord.outcome
                ),
            )
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
