"""Paying for a paid plan on Moyasar's hosted page.

A Studio or Chain subscription starts `pending_payment` and is billed and
gated as Solo until Moyasar's own record shows the first payment: plan price
plus 15% VAT, paid on this checkout's invoice. The owner's return and the
webhook both get there; neither trusts what it is told without asking Moyasar.
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.integrations.payments.moyasar import MoyasarGateway
from app.modules.billing.dependencies import build_billing_service
from app.modules.billing.domain import BillingPeriod
from app.modules.payment.dependencies import get_payment_gateway

WEBHOOK_SECRET = "whsec_plan_test"


@pytest.fixture(autouse=True)
def _configure_moyasar(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MOYASAR_API_KEY", "sk_test_x")
    monkeypatch.setenv("MOYASAR_WEBHOOK_SECRET", WEBHOOK_SECRET)
    yield
    get_settings.cache_clear()


class FakeMoyasar(MoyasarGateway):
    """Moyasar's API answered from dicts; the real webhook secret check."""

    def __init__(self) -> None:
        super().__init__(api_key="sk_test_x", webhook_secret=WEBHOOK_SECRET)
        self.created: list[dict[str, Any]] = []
        self.payments: dict[str, dict[str, Any]] = {}
        self.invoices: dict[str, dict[str, Any]] = {}

    async def create_invoice(self, **kwargs: Any) -> dict[str, Any]:
        invoice_id = f"inv_{uuid4().hex[:10]}"
        self.created.append({"id": invoice_id, **kwargs})
        return {"id": invoice_id, "url": f"https://checkout.moyasar.test/{invoice_id}"}

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self.payments.get(payment_id, {"id": payment_id, "status": "initiated"})

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        return self.invoices.get(
            invoice_id, {"id": invoice_id, "status": "initiated", "payments": []}
        )

    def pay(self, invoice_id: str, *, amount_minor: int, currency: str = "SAR") -> str:
        """The owner pays on Moyasar's page."""
        payment_id = f"pay_{uuid4().hex[:10]}"
        self.payments[payment_id] = {
            "id": payment_id,
            "status": "paid",
            "amount": amount_minor,
            "currency": currency,
            "invoice_id": invoice_id,
        }
        self.invoices[invoice_id] = {
            "id": invoice_id,
            "status": "paid",
            "payments": [{"id": payment_id, "status": "paid"}],
        }
        return payment_id


@pytest.fixture
def moyasar(app) -> FakeMoyasar:
    gateway = FakeMoyasar()
    app.dependency_overrides[get_payment_gateway] = lambda: gateway
    return gateway


def _billing(tenant) -> str:
    return f"/api/v1/tenants/{tenant.id}/billing"


def _return_url() -> str:
    return f"{get_settings().public_app_url}/app/billing"


async def _studio(client, tenant_factory, business_factory, **extra):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    response = await client.post(
        f"{_billing(tenant)}/subscriptions",
        json={"business_id": str(business.id), "tier": "studio", **extra},
    )
    assert response.status_code == 201, response.text
    return tenant, business, response.json()


async def _checkout(client, tenant, business):
    response = await client.post(
        f"{_billing(tenant)}/subscriptions/{business.id}/checkout",
        json={"return_url": _return_url()},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _subscription(client, tenant, business):
    return (await client.get(f"{_billing(tenant)}/subscriptions/{business.id}")).json()


async def test_a_paid_plan_waits_for_payment_and_opens_moyasar(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant, business, subscription = await _studio(client, tenant_factory, business_factory)
    assert subscription["status"] == "pending_payment"

    checkout = await _checkout(client, tenant, business)

    # 199 SAR plus 15% VAT, for the month it is paid in.
    assert (checkout["net_amount"], checkout["vat_amount"], checkout["total_amount"]) == (
        "199.00",
        "29.85",
        "228.85",
    )
    assert checkout["redirect_url"].startswith("https://checkout.moyasar.test/")
    sent = moyasar.created[0]
    assert sent["amount_minor"] == 22885
    assert sent["success_url"] == f"{_return_url()}?checkout={checkout['id']}"
    assert sent["metadata"]["purpose"] == "subscription"


async def test_the_owners_return_activates_the_plan_once_moyasar_says_it_is_paid(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant, business, _ = await _studio(client, tenant_factory, business_factory)
    checkout = await _checkout(client, tenant, business)
    sync = f"{_billing(tenant)}/checkouts/{checkout['id']}/sync"

    # Back before paying: nothing changes.
    assert (await client.post(sync)).json()["status"] == "pending"
    assert (await _subscription(client, tenant, business))["status"] == "pending_payment"

    moyasar.pay(moyasar.created[0]["id"], amount_minor=22885)
    synced = await client.post(sync)

    assert synced.json()["status"] == "paid"
    active = await _subscription(client, tenant, business)
    assert (active["status"], active["tier"]) == ("active", "studio")


async def test_a_payment_for_the_wrong_amount_does_not_activate_the_plan(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant, business, _ = await _studio(client, tenant_factory, business_factory)
    checkout = await _checkout(client, tenant, business)
    moyasar.pay(moyasar.created[0]["id"], amount_minor=100)

    synced = await client.post(f"{_billing(tenant)}/checkouts/{checkout['id']}/sync")

    assert synced.status_code == 409
    assert (await _subscription(client, tenant, business))["status"] == "pending_payment"


async def test_the_webhook_activates_the_plan_independently(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant, business, _ = await _studio(client, tenant_factory, business_factory)
    await _checkout(client, tenant, business)
    invoice_id = moyasar.created[0]["id"]
    payment_id = moyasar.pay(invoice_id, amount_minor=22885)

    delivered = await client.post(
        "/api/v1/webhooks/moyasar",
        content=json.dumps(
            {
                "id": f"evt_{uuid4().hex[:10]}",
                "type": "payment_paid",
                "created_at": datetime.now(UTC).isoformat(),
                "secret_token": WEBHOOK_SECRET,
                "live": False,
                "data": {"id": payment_id, "status": "paid", "invoice_id": invoice_id},
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )

    assert delivered.json()["status"] == "processed"
    assert (await _subscription(client, tenant, business))["status"] == "active"


async def test_a_pending_plan_unlocks_nothing(
    client: AsyncClient, moyasar, tenant_factory, business_factory, db_session
) -> None:
    tenant, business, _ = await _studio(client, tenant_factory, business_factory)
    billing = build_billing_service(db_session, tenant.id, gateway=moyasar)

    subscription = await billing.subscription_or_default(business.id)

    assert subscription.plan.tier == "solo"
    assert subscription.subscription_amount().amount == Decimal("0.00")


async def test_nothing_to_pay_on_a_free_or_already_paid_plan(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    await client.post(
        f"{_billing(tenant)}/subscriptions", json={"business_id": str(business.id), "tier": "solo"}
    )

    response = await client.post(
        f"{_billing(tenant)}/subscriptions/{business.id}/checkout",
        json={"return_url": _return_url()},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "subscription_not_awaiting_payment"


async def test_upgrading_from_solo_waits_for_payment(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    await client.post(
        f"{_billing(tenant)}/subscriptions", json={"business_id": str(business.id), "tier": "solo"}
    )

    changed = await client.post(
        f"{_billing(tenant)}/subscriptions/{business.id}/plan", json={"tier": "studio"}
    )

    assert changed.json()["status"] == "pending_payment"


async def test_the_return_url_must_be_on_the_apps_own_site(
    client: AsyncClient, moyasar, tenant_factory, business_factory
) -> None:
    tenant, business, _ = await _studio(client, tenant_factory, business_factory)

    response = await client.post(
        f"{_billing(tenant)}/subscriptions/{business.id}/checkout",
        json={"return_url": "https://evil.example/phish"},
    )

    assert response.status_code == 422
    assert moyasar.created == []


async def test_a_month_paid_up_front_is_not_charged_again_at_the_monthly_close(
    client: AsyncClient, moyasar, tenant_factory, business_factory, db_session
) -> None:
    tenant, business, _ = await _studio(client, tenant_factory, business_factory)
    checkout = await _checkout(client, tenant, business)
    moyasar.pay(moyasar.created[0]["id"], amount_minor=22885)
    await client.post(f"{_billing(tenant)}/checkouts/{checkout['id']}/sync")

    billing = build_billing_service(db_session, tenant.id, gateway=moyasar)
    paid_month = BillingPeriod.month_containing(date.fromisoformat(checkout["covers_from"]))
    invoice = await billing.close_period(business_id=business.id, period=paid_month)

    assert invoice.subscription_amount == Decimal("0.00")
