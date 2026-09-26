"""payment · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Two routers with very different security models:

  `router`         tenant-scoped, bearer-authenticated like everything else.
  `webhook_router` public, authenticated by signature alone. It is the only
                   unauthenticated write path in the system, which is why the
                   handler verifies before it reads anything and records the
                   raw payload before it acts.
"""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.idempotency import IdempotencyGuard, idempotency_guard
from app.core.schemas import Page
from app.core.security import Principal, get_principal
from app.core.throttling import write_rate_limit
from app.db.session import bypass_tenant_scope, set_tenant_scope
from app.modules.billing.dependencies import build_billing_service, subscription_checkout_tenant
from app.modules.identity.dependencies import RequirePermission
from app.modules.identity.domain import StaffPermission
from app.modules.payment.dependencies import (
    build_payment_service,
    get_payment_gateway,
    get_payment_service,
    get_webhook_processor,
    refuse_customer_amount,
)
from app.modules.payment.domain import (
    Payment,
    PaymentAmountMismatchError,
    PaymentVerificationError,
    WebhookSignatureError,
)
from app.modules.payment.exceptions import UnknownWebhookPaymentError
from app.modules.payment.schemas import (
    CreatePaymentIntentRequest,
    PaymentIntentOut,
    PaymentOut,
    RefundPaymentRequest,
    WebhookAckOut,
)
from app.modules.payment.service import PaymentService, PaymentWebhookProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_id}/payments", tags=["payment"])


def _payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        booking_id=p.booking_id,
        amount=p.amount.amount,
        currency=p.amount.currency,
        status=p.status,
        gateway=p.gateway,
        gateway_payment_id=p.gateway_payment_id,
        webhook_verified=p.webhook_verified,
        refunded_amount=p.refunded_amount,
        failure_code=p.failure_code,
        captured_at=p.captured_at,
        created_at=p.created_at,
    )


@router.post(
    "/intents",
    response_model=PaymentIntentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def create_payment_intent(
    tenant_id: UUID,
    payload: CreatePaymentIntentRequest,
    session: AsyncSession = Depends(get_db_session),
    service: PaymentService = Depends(get_payment_service),
    principal: Principal = Depends(get_principal),
    guard: IdempotencyGuard = Depends(idempotency_guard("POST /payments/intents")),
) -> object:
    """Starts a payment. Send an `Idempotency-Key` — a retried intent that
    creates a second gateway payment is a customer charged twice.

    Guarded on the booking: the request names a `booking_id`, and without a
    check any authenticated caller could open a real gateway payment against a
    stranger's appointment and read its price back in the response.
    """
    # Every check before the replay, so a stored response reaches only a caller
    # who could make this request now.
    refuse_customer_amount(amount=payload.amount, currency=payload.currency, principal=principal)
    await service.bookings.assert_visible_to(payload.booking_id, principal)

    body = payload.model_dump(mode="json")
    replay = await guard.begin(body)
    if replay is not None:
        return replay

    intent = await service.create_intent(**payload.model_dump())
    out = PaymentIntentOut(payment=_payment_out(intent.payment), redirect_url=intent.redirect_url)
    await guard.complete(status_code=status.HTTP_201_CREATED, body=out.model_dump(mode="json"))
    await session.commit()
    return out


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    tenant_id: UUID,
    payment_id: UUID,
    service: PaymentService = Depends(get_payment_service),
    principal: Principal = Depends(get_principal),
) -> PaymentOut:
    """One payment, if the caller may see its booking.

    Visibility is inherited from the booking rather than decided here, so a
    customer cannot read a stranger's amount, gateway id, or refund state.
    """
    return _payment_out(await service.get_for_principal(payment_id, principal))


@router.get("", response_model=Page[PaymentOut])
async def list_payments_for_booking(
    tenant_id: UUID,
    booking_id: UUID,
    service: PaymentService = Depends(get_payment_service),
    principal: Principal = Depends(get_principal),
) -> Page[PaymentOut]:
    """Guarded on the booking too — otherwise a payment that cannot be read by
    its own id is still readable by naming the booking it belongs to."""
    payments = await service.list_for_booking_for_principal(booking_id, principal)
    return Page(items=[_payment_out(p) for p in payments], total=len(payments))


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentOut,
    dependencies=[
        Depends(RequirePermission(StaffPermission.REFUND_PAYMENTS)),
        Depends(write_rate_limit),
    ],
)
async def refund_payment(
    tenant_id: UUID,
    payment_id: UUID,
    payload: RefundPaymentRequest,
    session: AsyncSession = Depends(get_db_session),
    service: PaymentService = Depends(get_payment_service),
    guard: IdempotencyGuard = Depends(idempotency_guard("POST /payments/refund")),
) -> object:
    """Refunds a captured payment. Owners and managers only (`refund_payments`),
    and idempotency-keyed — a double-submitted refund is real money leaving
    twice. The permission is a route dependency, so it is checked before any
    replay."""
    body = payload.model_dump(mode="json")
    replay = await guard.begin({**body, "payment_id": str(payment_id)})
    if replay is not None:
        return replay

    payment = await service.refund(payment_id, **payload.model_dump())
    out = _payment_out(payment)
    await guard.complete(status_code=200, body=out.model_dump(mode="json"))
    await session.commit()
    return out


@router.post(
    "/{payment_id}/sync",
    response_model=PaymentOut,
    dependencies=[Depends(write_rate_limit)],
)
async def sync_payment(
    tenant_id: UUID,
    payment_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    service: PaymentService = Depends(get_payment_service),
    principal: Principal = Depends(get_principal),
) -> PaymentOut:
    """Asks Moyasar where this payment stands, and records it.

    Called by the page a payer returns to from checkout. The redirect itself
    proves nothing — anyone can type the URL — so this reads Moyasar's own
    record of the payment and checks status, amount and currency before
    capturing, exactly as a webhook would. Visible to whoever may see the
    booking; idempotent, so a refreshed page does no harm.
    """
    await service.get_for_principal(payment_id, principal)
    try:
        payment = await service.reconcile(payment_id)
    except PaymentVerificationError:
        # Nothing captured; the payer sees the payment still pending, and the
        # mismatch is in the logs for a person to look at.
        logger.error("payment_sync_verification_failed", extra={"payment_id": str(payment_id)})
        payment = await service.get(payment_id)
    await session.commit()
    return _payment_out(payment)


# --- webhooks -------------------------------------------------------------

webhook_router = APIRouter(prefix="/webhooks", tags=["payment"])


@webhook_router.post("/moyasar", response_model=WebhookAckOut)
async def moyasar_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    processor: PaymentWebhookProcessor = Depends(get_webhook_processor),
    gateway=Depends(get_payment_gateway),
) -> WebhookAckOut:
    """Receives a Moyasar webhook (https://docs.moyasar.com/api/other/webhooks/webhook-reference/).

    The body is `{id, type, created_at, secret_token, account_name, live,
    data}`, with the payment in `data`. Order is deliberate and each step
    protects the next:

      1. Parse the body, refusing anything that is not a JSON object.
      2. Check `secret_token` against the webhook's shared secret. Nothing
         before this point is trusted, and an unverified payload never reaches
         a service.
      3. Record the event, less its shared secret, and stop if it is a
         duplicate — Moyasar retries, and applying a capture twice
         double-confirms a booking.
      4. Resolve the tenant from the payment (the one cross-tenant read in the
         application), then re-scope the connection for RLS.
      5. Apply the status change that Moyasar's own record of the payment
         confirms, which a forged webhook cannot supply.

    Answers 200 once the signature verifies, including for events we do not act
    on: a non-2xx makes the gateway retry an event that will never succeed. The
    exception is a claim Moyasar's record does not confirm, answered 503 so the
    gateway retries it, with nothing recorded.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise WebhookSignatureError() from None
    if not isinstance(payload, dict):
        raise WebhookSignatureError()

    processor.verify(payload=payload)

    # Cross-tenant reads and writes: this connection has no tenant yet, and
    # RLS would otherwise (correctly) show it nothing.
    await bypass_tenant_scope(session)

    event, is_duplicate = await processor.record(payload=payload, signature_verified=True)
    if is_duplicate:
        await session.commit()
        return WebhookAckOut(status="duplicate")

    data = payload.get("data")
    if not isinstance(data, dict):
        data = {}
    gateway_payment_id = str(data.get("id") or "")
    gateway_invoice_id = str(data.get("invoice_id") or "") or None
    gateway_status = str(data.get("status") or "")

    if payload.get("live") is False and get_settings().env == "production":
        # A test-mode event reaching production: someone pointed a test
        # webhook here. Nothing a test card "paid" may confirm a real booking.
        await processor.events.mark_processed(
            event, now=datetime.now(UTC), error="test-mode event on a live deployment"
        )
        await session.commit()
        return WebhookAckOut(status="ignored")

    if not gateway_payment_id:
        await processor.events.mark_processed(
            event, now=datetime.now(UTC), error="payload had no payment id"
        )
        await session.commit()
        return WebhookAckOut(status="ignored")

    # A payment on a plan checkout: NOVA's own revenue, which billing owns,
    # not a salon's takings. The same verification applies (billing checks
    # Moyasar's record of the payment before activating anything).
    plan_tenant = (
        await subscription_checkout_tenant(session, gateway_invoice_id)
        if gateway_invoice_id
        else None
    )
    if plan_tenant is not None and gateway_invoice_id:
        await set_tenant_scope(session, plan_tenant)
        billing = build_billing_service(session, plan_tenant, gateway=gateway)
        try:
            await billing.apply_gateway_payment(
                gateway_payment_id=gateway_payment_id,
                gateway_invoice_id=gateway_invoice_id,
                gateway_status=gateway_status,
            )
        except PaymentVerificationError as exc:
            await processor.events.mark_processed(
                event, now=datetime.now(UTC), tenant_id=plan_tenant, error=exc.message
            )
            await session.commit()
            logger.error(
                "webhook_plan_payment_not_verified",
                extra={"gateway_payment_id": gateway_payment_id, "reason": exc.code},
            )
            return WebhookAckOut(
                status="amount_mismatch"
                if isinstance(exc, PaymentAmountMismatchError)
                else "checkout_mismatch"
            )
        await processor.events.mark_processed(event, now=datetime.now(UTC), tenant_id=plan_tenant)
        await session.commit()
        return WebhookAckOut(status="processed")

    try:
        tenant_id = await processor.resolve_tenant(gateway_payment_id, gateway_invoice_id)
    except UnknownWebhookPaymentError:
        # Recorded, acknowledged, and not retried. A payment we have never
        # seen will not appear later, so making the gateway retry forever
        # helps nobody.
        await processor.events.mark_processed(
            event, now=datetime.now(UTC), error="no local payment for gateway id"
        )
        await session.commit()
        logger.warning("webhook_unknown_payment", extra={"gateway_payment_id": gateway_payment_id})
        return WebhookAckOut(status="unknown_payment")

    await set_tenant_scope(session, tenant_id)

    # Built through the module factory rather than `Depends`: the tenant is
    # only known now, and the DI chain for a tenant-scoped service requires a
    # bearer token the gateway does not have. The factory keeps this wiring
    # identical to the request path's.
    payment_service = build_payment_service(session, tenant_id, gateway=gateway)

    try:
        await payment_service.apply_gateway_status(
            gateway_payment_id=gateway_payment_id,
            gateway_invoice_id=gateway_invoice_id,
            gateway_status=gateway_status,
            webhook_verified=True,
        )
    except PaymentVerificationError as exc:
        # Recorded, acknowledged and left uncaptured for a person to look at. A
        # non-2xx would make the gateway retry a payment that will never match.
        await processor.events.mark_processed(
            event, now=datetime.now(UTC), tenant_id=tenant_id, error=exc.message
        )
        await session.commit()
        logger.error(
            "webhook_payment_not_verified",
            extra={
                "gateway_payment_id": gateway_payment_id,
                "tenant_id": str(tenant_id),
                "reason": exc.code,
            },
        )
        return WebhookAckOut(
            status="amount_mismatch"
            if isinstance(exc, PaymentAmountMismatchError)
            else "checkout_mismatch"
        )
    await processor.events.mark_processed(event, now=datetime.now(UTC), tenant_id=tenant_id)
    await session.commit()
    return WebhookAckOut(status="processed")
