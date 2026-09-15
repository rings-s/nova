"""payment · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi, sqlalchemy, or an HTTP client.

A rich entity, because payment state is a machine with real money attached and
an illegal transition is not a validation slip — it is a customer charged twice
or refunded twice.

State machine (docs/06 section 7):

    PENDING ──▶ AUTHORIZED ──▶ CAPTURED ──▶ REFUNDED
       │             │             │
       │             │             └──▶ PARTIALLY_REFUNDED ──▶ REFUNDED
       └─────────────┴──▶ FAILED

The rule that governs this whole context (docs/03 section 5, docs/06 section 7):
payment state is SEPARATE from booking state. A booking may be CONFIRMED while
its payment is still PENDING if the tenant's deposit policy allows it. Collapsing
the two makes "confirmed but unpaid" — an ordinary situation in a salon —
unrepresentable.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from app.core.exceptions import ConflictError, ValidationDomainError
from app.core.values import Money


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


#: Statuses in which money has actually moved to us. Only these can be refunded.
SETTLED_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.CAPTURED, PaymentStatus.PARTIALLY_REFUNDED}
)

#: Statuses from which nothing further can happen.
TERMINAL_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.FAILED, PaymentStatus.REFUNDED}
)

_ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED, PaymentStatus.FAILED}
    ),
    PaymentStatus.AUTHORIZED: frozenset({PaymentStatus.CAPTURED, PaymentStatus.FAILED}),
    PaymentStatus.CAPTURED: frozenset({PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED}),
    PaymentStatus.PARTIALLY_REFUNDED: frozenset(
        {PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED}
    ),
    # A captured payment can never be marked failed — the money is already
    # ours, and pretending otherwise loses it from the books.
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


class InvalidPaymentTransition(ConflictError):
    code = "invalid_payment_transition"

    def __init__(self, current: PaymentStatus, attempted: PaymentStatus) -> None:
        allowed = sorted(_ALLOWED_TRANSITIONS[current]) or "none (terminal)"
        super().__init__(
            f"Cannot move a payment from '{current}' to '{attempted}'. "
            f"Allowed from '{current}': {allowed}."
        )


class PaymentNotCapturedError(ConflictError):
    """docs/06 section 9 names this exception explicitly."""

    code = "payment_not_captured"

    def __init__(self) -> None:
        super().__init__("This payment has not been captured, so it cannot be refunded.")


class RefundExceedsCaptureError(ValidationDomainError):
    code = "refund_exceeds_capture"

    def __init__(self, requested: Decimal, remaining: Decimal) -> None:
        super().__init__(
            f"Cannot refund {requested}: only {remaining} of this payment remains refundable."
        )


class WebhookSignatureError(ValidationDomainError):
    """An unverified webhook must never be allowed to move money.

    docs/07 section 8: "Webhook payload must be treated as untrusted until
    signature verification." Anyone can POST to a webhook URL; the signature is
    the only thing separating the real gateway from someone who guessed it.
    """

    code = "invalid_webhook_signature"

    def __init__(self) -> None:
        super().__init__("Webhook signature verification failed.")


@dataclass
class Refund:
    """A refund is its own record, never a mutation of the original payment.

    docs/07 section 8: "Refunds must be stored as separate payment events or
    records." Overwriting the original amount would destroy the evidence of
    what the customer was actually charged.
    """

    id: UUID
    payment_id: UUID
    amount: Money
    reason: str | None = None
    gateway_refund_id: str | None = None
    created_at: datetime | None = None


@dataclass
class Payment:
    """Money owed or taken for a booking."""

    id: UUID
    tenant_id: UUID
    booking_id: UUID | None
    amount: Money
    status: PaymentStatus
    gateway: str = "moyasar"
    gateway_payment_id: str | None = None
    #: Whether the state was reached via a *verified* webhook rather than an
    #: optimistic client callback. Auditors care about the difference.
    webhook_verified: bool = False
    failure_code: str | None = None
    refunded_amount: Decimal = Decimal("0.00")
    captured_at: datetime | None = None
    refunded_at: datetime | None = None
    #: When the payment was opened. The repository replaces this with the row's
    #: own timestamp, so a persisted payment reports what Postgres recorded.
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    pending_events: list[object] = field(default_factory=list, repr=False)

    def _transition_to(self, target: PaymentStatus) -> None:
        if target not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidPaymentTransition(self.status, target)
        self.status = target

    def mark_authorized(self) -> None:
        self._transition_to(PaymentStatus.AUTHORIZED)

    def mark_captured(self, *, now: datetime, webhook_verified: bool = False) -> None:
        """Records that the money arrived.

        Callers must treat this as idempotent at the service layer: Moyasar
        retries webhooks, and a second capture on an already-captured payment
        is a duplicate delivery, not an error (docs/08 section 14).
        """
        self._transition_to(PaymentStatus.CAPTURED)
        self.captured_at = now
        self.webhook_verified = self.webhook_verified or webhook_verified

    def mark_failed(self, *, code: str | None = None) -> None:
        self._transition_to(PaymentStatus.FAILED)
        self.failure_code = code

    @property
    def refundable_amount(self) -> Decimal:
        return self.amount.amount - self.refunded_amount

    @property
    def is_captured(self) -> bool:
        return self.status in SETTLED_STATUSES

    def record_refund(self, amount: Money, *, now: datetime) -> None:
        """Applies a refund, moving to PARTIALLY_REFUNDED or REFUNDED.

        The status is derived from the arithmetic rather than passed in, so a
        caller cannot mark a payment fully refunded while only returning half
        the money.
        """
        if not self.is_captured:
            raise PaymentNotCapturedError()
        if amount.currency != self.amount.currency:
            raise ValidationDomainError(
                f"Cannot refund {amount.currency} against a {self.amount.currency} payment."
            )
        if amount.amount <= 0:
            raise ValidationDomainError("A refund must be for a positive amount.")
        if amount.amount > self.refundable_amount:
            raise RefundExceedsCaptureError(amount.amount, self.refundable_amount)

        self.refunded_amount += amount.amount
        self.refunded_at = now
        self._transition_to(
            PaymentStatus.REFUNDED
            if self.refunded_amount >= self.amount.amount
            else PaymentStatus.PARTIALLY_REFUNDED
        )


def deposit_for(price: Money, *, deposit_percent: int) -> Money:
    """How much must be paid up front to hold a booking.

    0% means the salon takes no deposit and the booking confirms without
    payment — a normal configuration, and the reason booking and payment states
    stay separate.
    """
    if not 0 <= deposit_percent <= 100:
        raise ValidationDomainError("Deposit percentage must be between 0 and 100.")

    raw = price.amount * Decimal(deposit_percent) / Decimal(100)
    # Round to fils. Rounding up would silently overcharge; quantize to 2dp is
    # what the NUMERIC(10,2) column stores anyway.
    return Money(amount=raw.quantize(Decimal("0.01")), currency=price.currency)


def to_minor_units(amount: Money) -> int:
    """Moyasar, like most gateways, takes integer minor units (halalas).

    Passing a float here is how rounding errors become real money, which is why
    `Money` carries a Decimal all the way to this boundary.
    """
    return int((amount.amount * 100).quantize(Decimal("1")))


class PaymentAmountMismatchError(ConflictError):
    """The gateway reports a different sum than this payment asked for.

    Not captured, and so the booking is not confirmed: a capture is what confirms
    a booking, so it must be for exactly the amount the booking required.
    """

    code = "payment_amount_mismatch"

    def __init__(self, *, expected: Money, amount_minor: object, currency: object) -> None:
        super().__init__(
            f"Expected {to_minor_units(expected)} {expected.currency} in minor units; the "
            f"gateway reported {amount_minor!r} {currency!r}. The payment was not captured."
        )


def paid_amount_matches(expected: Money, *, amount_minor: object, currency: object) -> bool:
    """Whether a gateway's report of what was paid is exactly what we asked for.

    The report is integer minor units and a currency code, from a verified
    webhook. Anything missing or malformed does not match: capture fails closed.
    """
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        return False
    if not isinstance(currency, str):
        return False
    return (
        amount_minor == to_minor_units(expected) and currency.upper() == expected.currency.upper()
    )


class ReturnUrlNotAllowedError(ValidationDomainError):
    code = "return_url_not_allowed"

    def __init__(self) -> None:
        super().__init__("return_url must be an absolute http(s) URL on the app's own origin.")


def assert_return_url_allowed(return_url: str, *, app_url: str) -> None:
    """Refuses a return URL anywhere but the customer app's own origin.

    The gateway sends the customer's browser here once they have paid. An
    arbitrary value would make NOVA's checkout a redirect to any site, with a
    genuine payment page in front of it to lend it trust (CWE-601).
    """
    allowed = _origin(app_url)
    if allowed is None or _origin(return_url) != allowed:
        raise ReturnUrlNotAllowedError()


def _origin(url: str) -> tuple[str, str, int] | None:
    """`(scheme, host, port)`, or None for anything but a plain http(s) URL.

    Backslashes, whitespace and credentials are refused outright: browsers and
    `urlsplit` disagree about where such a URL's host ends, and that
    disagreement is the classic way past an origin check.
    """
    if "\\" in url or any(ord(char) <= 0x20 for char in url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
        return None
    return parts.scheme, parts.hostname.lower(), port or (443 if parts.scheme == "https" else 80)


@dataclass(frozen=True)
class PaymentFact:
    """A payment as the analytics context sees it (docs/13 section 6.2).

    Amounts and dates only: no gateway id, no failure code, nothing a report
    has no use for.
    """

    booking_id: UUID
    status: PaymentStatus
    amount_minor: int
    refunded_minor: int
    currency: str
    captured_at: datetime | None
    refunded_at: datetime | None
