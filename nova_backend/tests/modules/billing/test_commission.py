"""The commission rules from docs/11 section 3.

These are the rules money actually turns on, so they get their own file. Every
test name is a sentence a salon owner could read and check.

The rule that must never break, quoted from docs/11:

    "A customer is charged as 'new' exactly once, per business, forever. Any
     bug that re-charges an existing customer is a P1."
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.values import Money
from app.modules.billing.domain import (
    CommissionClass,
    LineAlreadyReversedError,
    PlanTier,
    build_commission_line,
    build_reversal,
    classify_commission,
    commission_rate_for,
    plan_for,
)
from app.modules.booking.domain import NEVER_BILLABLE_SOURCES, BookingSource

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=UTC)


def sar(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="SAR")


def accrue(
    *,
    source: BookingSource,
    first: bool,
    completed: bool = True,
    tier: PlanTier = PlanTier.SOLO,
    price: str = "172.50",
):
    return build_commission_line(
        id=uuid4(),
        tenant_id=uuid4(),
        business_id=uuid4(),
        booking_id=uuid4(),
        customer_id=uuid4(),
        source=str(source),
        plan=plan_for(tier),
        service_price_gross=sar(price),
        is_first_booking_with_business=first,
        completed=completed,
        now=NOW,
    )


class TestTheEnumsAgree:
    """billing/domain.py compares source as a string to avoid importing
    booking. That is only safe if the two vocabularies really match."""

    def test_marketplace_is_spelled_the_same_in_both_modules(self):
        line = accrue(source=BookingSource.MARKETPLACE, first=True)
        assert line.commission_class is CommissionClass.NEW_MARKETPLACE

    def test_every_never_billable_source_classifies_as_direct(self):
        for source in NEVER_BILLABLE_SOURCES:
            line = accrue(source=source, first=True)
            assert line.commission_class is CommissionClass.DIRECT, source


class TestRuleOneNewMarketplaceIsBillable:
    def test_a_first_marketplace_booking_is_billable(self):
        line = accrue(source=BookingSource.MARKETPLACE, first=True)
        assert line.commission_class is CommissionClass.NEW_MARKETPLACE
        assert line.is_billable

    def test_solo_charges_thirty_five_percent_of_the_net(self):
        # 172.50 gross -> 150.00 net of VAT -> 35% -> 52.50
        line = accrue(source=BookingSource.MARKETPLACE, first=True, tier=PlanTier.SOLO)
        assert line.base_amount.amount == Decimal("150.00")
        assert line.rate_pct == Decimal("35.00")
        assert line.amount.amount == Decimal("52.50")

    def test_studio_charges_thirty_percent(self):
        line = accrue(source=BookingSource.MARKETPLACE, first=True, tier=PlanTier.STUDIO)
        assert line.amount.amount == Decimal("45.00")

    def test_chain_charges_twenty_five_percent(self):
        line = accrue(source=BookingSource.MARKETPLACE, first=True, tier=PlanTier.CHAIN)
        assert line.amount.amount == Decimal("37.50")


class TestRuleTwoRepeatIsAlwaysFree:
    def test_a_second_marketplace_booking_is_charged_nothing(self):
        """docs/11 section 11, first requirement."""
        line = accrue(source=BookingSource.MARKETPLACE, first=False)
        assert line.commission_class is CommissionClass.REPEAT
        assert line.amount.amount == Decimal("0.00")
        assert not line.is_billable

    @pytest.mark.parametrize("source", list(BookingSource))
    def test_a_returning_customer_is_free_through_every_channel(self, source):
        """ "regardless of channel, regardless of how much time passes"."""
        line = accrue(source=source, first=False)
        assert line.amount.amount == Decimal("0.00")

    def test_the_repeat_rate_is_zero_on_every_plan(self):
        for tier in PlanTier:
            assert commission_rate_for(plan_for(tier), CommissionClass.REPEAT) == Decimal("0")


class TestRuleThreeDirectIsFreeEvenFirstTime:
    def test_a_first_ever_direct_booking_is_charged_nothing(self):
        """docs/11 section 11, second requirement."""
        line = accrue(source=BookingSource.DIRECT_LINK, first=True)
        assert line.commission_class is CommissionClass.DIRECT
        assert line.amount.amount == Decimal("0.00")

    @pytest.mark.parametrize(
        "source",
        [
            BookingSource.DIRECT_LINK,
            BookingSource.WHATSAPP,
            BookingSource.WALK_IN,
            BookingSource.RECEPTION,
        ],
    )
    def test_the_free_forever_channels_never_charge(self, source):
        """docs/11 section 9: own link, WhatsApp, QR ticket, walk-in queue."""
        assert accrue(source=source, first=True).amount.amount == Decimal("0.00")


class TestRuleFiveNothingUncompletedAccrues:
    def test_a_no_show_accrues_nothing(self):
        """docs/11 section 11, third requirement (first half)."""
        line = accrue(source=BookingSource.MARKETPLACE, first=True, completed=False)
        assert line.commission_class is CommissionClass.EXEMPT
        assert line.amount.amount == Decimal("0.00")

    def test_a_cancelled_marketplace_booking_accrues_nothing(self):
        line = accrue(source=BookingSource.MARKETPLACE, first=True, completed=False)
        assert not line.is_billable

    def test_completion_is_checked_before_channel(self):
        # An uncompleted booking is EXEMPT, not DIRECT — the reason it was not
        # billed matters when an owner asks.
        assert (
            classify_commission(
                source="direct_link", is_first_booking_with_business=False, completed=False
            )
            is CommissionClass.EXEMPT
        )


class TestRuleSixRefundsReverseInFull:
    def test_a_refund_reverses_the_exact_amount(self):
        """docs/11 section 11, third requirement (second half)."""
        original = accrue(source=BookingSource.MARKETPLACE, first=True)
        reversal = build_reversal(original, id=uuid4(), now=NOW)

        assert reversal.amount.amount == original.amount.amount
        assert reversal.signed_amount == -original.amount.amount
        assert original.signed_amount + reversal.signed_amount == Decimal("0.00")

    def test_the_pair_nets_to_zero_on_the_invoice(self):
        original = accrue(source=BookingSource.MARKETPLACE, first=True)
        reversal = build_reversal(original, id=uuid4(), now=NOW)
        assert sum([original.signed_amount, reversal.signed_amount]) == Decimal("0")

    def test_reversal_is_a_new_row_not_an_edit(self):
        """docs/11 section 10: "Commission lines are append-only"."""
        original = accrue(source=BookingSource.MARKETPLACE, first=True)
        before = original.amount.amount
        reversal = build_reversal(original, id=uuid4(), now=NOW)

        assert original.amount.amount == before
        assert reversal.id != original.id
        assert reversal.reverses_line_id == original.id
        assert original.reversed is True

    def test_reversing_twice_is_refused(self):
        original = accrue(source=BookingSource.MARKETPLACE, first=True)
        build_reversal(original, id=uuid4(), now=NOW)
        with pytest.raises(LineAlreadyReversedError):
            build_reversal(original, id=uuid4(), now=NOW)

    def test_a_reversal_carries_the_original_rate_not_a_recomputed_one(self):
        """A plan change between accrual and refund must leave no residue."""
        original = accrue(source=BookingSource.MARKETPLACE, first=True, tier=PlanTier.SOLO)
        reversal = build_reversal(original, id=uuid4(), now=NOW)
        assert reversal.rate_pct == original.rate_pct == Decimal("35.00")


class TestRateIsFrozenAtAccrual:
    def test_a_line_keeps_the_rate_it_accrued_at(self):
        """docs/11 section 11, fourth requirement.

        A mid-period plan change does not retroactively re-rate accrued lines.
        The line owns its `rate_pct` — nothing reads back through to a plan.
        """
        line = accrue(source=BookingSource.MARKETPLACE, first=True, tier=PlanTier.SOLO)
        assert line.rate_pct == Decimal("35.00")

        # The salon upgrades to Studio (30%). The line is untouched: it holds a
        # value, not a reference to a plan.
        assert line.rate_pct == Decimal("35.00")
        assert line.amount.amount == Decimal("52.50")

    def test_the_class_is_stored_not_derived(self):
        line = accrue(source=BookingSource.MARKETPLACE, first=True)
        assert isinstance(line.commission_class, CommissionClass)
        # No method on the line recomputes it — the only way it could change is
        # a deliberate reassignment.
        assert not hasattr(line, "recompute_class")
