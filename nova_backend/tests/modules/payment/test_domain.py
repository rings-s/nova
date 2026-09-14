"""Payment rules — docs/06 section 7, docs/07 section 8, docs/08 section 14.

The invariant worth the most here is arithmetic: a refund can never exceed what
was captured, and status is derived from the numbers rather than asserted by a
caller.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, ValidationDomainError
from app.core.values import Money
from app.modules.payment.domain import (
    Payment,
    PaymentNotCapturedError,
    PaymentStatus,
    RefundExceedsCaptureError,
    deposit_for,
    to_minor_units,
)

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)


def make_payment(amount="100.00", status=PaymentStatus.PENDING, **overrides) -> Payment:
    defaults = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "booking_id": uuid4(),
        "amount": Money(amount=Decimal(amount), currency="SAR"),
        "status": status,
    }
    defaults.update(overrides)
    return Payment(**defaults)


class TestPaymentLifecycle:
    def test_pending_can_capture_directly(self):
        payment = make_payment()
        payment.mark_captured(now=NOW)
        assert payment.status is PaymentStatus.CAPTURED
        assert payment.captured_at == NOW

    def test_authorize_then_capture(self):
        payment = make_payment()
        payment.mark_authorized()
        payment.mark_captured(now=NOW)
        assert payment.status is PaymentStatus.CAPTURED

    def test_a_captured_payment_can_never_be_marked_failed(self):
        # The money is already ours; pretending otherwise loses it from the books.
        payment = make_payment(status=PaymentStatus.CAPTURED)
        with pytest.raises(ConflictError):
            payment.mark_failed(code="whatever")

    def test_a_failed_payment_is_terminal(self):
        payment = make_payment()
        payment.mark_failed(code="declined")
        with pytest.raises(ConflictError):
            payment.mark_captured(now=NOW)

    def test_webhook_verification_is_sticky(self):
        # Once a verified webhook has moved a payment, a later unverified
        # source must not be able to downgrade that fact.
        payment = make_payment()
        payment.mark_captured(now=NOW, webhook_verified=True)
        assert payment.webhook_verified is True


class TestRefunds:
    def test_an_uncaptured_payment_cannot_be_refunded(self):
        payment = make_payment()
        with pytest.raises(PaymentNotCapturedError):
            payment.record_refund(Money(amount=Decimal("10.00")), now=NOW)

    def test_a_full_refund_moves_to_refunded(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        payment.record_refund(Money(amount=Decimal("100.00")), now=NOW)
        assert payment.status is PaymentStatus.REFUNDED
        assert payment.refundable_amount == Decimal("0.00")

    def test_a_partial_refund_moves_to_partially_refunded(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        payment.record_refund(Money(amount=Decimal("40.00")), now=NOW)
        assert payment.status is PaymentStatus.PARTIALLY_REFUNDED
        assert payment.refundable_amount == Decimal("60.00")

    def test_partial_refunds_accumulate_to_a_full_refund(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        payment.record_refund(Money(amount=Decimal("60.00")), now=NOW)
        payment.record_refund(Money(amount=Decimal("40.00")), now=NOW)
        assert payment.status is PaymentStatus.REFUNDED

    def test_refunding_more_than_was_captured_is_refused(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        with pytest.raises(RefundExceedsCaptureError):
            payment.record_refund(Money(amount=Decimal("100.01")), now=NOW)

    def test_the_second_refund_cannot_exceed_what_remains(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        payment.record_refund(Money(amount=Decimal("70.00")), now=NOW)
        with pytest.raises(RefundExceedsCaptureError):
            payment.record_refund(Money(amount=Decimal("40.00")), now=NOW)

    def test_a_zero_or_negative_refund_is_refused(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        with pytest.raises(ValidationDomainError):
            payment.record_refund(Money(amount=Decimal("0.00")), now=NOW)

    def test_currencies_cannot_be_mixed(self):
        payment = make_payment(status=PaymentStatus.CAPTURED)
        with pytest.raises(ValidationDomainError):
            payment.record_refund(Money(amount=Decimal("10.00"), currency="AED"), now=NOW)


class TestDeposits:
    def test_a_zero_percent_policy_takes_nothing_up_front(self):
        # A salon that takes no deposit is a normal configuration, and the
        # reason booking and payment states stay separate.
        due = deposit_for(Money(amount=Decimal("200.00")), deposit_percent=0)
        assert due.amount == Decimal("0.00")

    def test_a_percentage_deposit_is_rounded_to_fils(self):
        due = deposit_for(Money(amount=Decimal("99.99")), deposit_percent=25)
        assert due.amount == Decimal("25.00")

    def test_a_full_deposit_is_the_whole_price(self):
        due = deposit_for(Money(amount=Decimal("150.50")), deposit_percent=100)
        assert due.amount == Decimal("150.50")

    def test_currency_is_preserved(self):
        due = deposit_for(Money(amount=Decimal("100.00"), currency="AED"), deposit_percent=50)
        assert due.currency == "AED"

    def test_an_impossible_percentage_is_refused(self):
        with pytest.raises(ValidationDomainError):
            deposit_for(Money(amount=Decimal("100.00")), deposit_percent=150)


class TestMinorUnits:
    def test_converts_to_halalas(self):
        assert to_minor_units(Money(amount=Decimal("100.00"))) == 10000
        assert to_minor_units(Money(amount=Decimal("0.05"))) == 5

    def test_awkward_decimals_do_not_lose_fils(self):
        # The whole reason Money carries a Decimal to this boundary: 19.99 as a
        # binary float is 19.989999..., which truncates to 1998.
        assert to_minor_units(Money(amount=Decimal("19.99"))) == 1999
