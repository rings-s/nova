"""The billing HTTP surface a dashboard reads. Needs Postgres."""

from httpx import AsyncClient


def url(tenant_id, path: str) -> str:
    return f"/api/v1/tenants/{tenant_id}/billing/{path}"


async def test_the_price_list_carries_what_a_pricing_table_needs(
    client: AsyncClient, tenant_factory
):
    tenant = await tenant_factory()

    response = await client.get(url(tenant.id, "plans"))

    assert response.status_code == 200
    plans = {plan["tier"]: plan for plan in response.json()["items"]}
    assert plans["solo"]["whatsapp_reminders_per_month"] == 100
    assert plans["studio"]["whatsapp_reminders_per_month"] is None
    assert plans["chain"]["contract_months"] == 12
    assert plans["studio"]["contract_months"] == 0


async def test_a_subscription_says_whether_it_is_billed_yearly(
    client: AsyncClient, tenant_factory, business_factory
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)

    created = await client.post(
        url(tenant.id, "subscriptions"),
        json={"business_id": str(business.id), "tier": "studio", "annual": True},
    )
    assert created.status_code == 201
    assert created.json()["annual"] is True

    changed = await client.post(
        url(tenant.id, f"subscriptions/{business.id}/plan"), json={"tier": "chain"}
    )
    assert changed.status_code == 200
    assert changed.json()["annual"] is False
    assert changed.json()["tier"] == "chain"
