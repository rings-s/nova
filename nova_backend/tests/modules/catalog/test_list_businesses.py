"""`GET /catalog/businesses`: how a dashboard finds its storefront. Needs Postgres.

Before it existed, a business id was only ever returned by the create call, so
an owner signing in on a new browser saw "set up your storefront" and was
offered to create a duplicate of the business they already had (2026-09-23).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.security import Principal, PrincipalKind, get_principal


def _path(tenant_id) -> str:
    return f"/api/v1/tenants/{tenant_id}/catalog/businesses"


async def test_staff_find_their_salons_storefront(client, tenant_factory, business_factory):
    tenant = await tenant_factory()
    # One test transaction gives both rows the same now(); age them apart.
    earlier = datetime.now(UTC) - timedelta(days=30)
    second = await business_factory(tenant, name_en="Second Storefront")
    first = await business_factory(tenant, name_en="Original Storefront", created_at=earlier)

    response = await client.get(_path(tenant.id))

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    # Oldest first, so "the first one" is the salon's original storefront.
    assert ids == [str(first.id), str(second.id)]


async def test_another_salons_storefront_is_never_listed(client, tenant_factory, business_factory):
    mine = await tenant_factory()
    theirs = await tenant_factory()
    await business_factory(mine)
    stranger = await business_factory(theirs)

    items = (await client.get(_path(mine.id))).json()["items"]

    assert str(stranger.id) not in {item["id"] for item in items}


async def test_a_customer_cannot_list_a_salons_storefronts(app, client, tenant_factory):
    tenant = await tenant_factory()
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )

    response = await client.get(_path(tenant.id))

    assert response.status_code == 403
