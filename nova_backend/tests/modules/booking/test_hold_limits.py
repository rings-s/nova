"""How many slots one customer may hold at once.

A hold blocks a provider's time for everyone. Uncapped, one account could hold
every slot on a salon's calendar and re-hold each as it expired, and nobody else
could book. Needs Postgres.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.modules.booking.models import SlotHoldRecord

LIMIT = get_settings().slot_hold_max_active_per_customer


@pytest_asyncio.fixture
async def salon(
    tenant_factory, business_factory, location_factory, service_factory, provider_factory, qualify
):
    tenant = await tenant_factory()
    location = await location_factory(await business_factory(tenant))
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    return {"tenant": tenant, "service": service, "provider": provider}


def act_as(app: FastAPI, kind: PrincipalKind = PrincipalKind.CUSTOMER) -> Principal:
    principal = Principal(subject_id=uuid4(), kind=kind)
    app.dependency_overrides[get_principal] = lambda: principal
    return principal


async def hold(client: AsyncClient, salon: dict, *, days_ahead: int) -> Response:
    starts_at = (datetime.now(UTC) + timedelta(days=days_ahead)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    return await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/bookings/holds",
        json={
            "provider_id": str(salon["provider"].id),
            "service_id": str(salon["service"].id),
            "starts_at": starts_at.isoformat(),
        },
    )


async def fill_to_the_limit(client: AsyncClient, salon: dict) -> list[str]:
    tokens = []
    for day in range(2, 2 + LIMIT):
        response = await hold(client, salon, days_ahead=day)
        assert response.status_code == 201, response.text
        tokens.append(response.json()["hold_token"])
    return tokens


async def test_a_customer_holds_up_to_the_limit_and_no_more(app: FastAPI, client, salon):
    act_as(app)
    await fill_to_the_limit(client, salon)

    refused = await hold(client, salon, days_ahead=20)

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "hold_limit_reached"


async def test_releasing_a_hold_makes_room_for_another(app: FastAPI, client, salon):
    act_as(app)
    tokens = await fill_to_the_limit(client, salon)

    released = await client.delete(
        f"/api/v1/tenants/{salon['tenant'].id}/bookings/holds/{tokens[0]}"
    )
    assert released.status_code == 204

    assert (await hold(client, salon, days_ahead=20)).status_code == 201


async def test_an_expired_hold_no_longer_counts(
    app: FastAPI, client, db_session: AsyncSession, salon
):
    act_as(app)
    await fill_to_the_limit(client, salon)
    await set_tenant_scope(db_session, salon["tenant"].id)
    await db_session.execute(
        update(SlotHoldRecord)
        .where(SlotHoldRecord.tenant_id == salon["tenant"].id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )

    assert (await hold(client, salon, days_ahead=20)).status_code == 201


async def test_one_customers_holds_do_not_limit_another(app: FastAPI, client, salon):
    act_as(app)
    await fill_to_the_limit(client, salon)

    act_as(app)
    assert (await hold(client, salon, days_ahead=20)).status_code == 201


async def test_staff_are_not_limited(app: FastAPI, client, salon):
    """Reception holds for whoever is at the desk. The conftest principal is SERVICE."""
    await fill_to_the_limit(client, salon)

    assert (await hold(client, salon, days_ahead=20)).status_code == 201


async def test_a_hold_records_who_took_it(app: FastAPI, client, db_session: AsyncSession, salon):
    customer = act_as(app)
    response = await hold(client, salon, days_ahead=2)
    assert response.status_code == 201, response.text

    await set_tenant_scope(db_session, salon["tenant"].id)
    held_by = (
        await db_session.execute(
            select(SlotHoldRecord.held_by).where(
                SlotHoldRecord.hold_token == response.json()["hold_token"]
            )
        )
    ).scalar_one()
    assert held_by == customer.subject_id
