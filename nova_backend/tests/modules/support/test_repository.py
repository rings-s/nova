"""Follow-ups: tenant isolation (ADR-0003) and one row per source. Needs Postgres.

Read as the schema owner, which RLS does not restrict, so only the
repository's own filter can pass them (see tests/modules/catalog/test_repository.py).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.support.domain import FollowUpReason, FollowUpSource, FollowUpStatus
from app.modules.support.repository import FollowUpRepository


def _values(source_ref: str, **extra) -> dict:
    return {
        "source": FollowUpSource.CALL,
        "source_ref": source_ref,
        "reason": FollowUpReason.AGENT_COULD_NOT_HELP,
        **extra,
    }


async def test_another_tenants_follow_ups_are_invisible(
    db_session: AsyncSession, tenant_factory, as_owner
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    async with as_owner():
        follow_up_id, _ = await FollowUpRepository(db_session, tenant_a.id).open(
            values=_values("call-a"), now=datetime.now(UTC)
        )

        others = FollowUpRepository(db_session, tenant_b.id)
        assert await others.get(follow_up_id) is None
        assert await others.list_by_status(None, limit=10, offset=0) == []
        assert await others.count_open() == 0

        own = FollowUpRepository(db_session, tenant_a.id)
        assert (await own.get(follow_up_id)) is not None
        assert await own.count_open() == 1


async def test_a_second_handoff_updates_the_open_one_and_reopens_a_resolved_one(
    db_session: AsyncSession, tenant_factory, as_owner
) -> None:
    tenant = await tenant_factory()
    repository = FollowUpRepository(db_session, tenant.id)
    first_at = datetime.now(UTC) - timedelta(hours=1)
    async with as_owner():
        follow_up_id, newly_open = await repository.open(
            values=_values("call-1", contact_phone="+966500000001", summary="First problem"),
            now=first_at,
        )
        assert newly_open

        # Open still: one row, the new reason, and what the new handoff left unsaid kept.
        again_id, newly_open = await repository.open(
            values=_values("call-1", reason=FollowUpReason.ESCALATED, customer_message="Hello?"),
            now=first_at + timedelta(minutes=5),
        )
        assert (again_id, newly_open) == (follow_up_id, False)
        row = await repository.get(follow_up_id)
        await db_session.refresh(row)
        assert row.reason is FollowUpReason.ESCALATED
        assert row.contact_phone == "+966500000001"
        assert row.summary == "First problem"
        assert row.customer_message == "Hello?"
        assert row.opened_at == first_at

        # Resolved, then the same call hands off again: open, with a fresh clock.
        row.status = FollowUpStatus.RESOLVED
        row.resolved_at = datetime.now(UTC)
        row.resolved_by = uuid4()
        await db_session.flush()
        reopened_at = first_at + timedelta(minutes=30)
        reopened_id, newly_open = await repository.open(values=_values("call-1"), now=reopened_at)
        assert (reopened_id, newly_open) == (follow_up_id, True)
        await db_session.refresh(row)
        assert row.status is FollowUpStatus.OPEN
        assert row.resolved_at is None and row.resolved_by is None
        assert row.opened_at == reopened_at

        # Another call is another follow-up.
        other_id, _ = await repository.open(values=_values("call-2"), now=reopened_at)
        assert other_id != follow_up_id
        assert await repository.count_open() == 2
