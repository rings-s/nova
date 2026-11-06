"""Who performs which service, as the dashboard reads and edits it.

A service nobody is assigned to has no bookable time anywhere, so the
dashboard has to be able to see the pairs (to warn) and take one away (an
owner narrowing who does a treatment), not only add one.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.security import Principal, PrincipalKind, get_principal


def _catalog(tenant) -> str:
    return f"/api/v1/tenants/{tenant.id}/catalog"


@pytest.fixture
def salon(
    tenant_factory, business_factory, location_factory, service_factory, provider_factory, qualify
):
    async def _make(**business):
        tenant = await tenant_factory()
        biz = await business_factory(tenant, **business)
        location = await location_factory(biz)
        service = await service_factory(location)
        provider = await provider_factory(location)
        await qualify(provider, service)
        return tenant, location, service, provider

    return _make


async def test_a_branch_lists_who_performs_what(
    client: AsyncClient, salon, service_factory, provider_factory, qualify
) -> None:
    tenant, location, service, provider = await salon()
    nobody = await service_factory(location, name_en="Nobody does this")
    other = await provider_factory(location, name_en="Second")
    await qualify(other, service)

    response = await client.get(f"{_catalog(tenant)}/locations/{location.id}/assignments")

    assert response.status_code == 200
    pairs = {(row["provider_id"], row["service_id"]) for row in response.json()["items"]}
    assert pairs == {(str(provider.id), str(service.id)), (str(other.id), str(service.id))}
    assert all(service_id != str(nobody.id) for _, service_id in pairs)


async def test_another_tenants_branch_is_not_found(client: AsyncClient, salon) -> None:
    mine, *_ = await salon()
    _, theirs, *_ = await salon()

    response = await client.get(f"{_catalog(mine)}/locations/{theirs.id}/assignments")

    assert response.status_code == 404


async def test_a_deleted_provider_performs_nothing(client: AsyncClient, salon) -> None:
    tenant, location, _, provider = await salon()
    deleted = await client.delete(f"{_catalog(tenant)}/providers/{provider.id}")
    assert deleted.status_code == 204

    response = await client.get(f"{_catalog(tenant)}/locations/{location.id}/assignments")

    assert response.json()["items"] == []


async def test_unassigning_takes_the_provider_off_the_public_calendar(
    client: AsyncClient, salon
) -> None:
    tenant, location, service, provider = await salon(slug="unassign-salon")
    base = f"/api/v1/tenants/{tenant.id}"
    schedule = await client.put(
        f"{base}/schedules/providers/{provider.id}",
        json={
            "windows": [
                {"weekday": day, "start_minute": 540, "end_minute": 1020} for day in range(7)
            ]
        },
    )
    assert schedule.status_code == 200
    start = (datetime.now(UTC) + timedelta(days=1)).replace(hour=0, minute=0, second=0)
    window = {"date_from": start.isoformat(), "date_to": (start + timedelta(days=2)).isoformat()}
    availability = f"/api/v1/discovery/businesses/unassign-salon/services/{service.id}/availability"
    assert (await client.get(availability, params=window)).json()["slots"]

    removed = await client.delete(
        f"{_catalog(tenant)}/providers/{provider.id}/services/{service.id}"
    )

    assert removed.status_code == 204
    assert (await client.get(availability, params=window)).json()["slots"] == []
    pairs = await client.get(f"{_catalog(tenant)}/locations/{location.id}/assignments")
    assert pairs.json()["items"] == []


async def test_unassigning_a_pair_that_is_not_assigned_is_harmless(
    client: AsyncClient, salon
) -> None:
    tenant, _, service, provider = await salon()
    url = f"{_catalog(tenant)}/providers/{provider.id}/services/{service.id}"

    assert (await client.delete(url)).status_code == 204
    assert (await client.delete(url)).status_code == 204


async def test_unassigning_an_unknown_service_is_a_404(client: AsyncClient, salon) -> None:
    tenant, _, _, provider = await salon()

    response = await client.delete(f"{_catalog(tenant)}/providers/{provider.id}/services/{uuid4()}")

    assert response.status_code == 404


async def test_a_customer_cannot_unassign(app: FastAPI, client: AsyncClient, salon) -> None:
    tenant, _, service, provider = await salon()
    customer = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
    app.dependency_overrides[get_principal] = lambda: customer

    response = await client.delete(
        f"{_catalog(tenant)}/providers/{provider.id}/services/{service.id}"
    )

    assert response.status_code == 403
