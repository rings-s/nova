"""payment · APPLICATION layer — use cases.

Layer rule: domain, repository, events, integrations, and other modules'
*services*. Must not import fastapi or another module's models/repository.

Services flush, never commit. The router owns the transaction boundary.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.core.events import publish_event
from app.core.security import Principal
from app.core.values import Money, TimeRange
from app.integrations.base import IntegrationNotConfiguredError
from app.integrations.payments.moyasar import PaymentGateway
from app.modules.booking.domain import BookingStatus
from app.modules.booking.service import BookingService
from app.modules.payment.domain import (
    Payment,
    PaymentAmountMismatchError,
    PaymentFact,
    PaymentStatus,
    Refund,
    WebhookSignatureError,
    assert_return_url_allowed,
    deposit_for,
    paid_amount_matches,
    to_minor_units,
)
from app.modules.payment.events import (
    PaymentCaptured,
    PaymentFailed,
    PaymentIntentCreated,
    PaymentRefunded,
)
from app.modules.payment.exceptions import (
    PaymentNotConfirmedError,
    PaymentNotFoundError,
    UnknownWebhookPaymentError,
)
from app.modules.payment.repository import PaymentRepository, WebhookEventRepository

logger = logging.getLogger(__name__)

#: Gateway statuses that mean the money actually arrived.
_CAPTURED_GATEWAY_STATUSES = frozenset({"paid", "captured"})
_FAILED_GATEWAY_STATUSES = frozenset({"failed", "voided", "expired"})


@dataclass(frozen=True)
class PaymentIntent:
    """A payment plus wherever the customer has to go to complete it."""

    payment: Payment
    redirect_url: str | None


class PaymentService:
    def __init__(
        self,
        *,
        repository: PaymentRepository,
        gateway: PaymentGateway,
        bookings: BookingService,
        tenant_id: UUID,
        public_app_url: str,
        default_deposit_percent: int = 0,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.bookings = bookings
        self.tenant_id = tenant_id
        #: The customer app. A payment's `return_url` must be on its origin.
        self.public_app_url = public_app_url
        self.default_deposit_percent = default_deposit_percent

    @property
    def session(self):
        return self.repository.session

    # --- intents ----------------------------------------------------------

    async def create_intent(
        self,
        *,
        booking_id: UUID,
        return_url: str,
        amount: Decimal | None = None,
        currency: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> PaymentIntent:
        """Starts a payment for a booking, and moves it to PENDING_PAYMENT.

        The amount is derived from the booking's own price and the tenant's
        deposit policy unless staff override it. Taking it from the request
        body by default would let a client decide what to pay, which is why the
        router refuses an override from anyone else (`refuse_customer_amount`).
        """
        # First, before anything is written or sent to the gateway.
        assert_return_url_allowed(return_url, app_url=self.public_app_url)
        booking = await self.bookings.get(booking_id)

        if amount is None:
            due = deposit_for(booking.price, deposit_percent=self.default_deposit_percent)
            # A 0% deposit policy still produces a payable record when someone
            # explicitly asks to pay — they are settling the full price.
            due = booking.price if due.amount == 0 else due
        else:
            due = Money(amount=amount, currency=currency or booking.price.currency)

        payment = await self.repository.add_payment(
            Payment(
                id=uuid4(),
                tenant_id=self.tenant_id,
                booking_id=booking_id,
                amount=due,
                status=PaymentStatus.PENDING,
            )
        )

        redirect_url: str | None = None
        gateway_payment_id: str | None = None
        try:
            created = await self.gateway.create_payment(
                amount_minor=to_minor_units(due),
                currency=due.currency,
                description=f"NOVA booking {booking_id}",
                callback_url=return_url,
                metadata={
                    **(metadata or {}),
                    # Echoed back on the webhook, which is how a payment is
                    # tied to its booking even if our own id lookup fails.
                    "booking_id": str(booking_id),
                    "tenant_id": str(self.tenant_id),
                    "payment_id": str(payment.id),
                },
            )
            gateway_payment_id = created.get("id")
            redirect_url = (created.get("source") or {}).get("transaction_url")
        except IntegrationNotConfiguredError:
            # No gateway on this deployment: the caller gets a 503, and nothing
            # failed that a traceback on every attempt would help anyone find.
            raise
        except Exception:
            # The local record stays PENDING so the failure is visible and
            # retryable, rather than vanishing with the exception.
            logger.exception("moyasar_create_payment_failed", extra={"payment_id": str(payment.id)})
            raise

        if gateway_payment_id:
            payment.gateway_payment_id = gateway_payment_id
            payment = await self.repository.save(payment)

        # The booking now waits on money. Deliberately not CONFIRMED: docs/06
        # section 7 keeps the two state machines separate.
        #
        # Compared against the enum member rather than `.value`: BookingStatus
        # is a StrEnum, so this holds whether the status arrived as the enum or
        # as a bare string from a raw insert. `.value` assumes the former and
        # raises AttributeError on the latter.
        if booking.status == BookingStatus.DRAFT:
            await self.bookings.require_payment(booking_id)

        await publish_event(
            self.session,
            PaymentIntentCreated(
                tenant_id=self.tenant_id,
                payment_id=payment.id,
                booking_id=booking_id,
                amount=str(due.amount),
                currency=due.currency,
            ),
        )
        return PaymentIntent(payment=payment, redirect_url=redirect_url)

    async def get(self, payment_id: UUID) -> Payment:
        payment = await self.repository.get_payment(payment_id)
        if payment is None:
            raise PaymentNotFoundError(payment_id)
        return payment

    async def list_for_booking(self, booking_id: UUID) -> list[Payment]:
        return await self.repository.list_for_booking(booking_id)

    async def list_payment_facts(self, *, window: TimeRange, limit: int) -> list[PaymentFact]:
        """For the analytics context (docs/13 section 6.2)."""
        return await self.repository.list_facts(window=window, limit=limit)

    async def get_for_principal(self, payment_id: UUID, principal: Principal) -> Payment:
        """A payment the caller is entitled to see.

        Visibility is inherited from the booking rather than decided again
        here: a payment belongs to whoever the appointment belongs to, and
        duplicating that rule is how the two drift apart.

        A payment with no booking is staff-only. There is no customer to
        inherit from, and the only way to create one today is through a
        booking, so this is an invariant rather than a real branch.
        """
        payment = await self.get(payment_id)
        if principal.is_staff:
            return payment
        if payment.booking_id is None:
            raise PaymentNotFoundError(payment_id)

        # Raises BookingNotFoundError (404) when the booking is not theirs.
        # Deliberately not re-raised as PaymentNotFoundError: either way the
        # caller learns nothing about whether the id exists.
        await self.bookings.assert_visible_to(payment.booking_id, principal)
        return payment

    async def list_for_booking_for_principal(
        self, booking_id: UUID, principal: Principal
    ) -> list[Payment]:
        """Without this, hardening `get_for_principal` would be cosmetic: a
        payment unreadable by its own id was still readable by naming its
        booking."""
        await self.bookings.assert_visible_to(booking_id, principal)
        return await self.list_for_booking(booking_id)

    # --- state changes ----------------------------------------------------

    async def capture(
        self,
        payment_id: UUID,
        *,
        webhook_verified: bool = False,
        confirm_booking: bool = True,
        now: datetime | None = None,
    ) -> Payment:
        """Records that money arrived, and confirms the booking.

        Idempotent (docs/08 section 14): a payment already CAPTURED returns
        unchanged instead of raising. Moyasar retries webhooks, and the second
        delivery must not double-confirm a booking or trip a transition error
        that makes the gateway retry forever.
        """
        now = now or datetime.now(UTC)
        payment = await self.get(payment_id)

        if payment.status is PaymentStatus.CAPTURED:
            return payment

        payment.mark_captured(now=now, webhook_verified=webhook_verified)
        saved = await self.repository.save(payment)

        if confirm_booking and saved.booking_id is not None:
            booking = await self.bookings.get(saved.booking_id)
            # Only advance a booking that is actually waiting. A cancelled
            # booking whose payment lands late must not spring back to life.
            if booking.status in (BookingStatus.DRAFT, BookingStatus.PENDING_PAYMENT):
                await self.bookings.confirm(saved.booking_id)

        await publish_event(
            self.session,
            PaymentCaptured(
                tenant_id=self.tenant_id,
                payment_id=saved.id,
                booking_id=saved.booking_id,
                amount=str(saved.amount.amount),
                currency=saved.amount.currency,
            ),
        )
        return saved

    async def fail(self, payment_id: UUID, *, code: str | None = None) -> Payment:
        payment = await self.get(payment_id)
        if payment.status is PaymentStatus.FAILED:
            return payment

        payment.mark_failed(code=code)
        saved = await self.repository.save(payment)

        await publish_event(
            self.session,
            PaymentFailed(
                tenant_id=self.tenant_id,
                payment_id=saved.id,
                booking_id=saved.booking_id,
                failure_code=code,
            ),
        )
        return saved

    async def refund(
        self,
        payment_id: UUID,
        *,
        amount: Decimal | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> Payment:
        """Refunds all or part of a captured payment.

        The refund is written as its own row before the gateway call, so a
        refund that succeeds at Moyasar but fails on our side is still visible
        rather than lost.
        """
        now = now or datetime.now(UTC)
        payment = await self.get(payment_id)

        refund_amount = Money(
            amount=amount if amount is not None else payment.refundable_amount,
            currency=payment.amount.currency,
        )

        # Domain first: this raises if the payment was never captured or the
        # amount exceeds what remains.
        payment.record_refund(refund_amount, now=now)

        gateway_refund_id: str | None = None
        if payment.gateway_payment_id:
            result = await self.gateway.refund(
                payment.gateway_payment_id, amount_minor=to_minor_units(refund_amount)
            )
            gateway_refund_id = result.get("id")

        self.repository.add_refund(
            Refund(
                id=uuid4(),
                payment_id=payment.id,
                amount=refund_amount,
                reason=reason,
                gateway_refund_id=gateway_refund_id,
            ),
            tenant_id=self.tenant_id,
        )
        saved = await self.repository.save(payment)

        await publish_event(
            self.session,
            PaymentRefunded(
                tenant_id=self.tenant_id,
                payment_id=saved.id,
                booking_id=saved.booking_id,
                amount=str(refund_amount.amount),
                currency=refund_amount.currency,
            ),
        )
        return saved

    async def apply_gateway_status(
        self, *, gateway_payment_id: str, gateway_status: str, webhook_verified: bool
    ) -> Payment:
        """Moves a payment to match Moyasar's own record of it.

        A webhook is a notification, not the truth: anyone holding the shared
        secret can sign one. So a claimed capture or failure is checked against
        the payment Moyasar's API returns, and that record decides:

          - captured there: captured here, but only for exactly the amount and
            currency this payment asked for (`PaymentAmountMismatchError`);
          - failed there: failed here;
          - anything else: `PaymentNotConfirmedError`, which the gateway retries.

        A claim of nothing final (e.g. "initiated") needs no call and changes
        nothing; the final webhook will follow.
        """
        payment = await self.repository.get_by_gateway_id(gateway_payment_id)
        if payment is None:
            raise UnknownWebhookPaymentError(gateway_payment_id)

        claimed = gateway_status.lower()
        if claimed not in _CAPTURED_GATEWAY_STATUSES | _FAILED_GATEWAY_STATUSES:
            logger.info("payment_webhook_ignored_status", extra={"gateway_status": claimed})
            return payment

        remote = await self.gateway.fetch_payment(gateway_payment_id)
        actual = str(remote.get("status") or "").lower()
        if actual in _CAPTURED_GATEWAY_STATUSES:
            amount_minor, currency = remote.get("amount"), remote.get("currency")
            if not paid_amount_matches(
                payment.amount, amount_minor=amount_minor, currency=currency
            ):
                raise PaymentAmountMismatchError(
                    expected=payment.amount, amount_minor=amount_minor, currency=currency
                )
            return await self.capture(payment.id, webhook_verified=webhook_verified)
        if actual in _FAILED_GATEWAY_STATUSES:
            return await self.fail(payment.id, code=actual)
        raise PaymentNotConfirmedError(gateway_payment_id, claimed=claimed, actual=actual)


class PaymentWebhookProcessor:
    """Handles inbound gateway webhooks. Not tenant-scoped on entry.

    A webhook arrives authenticated only by its signature: no bearer token, no
    tenant in the path. So the flow is deliberately inverted from every other
    entry point in the system:

        verify signature -> record raw payload -> dedupe -> resolve tenant
        -> build a tenant-scoped service -> apply

    The tenant lookup is the one cross-tenant read in the application, and it
    requires `bypass_tenant_scope` because RLS would otherwise (correctly)
    return nothing for a connection with no tenant set.
    """

    def __init__(
        self,
        *,
        events: WebhookEventRepository,
        gateway: PaymentGateway,
        provider: str = "moyasar",
    ) -> None:
        self.events = events
        self.gateway = gateway
        self.provider = provider

    def verify(self, *, raw_body: bytes, signature: str | None, payload: dict[str, Any]) -> None:
        if not self.gateway.verify_webhook(
            payload=raw_body,
            signature=signature,
            secret_token=payload.get("secret_token"),
        ):
            raise WebhookSignatureError()

    async def record(
        self, *, payload: dict[str, Any], signature_verified: bool
    ) -> tuple[Any, bool]:
        """Stores the raw event, less its shared secret. Returns `(event, is_duplicate)`.

        The unique (provider, external_event_id) index is what makes delivery
        idempotent — Moyasar retries, and a retried capture must not be applied
        twice.

        `secret_token` is dropped because it authenticates every webhook: stored
        in a table with no row-level security, anyone who could read the table
        could sign the next "paid" event.
        """
        external_id = str(payload.get("id") or payload.get("event_id") or "")
        existing = await self.events.find(provider=self.provider, external_event_id=external_id)
        if existing is not None:
            return existing, True

        event = await self.events.record(
            provider=self.provider,
            external_event_id=external_id,
            event_type=payload.get("type") or payload.get("event"),
            payload={key: value for key, value in payload.items() if key != "secret_token"},
            signature_verified=signature_verified,
        )
        return event, False

    async def resolve_tenant(self, gateway_payment_id: str) -> UUID:
        tenant_id = await self.events.find_payment_tenant(gateway_payment_id)
        if tenant_id is None:
            raise UnknownWebhookPaymentError(gateway_payment_id)
        return tenant_id


__all__ = ["PaymentIntent", "PaymentService", "PaymentWebhookProcessor"]
