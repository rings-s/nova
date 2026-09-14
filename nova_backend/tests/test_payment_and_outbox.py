"""Payment webhooks and outbox delivery.

Both are paths where a mistake is expensive and invisible: an unverified
webhook that captures a payment, a retried webhook that confirms a booking
twice, or an event that is written and never delivered so a customer is simply
never told anything.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.outbox import OutboxEvent
from app.db.session import set_tenant_scope
from app.integrations.payments.moyasar import MoyasarGateway
from app.modules.booking.models import BookingRecord
from app.modules.payment.dependencies import get_payment_gateway
from app.modules.payment.models import PaymentRecord, WebhookEventRecord

WEBHOOK_SECRET = "test-webhook-secret"

#: Moyasar's record of a paid 150.00 SAR payment. Amounts are integer halalas.
PAID = {"status": "paid", "amount": 15000, "currency": "SAR"}


@pytest.fixture(autouse=True)
def _configure_moyasar(monkeypatch):
    """Gives the gateway a webhook secret so signatures can verify at all."""
    get_settings.cache_clear()
    monkeypatch.setenv("MOYASAR_API_KEY", "sk_test_x")
    monkeypatch.setenv("MOYASAR_WEBHOOK_SECRET", WEBHOOK_SECRET)
    yield
    get_settings.cache_clear()


class FakeMoyasar(MoyasarGateway):
    """The real signature check, with Moyasar's payment API answered from a dict.

    A payment it has no record of is `initiated`, as Moyasar reports one the
    customer has not paid.
    """

    def __init__(self) -> None:
        super().__init__(api_key="sk_test_x", webhook_secret=WEBHOOK_SECRET)
        self.payments: dict[str, dict[str, Any]] = {}

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self.payments.get(payment_id, {"id": payment_id, "status": "initiated"})


@pytest.fixture
def moyasar(app) -> FakeMoyasar:
    gateway = FakeMoyasar()
    app.dependency_overrides[get_payment_gateway] = lambda: gateway
    return gateway


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _deliver(client, payload: dict[str, Any], *, sign: bool = True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sign:
        headers["X-Moyasar-Signature"] = _sign(body)
    return await client.post("/api/v1/webhooks/moyasar", content=body, headers=headers)


async def _payment(db_session, tenant, *, gateway_id: str, booking_id=None) -> PaymentRecord:
    # In the tenant's own scope, as the request that opened the payment was.
    await set_tenant_scope(db_session, tenant.id)
    payment = PaymentRecord(
        tenant_id=tenant.id,
        booking_id=booking_id,
        amount=Decimal("150.00"),
        currency="SAR",
        refunded_amount=Decimal("0.00"),
        status="pending",
        gateway="moyasar",
        gateway_payment_id=gateway_id,
        webhook_verified=False,
    )
    db_session.add(payment)
    await db_session.flush()
    return payment


async def _stored_event(db_session, external_id: str) -> WebhookEventRecord:
    return (
        await db_session.execute(
            select(WebhookEventRecord).where(WebhookEventRecord.external_event_id == external_id)
        )
    ).scalar_one()


class TestWebhookVerification:
    async def test_an_unsigned_webhook_is_refused(self, client, db_session, tenant_factory):
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_unsigned")

        body = json.dumps({"id": "pay_unsigned", "status": "paid"}).encode()
        response = await client.post(
            "/api/v1/webhooks/moyasar", content=body, headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_webhook_signature"

    async def test_a_wrongly_signed_webhook_is_refused(self, client, db_session, tenant_factory):
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_forged")

        body = json.dumps({"id": "pay_forged", "status": "paid"}).encode()
        response = await client.post(
            "/api/v1/webhooks/moyasar",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Moyasar-Signature": _sign(body, "not-the-secret"),
            },
        )

        assert response.status_code == 422

    async def test_an_unverified_webhook_never_moves_the_payment(
        self, client, db_session, tenant_factory
    ):
        # The point of the whole exercise: anyone can POST to a webhook URL.
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_untouched")

        body = json.dumps({"id": "pay_untouched", "status": "paid"}).encode()
        await client.post(
            "/api/v1/webhooks/moyasar", content=body, headers={"Content-Type": "application/json"}
        )

        await db_session.refresh(payment)
        assert payment.status == "pending"
        assert payment.webhook_verified is False


class TestWebhookProcessing:
    async def test_a_verified_capture_confirms_the_booking(
        self,
        client,
        db_session,
        moyasar,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        provider_factory,
        qualify,
        customer_factory,
    ):
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
            status="pending_payment",
            source="direct_link",
        )
        db_session.add(booking)
        await db_session.flush()

        payment = await _payment(db_session, tenant, gateway_id="pay_ok", booking_id=booking.id)
        moyasar.payments["pay_ok"] = {"id": "pay_ok", **PAID}

        response = await _deliver(
            client, {"id": "pay_ok", "type": "payment_paid", "status": "paid"}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "processed"

        await db_session.refresh(payment)
        await db_session.refresh(booking)
        assert payment.status == "captured"
        assert payment.webhook_verified is True
        # Payment state drives booking state — but only through the domain.
        assert booking.status == "confirmed"

    async def test_a_redelivered_webhook_is_a_no_op(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Moyasar retries. A second capture must not be applied twice."""
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_retry")
        moyasar.payments["pay_retry"] = {"id": "pay_retry", **PAID}

        first = await _deliver(client, {"id": "pay_retry", "status": "paid"})
        second = await _deliver(client, {"id": "pay_retry", "status": "paid"})

        assert first.json()["status"] == "processed"
        assert second.json()["status"] == "duplicate"

        # Exactly one stored event, which is what makes the dedupe real.
        stored = await db_session.execute(
            select(WebhookEventRecord).where(WebhookEventRecord.external_event_id == "pay_retry")
        )
        assert len(list(stored.scalars().all())) == 1

    async def test_the_raw_payload_is_stored_for_audit(
        self, client, db_session, moyasar, tenant_factory
    ):
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_audit")
        moyasar.payments["pay_audit"] = {"id": "pay_audit", **PAID}

        await _deliver(client, {"id": "pay_audit", "status": "paid", "extra": "kept"})

        stored = await _stored_event(db_session, "pay_audit")
        assert stored.payload["extra"] == "kept"
        assert stored.signature_verified is True

    async def test_the_shared_secret_is_never_stored(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Stored, it would let anyone who can read the table sign the next webhook."""
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_token")
        moyasar.payments["pay_token"] = {"id": "pay_token", **PAID}

        # The body-token scheme: no signature header, the secret in the payload.
        response = await _deliver(
            client,
            {"id": "pay_token", "status": "paid", "secret_token": WEBHOOK_SECRET},
            sign=False,
        )

        assert response.json()["status"] == "processed"
        stored = await _stored_event(db_session, "pay_token")
        assert "secret_token" not in stored.payload
        assert WEBHOOK_SECRET not in json.dumps(stored.payload)
        await db_session.refresh(payment)
        assert payment.status == "captured"

    async def test_a_forged_capture_is_not_applied(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Signed with a leaked secret, but Moyasar's record says nobody has paid."""
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_not_paid")

        response = await _deliver(client, {"id": "pay_not_paid", "status": "paid"})

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "payment_not_confirmed"
        await db_session.refresh(payment)
        assert payment.status == "pending"
        assert payment.webhook_verified is False

    async def test_a_webhook_for_an_unknown_payment_is_acknowledged_not_retried(self, client):
        # A 5xx would make the gateway retry forever for a payment that will
        # never exist here.
        body = json.dumps({"id": "pay_never_seen", "status": "paid"}).encode()
        response = await client.post(
            "/api/v1/webhooks/moyasar",
            content=body,
            headers={"Content-Type": "application/json", "X-Moyasar-Signature": _sign(body)},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "unknown_payment"

    async def test_a_failed_payment_does_not_confirm_anything(
        self, client, db_session, moyasar, tenant_factory
    ):
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_failed")
        moyasar.payments["pay_failed"] = {"id": "pay_failed", "status": "failed"}

        await _deliver(client, {"id": "pay_failed", "status": "failed"})

        await db_session.refresh(payment)
        assert payment.status == "failed"

    @pytest.mark.parametrize(
        ("recorded", "why"),
        [
            ({"amount": 100, "currency": "SAR"}, "1.00 against 150.00"),
            ({"amount": 15000, "currency": "USD"}, "another currency"),
            ({}, "no amount at all"),
        ],
    )
    async def test_a_capture_that_does_not_match_the_payment_is_not_applied(
        self, client, db_session, moyasar, tenant_factory, recorded, why
    ):
        """Paying less than the booking required must not capture it, or confirm anything."""
        tenant = await tenant_factory()
        gateway_id = f"pay_mismatch_{uuid4().hex[:8]}"
        payment = await _payment(db_session, tenant, gateway_id=gateway_id)
        moyasar.payments[gateway_id] = {"id": gateway_id, "status": "paid", **recorded}

        response = await _deliver(client, {"id": gateway_id, "status": "paid"})

        assert response.status_code == 200, why
        assert response.json()["status"] == "amount_mismatch", why
        await db_session.refresh(payment)
        assert payment.status == "pending", why

        stored = await _stored_event(db_session, gateway_id)
        assert stored.processed_at is not None
        assert "not captured" in (stored.error or "")


class TestOutboxDelivery:
    """`publish_event` writes; the dispatcher delivers. Both halves matter."""

    async def test_a_booking_writes_its_event_in_the_same_transaction(
        self,
        client,
        db_session,
        tenant_factory,
        business_factory,
        location_factory,
        service_factory,
        provider_factory,
        qualify,
        customer_factory,
    ):
        tenant = await tenant_factory()
        business = await business_factory(tenant)
        location = await location_factory(business)
        service = await service_factory(location)
        provider = await provider_factory(location)
        await qualify(provider, service)
        customer = await customer_factory(tenant)

        base = f"/api/v1/tenants/{tenant.id}"
        created = await client.post(
            f"{base}/bookings",
            json={
                "location_id": str(location.id),
                "service_id": str(service.id),
                "provider_id": str(provider.id),
                "starts_at": (datetime.now(UTC) + timedelta(days=9))
                .replace(microsecond=0)
                .isoformat(),
                "on_behalf_of_customer_id": str(customer.id),
            },
        )
        assert created.status_code == 201

        events = (
            (
                await db_session.execute(
                    select(OutboxEvent).where(OutboxEvent.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )

        names = {e.event_name for e in events}
        assert "BookingCreated" in names
        # Unpublished on write: the dispatcher is what delivers them.
        assert all(e.published_at is None for e in events)

    async def test_an_event_payload_carries_no_raw_decimals_or_uuids(
        self, db_session, tenant_factory
    ):
        # The outbox column is JSONB; a UUID or Decimal that reached it
        # unconverted would fail to serialise at publish time, long after the
        # request that caused it.
        from app.core.events import publish_event
        from app.modules.booking.events import BookingCreated

        tenant = await tenant_factory()
        await publish_event(
            db_session,
            BookingCreated(
                tenant_id=tenant.id,
                booking_id=uuid4(),
                customer_id=uuid4(),
                starts_at=datetime.now(UTC),
            ),
        )
        await db_session.flush()

        event = (
            (
                await db_session.execute(
                    select(OutboxEvent).where(OutboxEvent.tenant_id == tenant.id)
                )
            )
            .scalars()
            .first()
        )

        assert event is not None
        # Round-trips through JSON without complaint.
        json.dumps(event.payload)
        assert isinstance(event.payload["booking_id"], str)

    def test_retries_back_off_and_eventually_dead_letter(self):
        event = OutboxEvent(
            event_name="BookingConfirmed",
            tenant_id=uuid4(),
            payload={},
            occurred_at=datetime.now(UTC),
        )
        event.attempts = 0

        first_due = None
        for _ in range(10):
            event.schedule_retry("boom")
            if first_due is None:
                first_due = event.available_at

        # Parked far in the future rather than retried forever, and the row
        # survives as the evidence of what failed.
        assert event.is_dead_lettered
        assert event.last_error == "boom"
        assert event.available_at > datetime.now(UTC) + timedelta(days=3000)

    def test_a_published_event_is_not_dead_lettered(self):
        event = OutboxEvent(
            event_name="BookingConfirmed",
            tenant_id=uuid4(),
            payload={},
            occurred_at=datetime.now(UTC),
        )
        event.attempts = 99
        event.mark_published()
        assert not event.is_dead_lettered
        assert event.last_error is None
