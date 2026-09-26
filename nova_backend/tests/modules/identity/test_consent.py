"""Who may turn consent on, and the record of who did. Needs Postgres.

WhatsApp consent covers the transactional messages, and reception records it
for a walk-in at the counter. Marketing consent is the customer's alone to give
(`identity.domain.may_grant_consent`). Either can be withdrawn by staff or the
customer. Every change records its source, actor and time, which is what lets
a salon show that consent was given (PDPL).
"""

from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.modules.identity.models import User


def _consent_url(tenant, customer_id) -> str:
    return f"/api/v1/tenants/{tenant.id}/customers/{customer_id}/consent"


async def _as_customer(app: FastAPI, db_session: AsyncSession, customer_factory, tenant):
    """A signed-in customer who owns a customer record at this salon."""
    user = User(
        email=f"customer-{uuid4().hex[:8]}@example.com",
        full_name="Noura",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    await db_session.flush()
    customer = await customer_factory(tenant, user_id=user.id, whatsapp_consent=False)
    principal = Principal(subject_id=user.id, kind=PrincipalKind.CUSTOMER)
    app.dependency_overrides[get_principal] = lambda: principal
    return user, customer


async def test_staff_cannot_opt_a_customer_in_to_marketing(
    client: AsyncClient, tenant_factory, customer_factory
):
    tenant = await tenant_factory()
    customer = await customer_factory(tenant)

    response = await client.patch(
        _consent_url(tenant, customer.id), json={"marketing_consent": True}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "marketing_consent_customer_only"


async def test_a_refused_request_changes_neither_flag(
    client: AsyncClient, tenant_factory, customer_factory
):
    tenant = await tenant_factory()
    customer = await customer_factory(tenant, whatsapp_consent=False)

    await client.patch(
        _consent_url(tenant, customer.id),
        json={"marketing_consent": True, "whatsapp_consent": True},
    )

    body = (await client.get(f"/api/v1/tenants/{tenant.id}/customers/{customer.id}")).json()
    assert body["marketing_consent"] is False
    assert body["whatsapp_consent"] is False


async def test_staff_cannot_create_a_customer_already_opted_in_to_marketing(
    client: AsyncClient, tenant_factory
):
    tenant = await tenant_factory()

    response = await client.post(
        f"/api/v1/tenants/{tenant.id}/customers",
        json={"full_name": "Walk In", "phone": "+966500000411", "marketing_consent": True},
    )

    assert response.status_code == 403


async def test_staff_record_whatsapp_consent_with_its_provenance(
    client: AsyncClient, tenant_factory, customer_factory
):
    tenant = await tenant_factory()
    customer = await customer_factory(tenant, whatsapp_consent=False)

    response = await client.patch(
        _consent_url(tenant, customer.id), json={"whatsapp_consent": True}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["whatsapp_consent"] is True
    assert body["whatsapp_consent_source"] == "staff"
    assert body["whatsapp_consent_at"] is not None
    assert body["marketing_consent_source"] is None, "an untouched flag keeps no provenance"


async def test_staff_may_withdraw_marketing_consent(
    client: AsyncClient, tenant_factory, customer_factory
):
    tenant = await tenant_factory()
    customer = await customer_factory(tenant, marketing_consent=True)

    response = await client.patch(
        _consent_url(tenant, customer.id), json={"marketing_consent": False}
    )

    assert response.status_code == 200
    assert response.json()["marketing_consent"] is False
    assert response.json()["marketing_consent_source"] == "staff"


async def test_resaving_a_customers_own_opt_in_is_not_a_grant(
    client: AsyncClient, tenant_factory, customer_factory
):
    """The dashboard form sends both flags on every save. Re-sending a
    marketing opt-in the customer gave must neither be refused nor relabel it."""
    tenant = await tenant_factory()
    customer = await customer_factory(
        tenant, marketing_consent=True, marketing_consent_source="customer"
    )

    response = await client.patch(
        _consent_url(tenant, customer.id),
        json={"marketing_consent": True, "whatsapp_consent": True},
    )

    assert response.status_code == 200
    assert response.json()["marketing_consent_source"] == "customer"


async def test_a_customer_opts_in_to_marketing_themselves(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, tenant_factory, customer_factory
):
    tenant = await tenant_factory()
    user, customer = await _as_customer(app, db_session, customer_factory, tenant)

    response = await client.patch(
        f"/api/v1/tenants/{tenant.id}/customers/me/consent",
        json={"marketing_consent": True, "whatsapp_consent": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["marketing_consent"] is True
    assert body["whatsapp_consent"] is True
    assert "notes" not in body, "a customer never sees what staff wrote about them"

    await db_session.refresh(customer)
    assert customer.marketing_consent_source == "customer"
    assert customer.marketing_consent_by == user.id
    assert customer.marketing_consent_at is not None


async def test_a_customer_with_no_record_here_has_nothing_to_consent_to(
    app: FastAPI, client: AsyncClient, tenant_factory
):
    tenant = await tenant_factory()
    stranger = Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)
    app.dependency_overrides[get_principal] = lambda: stranger

    response = await client.patch(
        f"/api/v1/tenants/{tenant.id}/customers/me/consent", json={"marketing_consent": True}
    )

    assert response.status_code == 404
