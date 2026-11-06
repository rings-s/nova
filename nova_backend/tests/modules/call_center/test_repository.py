"""Tenant isolation for phone lines and calls (ADR-0003). Needs Postgres.

Read as the schema owner, which RLS does not restrict, so only the
repository's own filter can pass them (see tests/modules/catalog/test_repository.py).
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantMismatchError
from app.modules.call_center.domain import Call, CallDirection, CallPurpose
from app.modules.call_center.models import PhoneLineRecord
from app.modules.call_center.repository import PhoneLineRepository, VoiceCallRepository


async def _line(db_session: AsyncSession, tenant, business, number: str) -> PhoneLineRecord:
    line = PhoneLineRecord(
        tenant_id=tenant.id,
        business_id=business.id,
        number_e164=number,
        locale="ar",
        agent_name="call_center_agent",
        is_active=True,
        token_version=0,
    )
    PhoneLineRepository(db_session, tenant.id).add(line)
    await db_session.flush()
    return line


async def test_another_tenants_lines_and_calls_are_invisible(
    db_session: AsyncSession, tenant_factory, business_factory, as_owner
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    business_a = await business_factory(tenant_a)
    async with as_owner():
        line_a = await _line(db_session, tenant_a, business_a, "+966800000001")
        call_a = await VoiceCallRepository(db_session, tenant_a.id).add_call(
            Call(
                tenant_id=tenant_a.id,
                line_id=line_a.id,
                business_id=business_a.id,
                direction=CallDirection.INBOUND,
                purpose=CallPurpose.CONVERSATION,
                started_at=datetime.now(UTC),
                gateway_call_id="c-a",
            )
        )

        lines_b = PhoneLineRepository(db_session, tenant_b.id)
        calls_b = VoiceCallRepository(db_session, tenant_b.id)
        assert await lines_b.get(line_a.id) is None
        assert await lines_b.list_all() == []
        assert await lines_b.active_for_business(business_a.id) is None
        assert await calls_b.get_call(call_a.id) is None
        assert await calls_b.by_gateway_id("c-a") is None
        assert await calls_b.recent(limit=10, offset=0) == []

        # Its own tenant sees both.
        assert await VoiceCallRepository(db_session, tenant_a.id).get_call(call_a.id) == call_a


async def test_a_line_for_another_tenant_is_refused(
    db_session: AsyncSession, tenant_factory, business_factory
) -> None:
    tenant_a = await tenant_factory()
    tenant_b = await tenant_factory()
    business_a = await business_factory(tenant_a)
    rogue = PhoneLineRecord(
        tenant_id=tenant_a.id,
        business_id=business_a.id,
        number_e164="+966800000002",
        locale="ar",
        agent_name="call_center_agent",
    )
    with pytest.raises(TenantMismatchError):
        PhoneLineRepository(db_session, tenant_b.id).add(rogue)
