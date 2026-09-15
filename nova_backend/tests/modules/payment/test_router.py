"""Payment intents through the API: who names the amount, and where the customer goes back to.

Needs Postgres for the booking an intent pays for. The customer case is refused
before any row is read.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.security import AuthorizationError, Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.modules.booking.models import BookingRecord
from app.modules.payment.dependencies import refuse_customer_amount


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
