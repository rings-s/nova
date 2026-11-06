"""The follow-up inbox over HTTP. Needs Postgres.

How agents open follow-ups is tested where they do it: the chat in
tests/modules/ai_agents/test_turns.py, Sara in tests/modules/call_center/test_router.py.
"""

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import set_tenant_scope
from app.modules.support.dependencies import build_support_service
from app.modules.support.domain import FollowUpReason


async def test_staff_see_who_to_call_back_and_resolve_it(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory,
    business_factory,
    customer_factory,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    customer = await customer_factory(tenant)
    await set_tenant_scope(db_session, tenant.id)
    follow_up_id = await build_support_service(db_session, tenant.id).open_for_call(
        call_id=uuid4(),
        business_id=business.id,
        customer_id=customer.id,
        caller_phone="+966500000123",
        reason=FollowUpReason.ESCALATED,
        summary="Wants a refund for a cancelled appointment.",
        customer_message="أبي أسترجع فلوسي",
    )
    base = f"/api/v1/tenants/{tenant.id}/follow-ups"

    listed = await client.get(base, params={"status": "open"})
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["items"]
    assert item["id"] == str(follow_up_id)
    assert item["source"] == "call"
    assert item["reason"] == "escalated"
    assert item["customer_id"] == str(customer.id)
    assert item["contact_name"] == customer.full_name
    # The number that called, which is the one to ring back.
    assert item["contact_phone"] == "+966500000123"
    assert item["summary"] == "Wants a refund for a cancelled appointment."
    assert item["customer_message"] == "أبي أسترجع فلوسي"
    assert (await client.get(f"{base}/count")).json() == {"open": 1}

    resolved = await client.post(f"{base}/{follow_up_id}/resolve")
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None
    # Twice is fine: it is done either way.
    assert (await client.post(f"{base}/{follow_up_id}/resolve")).status_code == 200

    assert (await client.get(base, params={"status": "open"})).json()["items"] == []
    assert len((await client.get(base)).json()["items"]) == 1
    assert (await client.get(f"{base}/count")).json() == {"open": 0}


async def test_resolving_an_unknown_follow_up_answers_404(client: AsyncClient, tenant_factory):
    tenant = await tenant_factory()
    response = await client.post(f"/api/v1/tenants/{tenant.id}/follow-ups/{uuid4()}/resolve")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "follow_up_not_found"
