"""Where a branch sits on the map, set by its owner (ADR-0012).

`PATCH .../catalog/locations/{id}/position`. A branch is on the marketplace map
only if it has coordinates, and until this route the only way to give it any was
to supply them at creation, which no screen did. These tests cover the write
itself and, more importantly, that what an owner writes is what a customer's map
then shows.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.security import Principal, PrincipalKind, get_principal

#: Riyadh.
LAT, LNG = 24.7136, 46.6753


def _path(tenant, location) -> str:
    return f"/api/v1/tenants/{tenant.id}/catalog/locations/{location.id}/position"


async def _branch(tenant_factory, business_factory, location_factory, **overrides):
    tenant = await tenant_factory()
    business = await business_factory(tenant, **overrides)
    return tenant, business, await location_factory(business)


async def test_an_owner_puts_a_branch_on_the_map(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)
    assert location.latitude is None

    response = await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})

    assert response.status_code == 200
    body = response.json()
    assert (body["latitude"], body["longitude"]) == (LAT, LNG)
    # The row is read back after an UPDATE; see test_update_responses.py.
    assert body["updated_at"]


async def test_moving_a_pin_replaces_the_old_position(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)
    await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})

    moved = await client.patch(
        _path(tenant, location), json={"latitude": 21.4858, "longitude": 39.1925}
    )

    assert moved.status_code == 200
    assert (moved.json()["latitude"], moved.json()["longitude"]) == (21.4858, 39.1925)


async def test_null_and_null_takes_the_branch_off_the_map(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)
    await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})

    cleared = await client.patch(
        _path(tenant, location), json={"latitude": None, "longitude": None}
    )

    assert cleared.status_code == 200
    assert (cleared.json()["latitude"], cleared.json()["longitude"]) == (None, None)


async def test_what_an_owner_sets_is_what_the_customers_map_shows(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    """The point of the route, end to end: owner writes, customer's map reads."""
    tenant, business, location = await _branch(
        tenant_factory, business_factory, location_factory, name_en="Pinned By Owner Salon"
    )
    discovery = "/api/v1/discovery/map"

    def on_map(response) -> list[str]:
        return [f["properties"]["business_id"] for f in response.json()["features"]]

    before = await client.get(discovery, params={"q": "Pinned By Owner"})
    assert on_map(before) == []

    await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})
    placed = await client.get(discovery, params={"q": "Pinned By Owner"})
    assert on_map(placed) == [str(business.id)]
    # [longitude, latitude]: GeoJSON's order, not the API's usual one.
    assert placed.json()["features"][0]["geometry"]["coordinates"] == [LNG, LAT]

    await client.patch(_path(tenant, location), json={"latitude": None, "longitude": None})
    removed = await client.get(discovery, params={"q": "Pinned By Owner"})
    assert on_map(removed) == []


async def test_both_keys_are_required_so_an_empty_body_is_not_a_clear(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    """`{}` is a mistake to be told about; silently reading it as "remove the pin"
    would take a branch off the map on a malformed request."""
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)
    await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})

    refused = await client.patch(_path(tenant, location), json={})

    assert refused.status_code == 422
    kept = await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})
    assert kept.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"latitude": LAT, "longitude": None},
        {"latitude": None, "longitude": LNG},
        {"latitude": 91, "longitude": LNG},
        {"latitude": -91, "longitude": LNG},
        {"latitude": LAT, "longitude": 181},
        {"latitude": LAT, "longitude": -181},
    ],
    ids=["lat-only", "lng-only", "lat-high", "lat-low", "lng-high", "lng-low"],
)
async def test_a_half_pair_or_an_impossible_position_is_refused(
    client: AsyncClient, tenant_factory, business_factory, location_factory, body
) -> None:
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)

    response = await client.patch(_path(tenant, location), json=body)

    assert response.status_code == 422


async def test_nan_is_refused_not_stored(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    """`NaN` is not JSON, but Python's parser reads it, and it compares false to
    every bound — so a range check written the natural way waves it through and
    a branch is stored at a position that matches no viewport."""
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)

    response = await client.patch(
        _path(tenant, location),
        content='{"latitude": NaN, "longitude": 46.6}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


async def test_an_unknown_branch_is_a_404(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    tenant, _, _ = await _branch(tenant_factory, business_factory, location_factory)

    response = await client.patch(
        f"/api/v1/tenants/{tenant.id}/catalog/locations/{uuid4()}/position",
        json={"latitude": LAT, "longitude": LNG},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "location_not_found"


async def test_a_tenant_cannot_move_another_tenants_branch(
    client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    """The branch belongs to one tenant; asking through another finds nothing."""
    _, _, victim = await _branch(tenant_factory, business_factory, location_factory)
    other = await tenant_factory()

    response = await client.patch(
        f"/api/v1/tenants/{other.id}/catalog/locations/{victim.id}/position",
        json={"latitude": LAT, "longitude": LNG},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "location_not_found"


async def test_a_customer_cannot_move_a_pin(
    app: FastAPI, client: AsyncClient, tenant_factory, business_factory, location_factory
) -> None:
    """A customer may reach any tenant in a marketplace, so this has to be a
    staff check and not merely a tenant one."""
    tenant, _, location = await _branch(tenant_factory, business_factory, location_factory)
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )

    response = await client.patch(_path(tenant, location), json={"latitude": LAT, "longitude": LNG})

    assert response.status_code == 403
