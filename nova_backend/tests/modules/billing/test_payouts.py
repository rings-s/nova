"""What a business is actually paid, from docs/11 section 8.

    payout = collected - 2.5% processing - commission due

The arithmetic here is the number that lands in a salon's bank account, so it
gets tested at both ends: the grouping that turns a day of payments into one
settlement per business, and the domain that turns a settlement into a figure.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.values import Money
from app.modules.billing.domain import (
    CommissionClass,
    PlanTier,
    build_commission_line,
    build_payout,
    build_reversal,
    plan_for,
)
from app.modules.booking.domain import BookingSource
from app.modules.payment.repository import CapturedPayment
from app.worker.arq_worker import _group_takings

PAYOUT_DATE = date(2026, 8, 15)
NOW = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)


def sar(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="SAR")


class TestGroupingADayOfPayments:
    def test_two_payments_for_one_business_become_one_settlement(self):
        business = uuid4()
        b1, b2 = uuid4(), uuid4()
        payments = [
            CapturedPayment(uuid4(), b1, Decimal("100.00"), "SAR"),
            CapturedPayment(uuid4(), b2, Decimal("50.00"), "SAR"),
        ]

        takings = _group_takings(payments, {b1: business, b2: business})

        assert list(takings) == [business]
        assert takings[business].collected == Decimal("150.00")
        assert takings[business].booking_ids == [b1, b2]

    def test_two_businesses_are_paid_separately(self):
        salon, spa = uuid4(), uuid4()
        b1, b2 = uuid4(), uuid4()
        payments = [
            CapturedPayment(uuid4(), b1, Decimal("100.00"), "SAR"),
            CapturedPayment(uuid4(), b2, Decimal("40.00"), "SAR"),
        ]

        takings = _group_takings(payments, {b1: salon, b2: spa})

        assert takings[salon].collected == Decimal("100.00")
        assert takings[spa].collected == Decimal("40.00")

    def test_a_payment_whose_booking_is_unknown_is_dropped_not_guessed(self):
        """Paying it out would mean guessing who to pay."""
        known, orphan = uuid4(), uuid4()
        business = uuid4()
        payments = [
            CapturedPayment(uuid4(), known, Decimal("100.00"), "SAR"),
            CapturedPayment(uuid4(), orphan, Decimal("999.00"), "SAR"),
        ]

        takings = _group_takings(payments, {known: business})

        assert takings[business].collected == Decimal("100.00")
        assert orphan not in takings[business].booking_ids

    def test_a_second_currency_is_dropped_rather_than_added(self):
        business = uuid4()
        b1, b2 = uuid4(), uuid4()
        payments = [
            CapturedPayment(uuid4(), b1, Decimal("100.00"), "SAR"),
            CapturedPayment(uuid4(), b2, Decimal("100.00"), "USD"),
        ]

        takings = _group_takings(payments, {b1: business, b2: business})

        assert takings[business].currency == "SAR"
        assert takings[business].collected == Decimal("100.00")

    def test_an_empty_day_settles_nobody(self):
        assert _group_takings([], {}) == {}


class TestThePayoutArithmetic:
    def test_processing_is_two_and_a_half_percent_of_what_was_collected(self):
        payout = build_payout(
            id=uuid4(),
            tenant_id=uuid4(),
            business_id=uuid4(),
            payout_date=PAYOUT_DATE,
            collected=sar("1000.00"),
            plan=plan_for(PlanTier.SOLO),
            commission_due=sar("0.00"),
            booking_ids=[],
        )
        assert payout.processing_fee.amount == Decimal("25.00")
        assert payout.net_amount == Decimal("975.00")

    def test_commission_is_netted_at_payout_not_invoiced(self):
        """docs/11 section 8: commission comes off the settlement when a
        prepayment exists, rather than waiting for the monthly invoice."""
        payout = build_payout(
            id=uuid4(),
            tenant_id=uuid4(),
            business_id=uuid4(),
            payout_date=PAYOUT_DATE,
            collected=sar("1000.00"),
            plan=plan_for(PlanTier.SOLO),
            commission_due=sar("52.50"),
            booking_ids=[uuid4()],
        )
        assert payout.net_amount == Decimal("922.50")

    def test_every_payout_references_its_bookings(self):
        """ "Every payout references its bookings and is exportable as CSV for
        the business's accountant"."""
        ids = [uuid4(), uuid4()]
        payout = build_payout(
            id=uuid4(),
            tenant_id=uuid4(),
            business_id=uuid4(),
            payout_date=PAYOUT_DATE,
            collected=sar("200.00"),
            plan=plan_for(PlanTier.STUDIO),
            commission_due=sar("0.00"),
            booking_ids=ids,
        )
        assert payout.booking_ids == ids

    def test_the_rate_is_the_same_on_every_plan(self):
        """docs/11 section 2 prices processing at 2.5% across all three tiers."""
        for tier in PlanTier:
            assert plan_for(tier).processing_fee_pct == Decimal("2.50")


class TestWhatCommissionIsNetted:
    """`settle_payout` sums `line.amount` for lines where `is_billable`, so
    that property decides what is deducted from a salon's money."""

    def _line(self, *, source=BookingSource.MARKETPLACE, first=True):
        return build_commission_line(
            id=uuid4(),
            tenant_id=uuid4(),
            business_id=uuid4(),
            booking_id=uuid4(),
            customer_id=uuid4(),
            source=str(source),
            plan=plan_for(PlanTier.SOLO),
            service_price_gross=sar("172.50"),
            is_first_booking_with_business=first,
            completed=True,
            now=NOW,
        )

    def test_a_new_marketplace_booking_is_deducted(self):
        assert self._line().is_billable

    def test_a_direct_booking_is_not_deducted(self):
        assert not self._line(source=BookingSource.DIRECT_LINK).is_billable

    def test_a_repeat_booking_is_not_deducted(self):
        assert not self._line(first=False).is_billable

    def test_a_refunded_booking_is_not_deducted(self):
        """The salon already gave the money back; deducting NOVA's commission
        on top would take money it does not owe."""
        line = self._line()
        assert line.is_billable

        build_reversal(line, id=uuid4(), now=NOW)

        assert line.reversed
        assert not line.is_billable

    def test_the_reversal_row_itself_is_never_deducted(self):
        """Belt and braces: a reversal is EXEMPT *and* flagged `is_reversal`,
        so neither half of `is_billable` can let it through."""
        line = self._line()
        reversal = build_reversal(line, id=uuid4(), now=NOW)
        assert reversal.commission_class is CommissionClass.EXEMPT
        assert reversal.is_reversal
        assert not reversal.is_billable
