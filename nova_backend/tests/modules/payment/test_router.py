"""Payment intents through the API: who names the amount, where the customer goes back to,
and what a deployment without a gateway answers.

Needs Postgres for the booking an intent pays for. The customer case is refused
before any row is read.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import AuthorizationError, Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.integrations.payments.moyasar import NotConfiguredPaymentGateway
from app.modules.booking.models import BookingRecord
from app.modules.payment.dependencies import get_payment_gateway, refuse_customer_amount
from app.modules.payment.models import PaymentRecord


def _customer() -> Principal:
    return Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)


@pytest.fixture
async def draft_booking(
    db_session,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
) -> BookingRecord:
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    customer = await customer_factory(tenant)
    # In the tenant's own scope, as the request that made the booking was.
    await set_tenant_scope(db_session, tenant.id)
    booking = BookingRecord(
        tenant_id=tenant.id,
        business_id=business.id,
        location_id=location.id,
        service_id=service.id,
        provider_id=provider.id,
        customer_id=customer.id,
        starts_at=datetime.now(UTC) + timedelta(days=2),
        ends_at=datetime.now(UTC) + timedelta(days=2, hours=1),
        price=Decimal("150.00"),
        currency="SAR",
        status="draft",
        source="direct_link",
    )
    db_session.add(booking)
    await db_session.flush()
    return booking


class TestWhoMaySetTheAmount:
    def test_a_customer_may_not_name_the_amount(self) -> None:
        with pytest.raises(AuthorizationError):
            refuse_customer_amount(amount=Decimal("1.00"), currency=None, principal=_customer())

    def test_a_customer_may_not_name_the_currency(self) -> None:
        with pytest.raises(AuthorizationError):
            refuse_customer_amount(amount=None, currency="USD", principal=_customer())

    def test_a_customer_paying_what_the_booking_asks_is_not_refused(self) -> None:
        refuse_customer_amount(amount=None, currency=None, principal=_customer())

    def test_staff_may_override_the_amount(self) -> None:
        staff = Principal(subject_id=uuid4(), kind=PrincipalKind.STAFF)
        refuse_customer_amount(amount=Decimal("99.00"), currency="SAR", principal=staff)


async def test_a_customer_who_sets_the_amount_is_refused(
    app: FastAPI, client: AsyncClient, tenant_factory
) -> None:
    """The audit's P6: 1.00 against a 150.00 booking reached the gateway."""
    tenant = await tenant_factory()
    app.dependency_overrides[get_principal] = _customer

    response = await client.post(
        f"/api/v1/tenants/{tenant.id}/payments/intents",
        json={
            "booking_id": str(uuid4()),
            "return_url": "http://localhost:5173/bookings/paid",
            "amount": "1.00",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_a_return_url_off_the_app_origin_is_refused(
    client: AsyncClient, draft_booking: BookingRecord
) -> None:
    """Otherwise the gateway's own page would forward a paying customer anywhere."""
    response = await client.post(
        f"/api/v1/tenants/{draft_booking.tenant_id}/payments/intents",
        json={
            "booking_id": str(draft_booking.id),
            "return_url": "https://attacker.example/after-pay",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "return_url_not_allowed"


async def test_paying_where_no_gateway_is_configured_is_a_503_and_logs_no_error(
    app: FastAPI,
    client: AsyncClient,
    draft_booking: BookingRecord,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing failed: payments are switched off on this deployment.

    It was a 500 from the catch-all handler, with a traceback logged as an
    unhandled fault on every attempt.
    """
    app.dependency_overrides[get_payment_gateway] = NotConfiguredPaymentGateway

    with caplog.at_level(logging.INFO):
        response = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/intents",
            json={
                "booking_id": str(draft_booking.id),
                "return_url": f"{get_settings().public_app_url}/bookings/paid",
            },
        )

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "integration_not_configured"
    assert error["retryable"] is False
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []


class CheckoutMoyasar(NotConfiguredPaymentGateway):
    """Moyasar's invoice and payment API, answered from dicts, recording the
    checkouts it was asked to open."""

    def __init__(self) -> None:
        self.opened: list[dict[str, Any]] = []
        self.invoices: dict[str, dict[str, Any]] = {}
        self.payments: dict[str, dict[str, Any]] = {}

    async def create_invoice(self, **kwargs: Any) -> dict[str, Any]:
        invoice_id = f"inv_{len(self.opened) + 1}"
        self.opened.append(kwargs)
        self.invoices[invoice_id] = {"id": invoice_id, "status": "initiated", "payments": []}
        return {**self.invoices[invoice_id], "url": f"https://checkout.moyasar.com/{invoice_id}"}

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        return self.invoices[invoice_id]

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self.payments[payment_id]

    def pay(self, invoice_id: str, *, amount: int = 15000, currency: str = "SAR") -> None:
        """What happens on Moyasar's page when the payer's card goes through."""
        payment = {
            "id": f"pay_for_{invoice_id}",
            "status": "paid",
            "amount": amount,
            "currency": currency,
            "invoice_id": invoice_id,
        }
        self.payments[payment["id"]] = payment
        self.invoices[invoice_id] = {
            **self.invoices[invoice_id],
            "status": "paid",
            "payments": [payment],
        }


@pytest.fixture
def checkout(app: FastAPI) -> CheckoutMoyasar:
    gateway = CheckoutMoyasar()
    app.dependency_overrides[get_payment_gateway] = lambda: gateway
    return gateway


async def _open(client: AsyncClient, booking: BookingRecord, **extra: Any):
    return await client.post(
        f"/api/v1/tenants/{booking.tenant_id}/payments/intents",
        json={
            "booking_id": str(booking.id),
            "return_url": f"{get_settings().public_app_url}/bookings?tenant={booking.tenant_id}",
            **extra,
        },
    )


class TestCheckout:
    async def test_an_intent_opens_a_moyasar_checkout_for_the_booking_price(
        self, client: AsyncClient, db_session, draft_booking: BookingRecord, checkout
    ) -> None:
        response = await _open(client, draft_booking)

        assert response.status_code == 201
        body = response.json()
        assert body["redirect_url"] == "https://checkout.moyasar.com/inv_1"
        assert body["payment"]["status"] == "pending"

        (opened,) = checkout.opened
        # The booking's own price, in halalas.
        assert opened["amount_minor"] == 15000
        assert opened["currency"] == "SAR"
        # The payer comes back to the page they left, told which payment it was,
        # and keeps whatever the page had in its query already.
        payment_id = body["payment"]["id"]
        assert opened["success_url"].endswith(
            f"/bookings?tenant={draft_booking.tenant_id}&payment={payment_id}"
        )
        assert opened["back_url"] == opened["success_url"]
        assert opened["expired_at"] > datetime.now(UTC)
        assert opened["metadata"]["booking_id"] == str(draft_booking.id)

        record = await db_session.get(PaymentRecord, UUID(payment_id))
        assert record.gateway_invoice_id == "inv_1"
        assert record.gateway_payment_id is None
        # No publishable key here, so no embedded form: the hosted page it is.
        assert body["checkout"] is None

    async def test_with_a_publishable_key_the_payer_gets_the_embedded_form(
        self, client: AsyncClient, draft_booking: BookingRecord, checkout, monkeypatch
    ) -> None:
        get_settings.cache_clear()
        monkeypatch.setenv("MOYASAR_PUBLISHABLE_KEY", "pk_test_form")
        try:
            response = await _open(client, draft_booking)
        finally:
            monkeypatch.delenv("MOYASAR_PUBLISHABLE_KEY")
            get_settings.cache_clear()

        assert response.status_code == 201
        body = response.json()
        (opened,) = checkout.opened
        payment_id = body["payment"]["id"]
        # Bound to the invoice the server opened, for the amount it decided: the
        # form cannot pay anything else.
        assert body["checkout"] == {
            "publishable_api_key": "pk_test_form",
            "invoice_id": "inv_1",
            "amount": 15000,
            "currency": "SAR",
            "description": opened["description"],
            "callback_url": opened["success_url"],
        }
        assert body["checkout"]["callback_url"].endswith(f"&payment={payment_id}")
        # The hosted page stays available for the same invoice.
        assert body["redirect_url"] == "https://checkout.moyasar.com/inv_1"

    async def test_returning_from_a_paid_checkout_captures_and_confirms(
        self, client: AsyncClient, db_session, draft_booking: BookingRecord, checkout
    ) -> None:
        opened = (await _open(client, draft_booking)).json()["payment"]
        checkout.pay("inv_1")

        response = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/{opened['id']}/sync"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "captured"
        assert response.json()["gateway_payment_id"] == "pay_for_inv_1"
        await db_session.refresh(draft_booking)
        assert draft_booking.status == "confirmed"

        # A refreshed return page changes nothing.
        again = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/{opened['id']}/sync"
        )
        assert again.json()["status"] == "captured"

    async def test_returning_without_paying_leaves_the_payment_pending(
        self, client: AsyncClient, draft_booking: BookingRecord, checkout
    ) -> None:
        """Anyone can type the return URL: the redirect itself proves nothing."""
        opened = (await _open(client, draft_booking)).json()["payment"]

        response = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/{opened['id']}/sync"
        )

        assert response.json()["status"] == "pending"

    async def test_an_expired_checkout_fails_the_payment(
        self, client: AsyncClient, draft_booking: BookingRecord, checkout
    ) -> None:
        opened = (await _open(client, draft_booking)).json()["payment"]
        checkout.invoices["inv_1"]["status"] = "expired"

        response = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/{opened['id']}/sync"
        )

        assert response.json()["status"] == "failed"
        assert response.json()["failure_code"] == "checkout_expired"

    async def test_a_checkout_paid_short_is_not_captured(
        self, client: AsyncClient, draft_booking: BookingRecord, checkout
    ) -> None:
        opened = (await _open(client, draft_booking)).json()["payment"]
        checkout.pay("inv_1", amount=100)

        response = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/{opened['id']}/sync"
        )

        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    async def test_a_stranger_cannot_sync_someone_elses_payment(
        self, app: FastAPI, client: AsyncClient, draft_booking: BookingRecord, checkout
    ) -> None:
        opened = (await _open(client, draft_booking)).json()["payment"]
        app.dependency_overrides[get_principal] = _customer

        response = await client.post(
            f"/api/v1/tenants/{draft_booking.tenant_id}/payments/{opened['id']}/sync"
        )

        assert response.status_code == 404

    async def test_less_than_one_riyal_cannot_be_paid_online(
        self, client: AsyncClient, draft_booking: BookingRecord, checkout
    ) -> None:
        """Moyasar's floor for an invoice is 100 halalas."""
        response = await _open(client, draft_booking, amount="0.50", currency="SAR")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "payment_amount_too_small"
        assert checkout.opened == []
