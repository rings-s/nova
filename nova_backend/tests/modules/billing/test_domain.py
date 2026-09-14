"""Pure domain tests for billing — no database, no HTTP, no fixtures.

The whole commercial model is arithmetic over immutable inputs, so all of it is
testable here. Anything in this file that needs a database is in the wrong file.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, ValidationDomainError
from app.core.values import Money
from app.modules.billing.domain import (
    PLANS,
    VAT_RATE,
    BillingPeriod,
    DowngradeBelowUsageError,
    Invoice,
    InvoiceAlreadyIssuedError,
    InvoiceStatus,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    build_payout,
    commission_base,
    percentage_of,
    plan_for,
    to_fils,
)

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def sar(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="SAR")


def make_subscription(
    *, tier: PlanTier = PlanTier.SOLO, seats: int = 1, locations: int = 1
) -> Subscription:
    period = BillingPeriod.month_containing(NOW.date())
    return Subscription(
        id=uuid4(),
        tenant_id=uuid4(),
        business_id=uuid4(),
        tier=tier,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=period.period_start,
        current_period_end=period.period_end,
        seats=seats,
        locations=locations,
    )


def make_invoice() -> Invoice:
    return Invoice(
        id=uuid4(),
        tenant_id=uuid4(),
        business_id=uuid4(),
        period=BillingPeriod.month_containing(date(2026, 7, 15)),
    )


class TestThePriceList:
    """docs/11 section 2, read straight off the table."""

    def test_solo_starts_at_zero(self):
        plan = plan_for(PlanTier.SOLO)
        assert plan.monthly_price == Decimal("0.00")
        assert plan.new_client_commission_pct == Decimal("35.00")

    def test_studio_is_199_a_month_and_30_percent(self):
        plan = plan_for(PlanTier.STUDIO)
        assert plan.monthly_price == Decimal("199.00")
        assert plan.new_client_commission_pct == Decimal("30.00")

    def test_studio_annual_is_two_months_free(self):
        plan = plan_for(PlanTier.STUDIO)
        assert plan.annual_price == plan.monthly_price * 10

    def test_chain_is_449_per_location_and_25_percent(self):
        plan = plan_for(PlanTier.CHAIN)
        assert plan.monthly_price == Decimal("449.00")
        assert plan.new_client_commission_pct == Decimal("25.00")
        assert plan.priced_per_location is True

    @pytest.mark.parametrize("tier", list(PlanTier))
    def test_repeat_and_direct_are_free_on_every_plan(self, tier):
        """The promise the whole model rests on: 0% forever, on every tier."""
        assert PLANS[tier].repeat_commission_pct == Decimal("0")

    @pytest.mark.parametrize("tier", list(PlanTier))
    def test_processing_is_two_and_a_half_percent_everywhere(self, tier):
        assert PLANS[tier].processing_fee_pct == Decimal("2.5")

    def test_a_chain_pays_per_branch(self):
        plan = plan_for(PlanTier.CHAIN)
        assert plan.subscription_amount(locations=3).amount == Decimal("1347.00")

    def test_a_studio_pays_the_same_whatever_its_footprint(self):
        plan = plan_for(PlanTier.STUDIO)
        assert plan.subscription_amount(locations=1).amount == Decimal("199.00")


class TestCommissionBase:
    """docs/11 section 3 rule 7: net of VAT, net of discounts."""

    def test_vat_is_removed_from_the_displayed_price(self):
        # 172.50 gross at 15% VAT is 150.00 net. Charging commission on the
        # gross would be charging the salon for tax it merely collected.
        assert commission_base(sar("172.50")).amount == Decimal("150.00")

    def test_discounts_come_off_before_the_rate_applies(self):
        assert commission_base(sar("172.50"), discount=sar("57.50")).amount == Decimal("100.00")

    def test_a_discount_larger_than_the_price_is_refused(self):
        with pytest.raises(ValidationDomainError):
            commission_base(sar("100.00"), discount=sar("150.00"))

    def test_the_base_rounds_to_fils(self):
        base = commission_base(sar("99.99"))
        assert base.amount == base.amount.quantize(Decimal("0.01"))


class TestPercentages:
    def test_thirty_five_percent_of_a_hundred(self):
        assert percentage_of(sar("100.00"), Decimal("35")).amount == Decimal("35.00")

    def test_rounds_half_up_to_fils(self):
        # 33.333... rounds to 33.33; a salon checking by hand gets the same.
        assert percentage_of(sar("95.24"), Decimal("35")).amount == Decimal("33.33")

    def test_a_negative_rate_is_refused(self):
        with pytest.raises(ValidationDomainError):
            percentage_of(sar("100.00"), Decimal("-5"))


class TestSubscriptionPlanChanges:
    def test_upgrading_is_always_allowed(self):
        subscription = make_subscription(tier=PlanTier.SOLO)
        subscription.change_plan(PlanTier.STUDIO)
        assert subscription.tier is PlanTier.STUDIO

    def test_downgrading_below_seats_in_use_is_refused(self):
        """docs/11 section 5. The salon decides what to remove, not us."""
        subscription = make_subscription(tier=PlanTier.STUDIO, seats=6)
        with pytest.raises(DowngradeBelowUsageError):
            subscription.change_plan(PlanTier.SOLO)
        assert subscription.tier is PlanTier.STUDIO

    def test_downgrading_below_locations_in_use_is_refused(self):
        subscription = make_subscription(tier=PlanTier.CHAIN, locations=4)
        with pytest.raises(DowngradeBelowUsageError):
            subscription.change_plan(PlanTier.STUDIO)

    def test_the_refusal_names_what_is_in_the_way(self):
        subscription = make_subscription(tier=PlanTier.STUDIO, seats=6)
        with pytest.raises(DowngradeBelowUsageError) as excinfo:
            subscription.change_plan(PlanTier.SOLO)
        assert "staff seats" in str(excinfo.value)

    def test_solo_refuses_a_second_location(self):
        subscription = make_subscription(tier=PlanTier.SOLO)
        with pytest.raises(DowngradeBelowUsageError):
            subscription.add_location()

    def test_a_plan_without_an_annual_price_refuses_annual(self):
        subscription = make_subscription(tier=PlanTier.SOLO)
        with pytest.raises(ValidationDomainError):
            subscription.change_plan(PlanTier.CHAIN, annual=True)

    def test_a_negotiated_chain_price_overrides_the_list(self):
        subscription = make_subscription(tier=PlanTier.CHAIN, locations=5)
        subscription.negotiated_monthly_price = Decimal("1800.00")
        assert subscription.subscription_amount().amount == Decimal("1800.00")


class TestSubscriptionLifecycle:
    def test_a_cancelled_subscription_keeps_access_to_period_end(self):
        """docs/11 section 5."""
        subscription = make_subscription()
        subscription.cancel(at_period_end=False, now=NOW)
        assert subscription.has_access_on(subscription.current_period_end - timedelta(days=1))
        assert not subscription.has_access_on(subscription.current_period_end)

    def test_cancelling_at_period_end_leaves_it_active(self):
        subscription = make_subscription()
        subscription.cancel(at_period_end=True, now=NOW)
        assert subscription.cancel_at_period_end is True
        assert subscription.status is SubscriptionStatus.ACTIVE

    def test_hiding_the_listing_is_all_non_payment_does(self):
        """docs/11 section 7: "Never break the salon's day."

        There is deliberately nothing on this aggregate that could close a
        queue, cancel a booking, or lock a calendar. The only lever
        non-payment has is the marketing NOVA itself provides.
        """
        subscription = make_subscription()
        subscription.mark_past_due()
        subscription.hide_marketplace_listing()

        assert subscription.marketplace_listing_hidden is True
        assert subscription.status is SubscriptionStatus.PAST_DUE
        assert not hasattr(subscription, "suspend_operations")

    def test_paying_restores_the_listing(self):
        subscription = make_subscription()
        subscription.hide_marketplace_listing()
        subscription.activate()
        assert subscription.marketplace_listing_hidden is False


class TestInvoiceArithmetic:
    def test_vat_is_fifteen_percent_of_the_net(self):
        invoice = make_invoice()
        invoice.set_charges(
            subscription=sar("199.00"), commission=Decimal("100.00"), processing=sar("25.00")
        )
        assert invoice.net_amount == Decimal("324.00")
        assert invoice.vat_amount == to_fils(Decimal("324.00") * VAT_RATE)
        assert invoice.total_amount == Decimal("372.60")

    def test_totals_reconcile_to_the_fils(self):
        """docs/11 section 11, last requirement."""
        invoice = make_invoice()
        invoice.set_charges(
            subscription=sar("199.00"), commission=Decimal("33.33"), processing=sar("7.77")
        )
        assert invoice.reconciles()
        assert invoice.total_amount == invoice.net_amount + invoice.vat_amount

    def test_a_month_of_only_reversals_owes_negative_commission(self):
        """Refunding last month's bookings legitimately credits this one."""
        invoice = make_invoice()
        invoice.set_charges(
            subscription=sar("0.00"), commission=Decimal("-52.50"), processing=sar("0.00")
        )
        assert invoice.commission_amount == Decimal("-52.50")
        assert invoice.reconciles()

    def test_mixing_currencies_is_refused(self):
        invoice = make_invoice()
        with pytest.raises(ValidationDomainError):
            invoice.set_charges(
                subscription=sar("199.00"),
                commission=Decimal("0"),
                processing=Money(amount=Decimal("10.00"), currency="AED"),
            )


class TestInvoiceImmutability:
    """docs/11 section 5: "An issued invoice is never edited"."""

    def test_charges_cannot_be_rewritten_after_issue(self):
        invoice = make_invoice()
        invoice.set_charges(
            subscription=sar("199.00"), commission=Decimal("0"), processing=sar("0")
        )
        invoice.issue(now=NOW, due_at=NOW + timedelta(days=7))

        with pytest.raises(InvoiceAlreadyIssuedError):
            invoice.set_charges(
                subscription=sar("0.00"), commission=Decimal("0"), processing=sar("0")
            )

    def test_it_cannot_be_issued_twice(self):
        invoice = make_invoice()
        invoice.issue(now=NOW, due_at=NOW + timedelta(days=7))
        with pytest.raises(InvoiceAlreadyIssuedError):
            invoice.issue(now=NOW, due_at=NOW + timedelta(days=7))

    def test_a_paid_invoice_cannot_be_voided(self):
        invoice = make_invoice()
        invoice.issue(now=NOW, due_at=NOW + timedelta(days=7))
        invoice.mark_paid(now=NOW)
        with pytest.raises(ConflictError):
            invoice.void()

    def test_marking_paid_twice_is_a_no_op(self):
        invoice = make_invoice()
        invoice.issue(now=NOW, due_at=NOW + timedelta(days=7))
        invoice.mark_paid(now=NOW)
        first_paid_at = invoice.paid_at
        invoice.mark_paid(now=NOW + timedelta(days=1))
        assert invoice.paid_at == first_paid_at

    def test_only_an_issued_invoice_goes_overdue(self):
        invoice = make_invoice()
        invoice.mark_overdue()
        assert invoice.status is InvoiceStatus.DRAFT


class TestBillingPeriod:
    def test_a_month_is_half_open(self):
        period = BillingPeriod.month_containing(date(2026, 8, 16))
        assert period.period_start == date(2026, 8, 1)
        assert period.period_end == date(2026, 9, 1)

    def test_december_rolls_into_january(self):
        period = BillingPeriod.month_containing(date(2026, 12, 5))
        assert period.period_end == date(2027, 1, 1)

    def test_the_first_of_the_month_closes_the_month_before(self):
        """docs/11 section 7 step 3."""
        period = BillingPeriod.previous_month(date(2026, 9, 1))
        assert period.period_start == date(2026, 8, 1)
        assert period.period_end == date(2026, 9, 1)

    def test_january_first_closes_december(self):
        period = BillingPeriod.previous_month(date(2027, 1, 1))
        assert period.period_start == date(2026, 12, 1)


class TestPayouts:
    """docs/11 section 8: collected - 2.5% processing - commission due."""

    def test_the_arithmetic(self):
        payout = build_payout(
            id=uuid4(),
            tenant_id=uuid4(),
            business_id=uuid4(),
            payout_date=date(2026, 8, 16),
            collected=sar("1000.00"),
            plan=plan_for(PlanTier.STUDIO),
            commission_due=sar("52.50"),
            booking_ids=[uuid4()],
        )
        assert payout.processing_fee.amount == Decimal("25.00")
        assert payout.net_amount == Decimal("922.50")

    def test_a_payout_references_its_bookings(self):
        """ "Every payout references its bookings and is exportable as CSV"."""
        bookings = [uuid4(), uuid4()]
        payout = build_payout(
            id=uuid4(),
            tenant_id=uuid4(),
            business_id=uuid4(),
            payout_date=date(2026, 8, 16),
            collected=sar("500.00"),
            plan=plan_for(PlanTier.SOLO),
            commission_due=sar("0.00"),
            booking_ids=bookings,
        )
        assert payout.booking_ids == bookings


class TestNoFloatsAnywhere:
    def test_every_published_price_is_a_decimal(self):
        for plan in PLANS.values():
            assert isinstance(plan.monthly_price, Decimal)
            assert isinstance(plan.new_client_commission_pct, Decimal)
            assert plan.annual_price is None or isinstance(plan.annual_price, Decimal)

    def test_vat_is_a_decimal(self):
        assert isinstance(VAT_RATE, Decimal)
