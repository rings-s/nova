"""payment · APPLICATION layer — use cases.

Layer rule: domain, repository, events, integrations, and other modules'
*services*. Must not import fastapi or another module's models/repository.

Services flush, never commit. The router owns the transaction boundary.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.core.events import publish_event
from app.core.security import Principal
from app.core.values import Money, TimeRange
from app.integrations.base import IntegrationNotConfiguredError
from app.integrations.payments.moyasar import (
    MIN_INVOICE_AMOUNT_MINOR,
    PaymentGateway,
    PaymentGatewayError,
)
from app.modules.booking.domain import BookingStatus
from app.modules.booking.service import BookingService
from app.modules.payment.domain import (
    SETTLED_STATUSES,
    CapturedPayment,
    CheckoutAmountTooSmallError,
    Payment,
    PaymentAmountMismatchError,
    PaymentCheckoutMismatchError,
    PaymentFact,
    PaymentStatus,
    Refund,
    WebhookSignatureError,
    assert_return_url_allowed,
    deposit_for,
    paid_amount_matches,
    to_minor_units,
    with_query,
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
from app.modules.payment.repository import (
    PaymentRepository,
    SettlementRepository,
    WebhookEventRepository,
)

logger = logging.getLogger(__name__)

#: Moyasar payment statuses that mean the money actually arrived.
_CAPTURED_GATEWAY_STATUSES = frozenset({"paid", "captured"})
#: Moyasar payment statuses that end an attempt without money.
_FAILED_GATEWAY_STATUSES = frozenset({"failed", "voided"})
#: Moyasar invoice statuses after which the checkout can no longer be paid.
#: Anything else (`initiated`, `on_hold`) is still open.
_CLOSED_INVOICE_STATUSES = frozenset({"expired", "canceled", "voided", "failed"})
#: Our statuses a payment never leaves by reconciling with the gateway.
_FINAL_STATUSES = frozenset({PaymentStatus.FAILED, PaymentStatus.REFUNDED} | SETTLED_STATUSES)


@dataclass(frozen=True)
class PaymentFormConfig:
    """What the browser hands Moyasar's Payment Form (`Moyasar.init`).

    Bound to the invoice this server opened: Moyasar refuses a form payment
    whose amount differs from the invoice's, so the browser cannot choose what
    it pays, and the payment lands on that invoice, where `reconcile` and the
    webhook already look for it. Nothing here is secret; the publishable key
    can pay an invoice but neither create one nor read a payment back.
    """

    publishable_api_key: str
    invoice_id: str
    #: Integer minor units (halalas), as Moyasar takes them.
    amount: int
    currency: str
    description: str
    #: Where Moyasar sends the payer after paying or 3-D Secure, with its own
    #: `id`, `status` and `message` added to the query.
    callback_url: str


@dataclass(frozen=True)
class PaymentIntent:
    """A payment plus how the customer completes it: the embedded form when a
    publishable key is configured, else Moyasar's hosted page."""

    payment: Payment
    redirect_url: str | None
    checkout: PaymentFormConfig | None = None


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
        checkout_ttl_minutes: int = 30,
        publishable_key: str | None = None,
    ) -> None:
        self.repository = repository
        self.gateway = gateway
        self.bookings = bookings
        self.tenant_id = tenant_id
        #: The customer app. A payment's `return_url` must be on its origin.
        self.public_app_url = public_app_url
        self.default_deposit_percent = default_deposit_percent
        self.checkout_ttl_minutes = checkout_ttl_minutes
        #: Moyasar's publishable key, for the embedded Payment Form. None means
        #: payers use the invoice's hosted page instead.
        self.publishable_key = publishable_key

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

        amount_minor = to_minor_units(due)
        if amount_minor < MIN_INVOICE_AMOUNT_MINOR:
            raise CheckoutAmountTooSmallError(due)

        payment = await self.repository.add_payment(
            Payment(
                id=uuid4(),
                tenant_id=self.tenant_id,
                booking_id=booking_id,
                amount=due,
                status=PaymentStatus.PENDING,
            )
        )

        # Moyasar sends the payer back to exactly this URL, so it carries the
        # payment's id: the page they land on asks `reconcile` what happened.
        landing = with_query(return_url, payment=str(payment.id))
        # Shown to the payer on Moyasar's checkout page or form.
        description = f"NOVA booking {booking_id.hex[:8].upper()}"
        try:
            invoice = await self.gateway.create_invoice(
                amount_minor=amount_minor,
                currency=due.currency,
                description=description,
                success_url=landing,
                back_url=landing,
                expired_at=datetime.now(UTC) + timedelta(minutes=self.checkout_ttl_minutes),
                metadata={
                    **(metadata or {}),
                    # Echoed back on every payment and webhook, which ties a
                    # payment to its booking even if our own lookup fails.
                    "booking_id": str(booking_id),
                    "tenant_id": str(self.tenant_id),
                    "payment_id": str(payment.id),
                },
            )
        except (IntegrationNotConfiguredError, PaymentGatewayError):
            # No gateway here (503), or Moyasar said no (502): the adapter has
            # logged the detail, and the PENDING row stays as the record.
            raise
        except Exception:
            logger.exception("moyasar_create_invoice_failed", extra={"payment_id": str(payment.id)})
            raise

        redirect_url = invoice.get("url")
        checkout: PaymentFormConfig | None = None
        if invoice.get("id"):
            invoice_id = str(invoice["id"])
            payment.gateway_invoice_id = invoice_id
            payment = await self.repository.save(payment)
            if self.publishable_key:
                checkout = PaymentFormConfig(
                    publishable_api_key=self.publishable_key,
                    invoice_id=invoice_id,
                    amount=amount_minor,
                    currency=due.currency,
                    description=description,
                    callback_url=landing,
                )

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
        return PaymentIntent(payment=payment, redirect_url=redirect_url, checkout=checkout)

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

        if payment.gateway_invoice_id and not payment.gateway_payment_id:
            # Paid through a checkout whose payment id never reached us: there
            # is nothing to refund against, and recording a refund that no
            # money followed would be worse than refusing.
            raise PaymentGatewayError(
                "This payment's gateway record is incomplete; refund it from the Moyasar dashboard."
            )

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
        self,
        *,
        gateway_payment_id: str,
        gateway_status: str,
        webhook_verified: bool,
        gateway_invoice_id: str | None = None,
    ) -> Payment:
        """Moves a payment to match Moyasar's own record of it.

        A webhook is a notification, not the truth: anyone holding the shared
        secret can send one. So a claimed capture or failure is checked against
        the payment Moyasar's API returns, and that record decides:

          - paid there: captured here, but only for exactly the amount and
            currency this payment asked for, and only if it paid this
            payment's own checkout (`PaymentVerificationError`);
          - failed there: failed here, unless the checkout it was an attempt
            on is still open (the payer can try another card);
          - anything else: `PaymentNotConfirmedError`, which the gateway retries.

        A claim of nothing final (e.g. "initiated") needs no call and changes
        nothing; the final webhook will follow.
        """
        payment = await self.repository.find_for_gateway(
            gateway_payment_id=gateway_payment_id, gateway_invoice_id=gateway_invoice_id
        )
        if payment is None:
            raise UnknownWebhookPaymentError(gateway_payment_id)

        claimed = gateway_status.lower()
        if claimed not in _CAPTURED_GATEWAY_STATUSES | _FAILED_GATEWAY_STATUSES:
            logger.info("payment_webhook_ignored_status", extra={"gateway_status": claimed})
            return payment

        remote = await self.gateway.fetch_payment(gateway_payment_id)
        actual = str(remote.get("status") or "").lower()
        if actual not in _CAPTURED_GATEWAY_STATUSES | _FAILED_GATEWAY_STATUSES:
            raise PaymentNotConfirmedError(gateway_payment_id, claimed=claimed, actual=actual)
        return await self._apply_remote_payment(payment, remote, webhook_verified=webhook_verified)

    async def reconcile(self, payment_id: UUID) -> Payment:
        """Brings a payment up to date with Moyasar, on the payer's return.

        Moyasar's guidance is to fetch the payment and check its status, amount
        and currency before fulfilling, whatever the redirect claimed. This is
        that check, and it makes a payment confirm even where webhooks cannot
        reach NOVA (a laptop, a firewall). Safe to call any number of times: a
        payment already settled or failed is returned as it is.
        """
        payment = await self.get(payment_id)
        if payment.status in _FINAL_STATUSES:
            return payment

        if payment.gateway_payment_id:
            remote = await self.gateway.fetch_payment(payment.gateway_payment_id)
            return await self._apply_remote_payment(payment, remote, webhook_verified=False)

        if payment.gateway_invoice_id:
            invoice = await self.gateway.fetch_invoice(payment.gateway_invoice_id)
            paid = next(
                (
                    attempt
                    for attempt in invoice.get("payments") or []
                    if str(attempt.get("status") or "").lower() in _CAPTURED_GATEWAY_STATUSES
                ),
                None,
            )
            if paid is not None and paid.get("id"):
                # Read the payment itself rather than trusting the summary on
                # the invoice: it is the record the capture is checked against.
                remote = await self.gateway.fetch_payment(str(paid["id"]))
                return await self._apply_remote_payment(payment, remote, webhook_verified=False)
            status = str(invoice.get("status") or "").lower()
            if status in _CLOSED_INVOICE_STATUSES:
                return await self.fail(payment.id, code=f"checkout_{status}")
        return payment

    async def _apply_remote_payment(
        self, payment: Payment, remote: dict[str, Any], *, webhook_verified: bool
    ) -> Payment:
        """Applies Moyasar's record of one payment to ours. The single place a
        gateway report becomes a capture or a failure."""
        actual = str(remote.get("status") or "").lower()
        remote_id = str(remote.get("id") or "")

        if actual in _CAPTURED_GATEWAY_STATUSES:
            if (
                payment.gateway_invoice_id
                and remote_id != payment.gateway_payment_id
                and str(remote.get("invoice_id") or "") != payment.gateway_invoice_id
            ):
                raise PaymentCheckoutMismatchError(
                    expected_invoice_id=payment.gateway_invoice_id,
                    invoice_id=remote.get("invoice_id"),
                )
            amount_minor, currency = remote.get("amount"), remote.get("currency")
            if not paid_amount_matches(
                payment.amount, amount_minor=amount_minor, currency=currency
            ):
                raise PaymentAmountMismatchError(
                    expected=payment.amount, amount_minor=amount_minor, currency=currency
                )
            if remote_id and payment.gateway_payment_id != remote_id:
                # Learnt only now, and needed for any refund.
                payment.gateway_payment_id = remote_id
                await self.repository.save(payment)
            return await self.capture(payment.id, webhook_verified=webhook_verified)

        if actual in _FAILED_GATEWAY_STATUSES:
            if payment.gateway_invoice_id:
                # One declined card is not a failed checkout: the payer is still
                # on Moyasar's page and may pay with another. Only a checkout
                # that can no longer be paid fails the payment.
                invoice = await self.gateway.fetch_invoice(payment.gateway_invoice_id)
                status = str(invoice.get("status") or "").lower()
                if status not in _CLOSED_INVOICE_STATUSES:
                    return payment
                return await self.fail(payment.id, code=f"checkout_{status}")
            return await self.fail(payment.id, code=actual)

        return payment


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

    def verify(self, *, payload: dict[str, Any]) -> None:
        """Moyasar authenticates a webhook by the `secret_token` in its body."""
        secret_token = payload.get("secret_token")
        if not isinstance(secret_token, str) or not self.gateway.verify_webhook(
            secret_token=secret_token
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
        external_id = str(payload.get("id") or "")
        existing = await self.events.find(provider=self.provider, external_event_id=external_id)
        if existing is not None:
            return existing, True

        event = await self.events.record(
            provider=self.provider,
            external_event_id=external_id,
            event_type=payload.get("type"),
            payload={key: value for key, value in payload.items() if key != "secret_token"},
            signature_verified=signature_verified,
        )
        return event, False

    async def resolve_tenant(
        self, gateway_payment_id: str, gateway_invoice_id: str | None = None
    ) -> UUID:
        tenant_id = await self.events.find_payment_tenant(gateway_payment_id, gateway_invoice_id)
        if tenant_id is None:
            raise UnknownWebhookPaymentError(gateway_payment_id)
        return tenant_id


__all__ = ["PaymentIntent", "PaymentService", "PaymentWebhookProcessor"]


class SettlementReader:
    """What the daily payout asks across every tenant: what was captured when.

    The payout itself is settled per tenant, through `BillingService`.
    """

    def __init__(self, settlements: SettlementRepository) -> None:
        self.settlements = settlements

    async def list_captured_between(
        self, *, start: datetime, end: datetime
    ) -> list[CapturedPayment]:
        """Prepayments captured in `[start, end)`, net of refunds."""
        return await self.settlements.list_captured_between(start=start, end=end)
