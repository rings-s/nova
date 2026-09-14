"""Endpoints that change a row and return it must be able to serialise it.

Needs Postgres. `TimestampMixin.updated_at` is computed by the database on
every UPDATE. Without `eager_defaults`, SQLAlchemy expires the attribute at
flush instead of reading it back; the router then serialises the response after
commit, outside the greenlet an async lazy load needs, and every such endpoint
returned 500 with MissingGreenlet.

Nothing caught it because nothing exercised a *real* UPDATE-then-return: the
creates read their server defaults back with RETURNING already, and an update
that sets a column to the value it already holds expires nothing — `is_listed`
defaults to true, so a request setting it to true succeeds either way.
"""

from httpx import AsyncClient


async def test_hiding_a_listing_returns_the_business(
    client: AsyncClient, tenant_factory, business_factory
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)

    # False, not True: the default is already true, and a no-op would pass
    # without the fix.
    response = await client.patch(
        f"/api/v1/tenants/{tenant.id}/catalog/businesses/{business.id}/listing",
        json={"is_listed": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_listed"] is False
    assert body["updated_at"]


async def test_changing_consent_returns_the_customer(client: AsyncClient, tenant_factory) -> None:
    tenant = await tenant_factory()
    created = await client.post(
        f"/api/v1/tenants/{tenant.id}/customers",
        json={"full_name": "Walk In", "phone": "+966500000198"},
    )
    assert created.status_code == 201
    assert created.json()["whatsapp_consent"] is False

    response = await client.patch(
        f"/api/v1/tenants/{tenant.id}/customers/{created.json()['id']}/consent",
        json={"whatsapp_consent": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["whatsapp_consent"] is True
    assert body["updated_at"]
