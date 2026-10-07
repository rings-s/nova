"""Payment webhooks and outbox delivery.

Both are paths where a mistake is expensive and invisible: an unverified
webhook that captures a payment, a retried webhook that confirms a booking
twice, or an event that is written and never delivered so a customer is simply
never told anything.
"""

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
    """Gives the gateway a webhook secret so webhooks can verify at all."""
    get_settings.cache_clear()
    monkeypatch.setenv("MOYASAR_API_KEY", "sk_test_x")
    monkeypatch.setenv("MOYASAR_WEBHOOK_SECRET", WEBHOOK_SECRET)
    yield
    get_settings.cache_clear()


class FakeMoyasar(MoyasarGateway):
    """The real webhook check, with Moyasar's API answered from dicts.

    A payment it has no record of is `initiated`, as Moyasar reports one the
    customer has not paid; an invoice it has no record of is still open.
    """

    def __init__(self) -> None:
        super().__init__(api_key="sk_test_x", webhook_secret=WEBHOOK_SECRET)
        self.payments: dict[str, dict[str, Any]] = {}
        self.invoices: dict[str, dict[str, Any]] = {}

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return self.payments.get(payment_id, {"id": payment_id, "status": "initiated"})

    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        return self.invoices.get(
            invoice_id, {"id": invoice_id, "status": "initiated", "payments": []}
        )


@pytest.fixture
def moyasar(app) -> FakeMoyasar:
    gateway = FakeMoyasar()
    app.dependency_overrides[get_payment_gateway] = lambda: gateway
    return gateway


def _event(
    data: dict[str, Any],
    *,
    event_id: str | None = None,
    type: str = "payment_paid",
    secret_token: str | None = WEBHOOK_SECRET,
    live: bool = False,
) -> dict[str, Any]:
    """A webhook body as Moyasar documents it: the payment rides in `data`."""
    body: dict[str, Any] = {
        "id": event_id or f"evt_{uuid4().hex[:12]}",
        "type": type,
        "created_at": datetime.now(UTC).isoformat(),
        "account_name": "NOVA test",
        "live": live,
        "data": data,
    }
    if secret_token is not None:
        body["secret_token"] = secret_token
    return body


async def _deliver(client, payload: dict[str, Any]):
    return await client.post(
        "/api/v1/webhooks/moyasar",
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )


async def _payment(
    db_session,
    tenant,
    *,
    gateway_id: str | None = None,
    invoice_id: str | None = None,
    booking_id=None,
) -> PaymentRecord:
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
        gateway_invoice_id=invoice_id,
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


async def _pending_booking(
    db_session,
    tenant,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    qualify,
    customer_factory,
) -> BookingRecord:
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
    return booking


class TestWebhookVerification:
    async def test_a_webhook_without_its_secret_token_is_refused(
        self, client, db_session, tenant_factory
    ):
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_unsigned")

        response = await _deliver(
            client, _event({"id": "pay_unsigned", "status": "paid"}, secret_token=None)
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_webhook_signature"

    async def test_a_webhook_with_the_wrong_secret_token_is_refused(
        self, client, db_session, tenant_factory
    ):
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_forged")

        response = await _deliver(
            client,
            _event({"id": "pay_forged", "status": "paid"}, secret_token="not-the-secret"),
        )

        assert response.status_code == 422

    async def test_a_signature_header_is_not_a_substitute_for_the_token(
        self, client, db_session, tenant_factory
    ):
        """Moyasar documents one scheme, the body's `secret_token`. A header
        scheme it never sends is only another way in."""
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_header")

        body = json.dumps(_event({"id": "pay_header", "status": "paid"}, secret_token=None))
        response = await client.post(
            "/api/v1/webhooks/moyasar",
            content=body.encode(),
            headers={"Content-Type": "application/json", "X-Moyasar-Signature": "anything"},
        )

        assert response.status_code == 422

    async def test_an_unverified_webhook_never_moves_the_payment(
        self, client, db_session, tenant_factory
    ):
        # The point of the whole exercise: anyone can POST to a webhook URL.
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_untouched")

        await _deliver(client, _event({"id": "pay_untouched", "status": "paid"}, secret_token=None))

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
        booking = await _pending_booking(
            db_session,
            tenant,
            business_factory,
            location_factory,
            service_factory,
            provider_factory,
            qualify,
            customer_factory,
        )
        payment = await _payment(db_session, tenant, gateway_id="pay_ok", booking_id=booking.id)
        moyasar.payments["pay_ok"] = {"id": "pay_ok", **PAID}

        response = await _deliver(client, _event({"id": "pay_ok", "status": "paid"}))

        assert response.status_code == 200
        assert response.json()["status"] == "processed"

        await db_session.refresh(payment)
        await db_session.refresh(booking)
        assert payment.status == "captured"
        assert payment.webhook_verified is True
        # Payment state drives booking state — but only through the domain.
        assert booking.status == "confirmed"

    async def test_a_paid_checkout_is_found_by_its_invoice_and_learns_its_payment_id(
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
        """The usual case: NOVA opened an invoice, and the first it hears of the
        payment that paid it is this webhook."""
        tenant = await tenant_factory()
        booking = await _pending_booking(
            db_session,
            tenant,
            business_factory,
            location_factory,
            service_factory,
            provider_factory,
            qualify,
            customer_factory,
        )
        payment = await _payment(db_session, tenant, invoice_id="inv_1", booking_id=booking.id)
        moyasar.payments["pay_new"] = {"id": "pay_new", "invoice_id": "inv_1", **PAID}

        response = await _deliver(
            client, _event({"id": "pay_new", "invoice_id": "inv_1", "status": "paid"})
        )

        assert response.json()["status"] == "processed"
        await db_session.refresh(payment)
        await db_session.refresh(booking)
        assert payment.status == "captured"
        # Kept, because a refund is made against it.
        assert payment.gateway_payment_id == "pay_new"
        assert booking.status == "confirmed"

    async def test_a_paid_payment_for_another_checkout_does_not_capture_this_one(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Signed with the shared secret, naming our invoice, and pointing at a
        real paid payment of the same amount — for somebody else's invoice."""
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, invoice_id="inv_ours")
        moyasar.payments["pay_theirs"] = {"id": "pay_theirs", "invoice_id": "inv_other", **PAID}

        response = await _deliver(
            client, _event({"id": "pay_theirs", "invoice_id": "inv_ours", "status": "paid"})
        )

        assert response.status_code == 200
        assert response.json()["status"] == "checkout_mismatch"
        await db_session.refresh(payment)
        assert payment.status == "pending"
        assert payment.gateway_payment_id is None

    async def test_a_declined_card_on_an_open_checkout_does_not_fail_the_payment(
        self, client, db_session, moyasar, tenant_factory
    ):
        """The payer is still on Moyasar's page and can try another card."""
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, invoice_id="inv_open")
        moyasar.payments["pay_declined"] = {
            "id": "pay_declined",
            "invoice_id": "inv_open",
            "status": "failed",
        }

        response = await _deliver(
            client,
            _event(
                {"id": "pay_declined", "invoice_id": "inv_open", "status": "failed"},
                type="payment_failed",
            ),
        )

        assert response.json()["status"] == "processed"
        await db_session.refresh(payment)
        assert payment.status == "pending"

    async def test_a_redelivered_webhook_is_a_no_op(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Moyasar retries. A second capture must not be applied twice."""
        tenant = await tenant_factory()
        await _payment(db_session, tenant, gateway_id="pay_retry")
        moyasar.payments["pay_retry"] = {"id": "pay_retry", **PAID}
        event = _event({"id": "pay_retry", "status": "paid"}, event_id="evt_retry")

        first = await _deliver(client, event)
        second = await _deliver(client, event)

        assert first.json()["status"] == "processed"
        assert second.json()["status"] == "duplicate"

        # Exactly one stored event, which is what makes the dedupe real.
        stored = await db_session.execute(
            select(WebhookEventRecord).where(WebhookEventRecord.external_event_id == "evt_retry")
        )
        assert len(list(stored.scalars().all())) == 1

    async def test_the_payload_is_stored_for_audit_without_its_secret(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Stored, the secret would let anyone who can read the table send the
        next webhook."""
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_audit")
        moyasar.payments["pay_audit"] = {"id": "pay_audit", **PAID}

        response = await _deliver(
            client,
            _event({"id": "pay_audit", "status": "paid", "extra": "kept"}, event_id="evt_audit"),
        )

        assert response.json()["status"] == "processed"
        stored = await _stored_event(db_session, "evt_audit")
        assert stored.event_type == "payment_paid"
        assert stored.payload["data"]["extra"] == "kept"
        assert stored.signature_verified is True
        assert "secret_token" not in stored.payload
        assert WEBHOOK_SECRET not in json.dumps(stored.payload)
        await db_session.refresh(payment)
        assert payment.status == "captured"

    async def test_a_forged_capture_is_not_applied(
        self, client, db_session, moyasar, tenant_factory
    ):
        """Sent with a leaked secret, but Moyasar's record says nobody has paid."""
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_not_paid")

        response = await _deliver(client, _event({"id": "pay_not_paid", "status": "paid"}))

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "payment_not_confirmed"
        await db_session.refresh(payment)
        assert payment.status == "pending"
        assert payment.webhook_verified is False

    async def test_a_webhook_for_an_unknown_payment_is_acknowledged_not_retried(self, client):
        # A 5xx would make the gateway retry forever for a payment that will
        # never exist here.
        response = await _deliver(client, _event({"id": "pay_never_seen", "status": "paid"}))
        assert response.status_code == 200
        assert response.json()["status"] == "unknown_payment"

    async def test_a_failed_payment_does_not_confirm_anything(
        self, client, db_session, moyasar, tenant_factory
    ):
        tenant = await tenant_factory()
        payment = await _payment(db_session, tenant, gateway_id="pay_failed")
        moyasar.payments["pay_failed"] = {"id": "pay_failed", "status": "failed"}

        await _deliver(
            client, _event({"id": "pay_failed", "status": "failed"}, type="payment_failed")
        )

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

        event_id = f"evt_{gateway_id}"
        response = await _deliver(
            client, _event({"id": gateway_id, "status": "paid"}, event_id=event_id)
        )

        assert response.status_code == 200, why
        assert response.json()["status"] == "amount_mismatch", why
        await db_session.refresh(payment)
        assert payment.status == "pending", why

        stored = await _stored_event(db_session, event_id)
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

    async def test_a_failing_handler_does_not_undo_another_handlers_work(
        self, db_session, tenant_factory, monkeypatch
    ):
        """Commission must not roll back because a WhatsApp message failed."""
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.worker import outbox

        tenant = await tenant_factory()
        probe = OutboxEvent(
            event_name="OutboxProbe", tenant_id=tenant.id, payload={}, occurred_at=datetime.now(UTC)
        )
        db_session.add(probe)
        await db_session.flush()

        async def accrues(session, tenant_id, payload):
            session.add(
                OutboxEvent(
                    event_name="OutboxProbeAccrued",
                    tenant_id=tenant_id,
                    payload={},
                    occurred_at=datetime.now(UTC),
                )
            )
            await session.flush()

        async def notifies(session, tenant_id, payload):
            session.add(
                OutboxEvent(
                    event_name="OutboxProbeNotified",
                    tenant_id=tenant_id,
                    payload={},
                    occurred_at=datetime.now(UTC),
                )
            )
            await session.flush()
            raise RuntimeError("whatsapp down")

        monkeypatch.setattr(outbox, "handlers_for", lambda name: [accrues, notifies])
        factory = async_sessionmaker(
            bind=db_session.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

        ok = await outbox._process_one(
            factory, event_id=probe.id, event_name="OutboxProbe", tenant_id=tenant.id, payload={}
        )

        assert ok is False
        names = set(
            (
                await db_session.execute(
                    select(OutboxEvent.event_name).where(OutboxEvent.tenant_id == tenant.id)
                )
            )
            .scalars()
            .all()
        )
        # The first handler's write survived; the failing one's did not.
        assert "OutboxProbeAccrued" in names
        assert "OutboxProbeNotified" not in names
        await db_session.refresh(probe)
        assert probe.published_at is None
        assert probe.attempts == 1
        assert probe.last_error == "notifies: whatsapp down"

    async def test_an_event_whose_handlers_all_succeed_is_published(
        self, db_session, tenant_factory, monkeypatch
    ):
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.worker import outbox

        tenant = await tenant_factory()
        probe = OutboxEvent(
            event_name="OutboxProbe", tenant_id=tenant.id, payload={}, occurred_at=datetime.now(UTC)
        )
        db_session.add(probe)
        await db_session.flush()

        async def quiet(session, tenant_id, payload):
            return None

        monkeypatch.setattr(outbox, "handlers_for", lambda name: [quiet, quiet])
        factory = async_sessionmaker(
            bind=db_session.bind, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

        ok = await outbox._process_one(
            factory, event_id=probe.id, event_name="OutboxProbe", tenant_id=tenant.id, payload={}
        )

        assert ok is True
        await db_session.refresh(probe)
        assert probe.published_at is not None

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
