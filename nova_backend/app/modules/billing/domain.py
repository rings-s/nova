"""billing · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi or sqlalchemy. Nothing here knows a database exists.

Rich entities rather than validator functions, for the same reason `booking`
has one: a `Subscription`, an `Invoice` and a `CommissionLine` can each be in a
wrong state, and the wrong state costs someone money. An invoice edited after
issue and a line re-rated after accrual are both corrupted aggregates, not
invalid input.

Everything in this file is pure, so the whole commercial model — plans, rates,
VAT, commission classification, invoice arithmetic — is testable with no
database and no clock.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.exceptions import ConflictError, DomainError, ValidationDomainError
from app.core.values import Money

#: KSA VAT, applied to subscription, commission and processing fees alike
#: (docs/11 section 2). Not a plan attribute — it is set by the tax authority,
#: not by us, and a plan that could carry its own rate would invite that
#: confusion.
VAT_RATE = Decimal("0.15")

#: Every amount in this module quantizes to fils before it is stored or summed.
FILS = Decimal("0.01")


class PlanTier(StrEnum):
    SOLO = "solo"
    STUDIO = "studio"
    CHAIN = "chain"


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class CommissionClass(StrEnum):
    """Why a booking was, or was not, billable (docs/11 section 4).

    Derived exactly once, at booking completion, and stored on the line. Never
    recomputed from live data — a customer's history changes as they book
    again, and a line that re-derived itself would silently re-rate the past.
    """

    NEW_MARKETPLACE = "new_marketplace"  # billable
    REPEAT = "repeat"  # 0%
    DIRECT = "direct"  # 0%
    EXEMPT = "exempt"  # cancelled, no-show, refunded


class CommissionLineStatus(StrEnum):
    DRAFT = "draft"  # accrued, not yet on an invoice
    INVOICED = "invoiced"  # closed into an issued invoice


# --- money helpers ---------------------------------------------------------


def to_fils(amount: Decimal) -> Decimal:
    """Rounds to two decimal places, half-up.

    Half-up rather than Python's default banker's rounding: an invoice a
    salon checks by hand should round the way they were taught at school, and
    the fraction of a halala this costs over a year is not worth the support
    conversation.
    """
    return amount.quantize(FILS, rounding=ROUND_HALF_UP)


def percentage_of(base: Money, rate_pct: Decimal) -> Money:
    """`rate_pct` percent of `base`, rounded to fils."""
    if rate_pct < 0:
        raise ValidationDomainError("A rate cannot be negative.")
    return Money(amount=to_fils(base.amount * rate_pct / Decimal(100)), currency=base.currency)


def vat_on(amount: Money) -> Money:
    return Money(amount=to_fils(amount.amount * VAT_RATE), currency=amount.currency)


# --- plans -----------------------------------------------------------------


class Plan(BaseModel):
    """A price list entry (docs/11 section 2). Immutable by construction."""

    model_config = {"frozen": True}

    tier: PlanTier
    monthly_price: Decimal
    annual_price: Decimal | None = None
    currency: str = "SAR"

    new_client_commission_pct: Decimal
    repeat_commission_pct: Decimal = Decimal("0")
    processing_fee_pct: Decimal = Decimal("2.5")

    #: `None` means unlimited. A number is a hard ceiling the domain refuses to
    #: let a subscription exceed.
    max_seats: int | None = None
    max_locations: int | None = None
    whatsapp_reminders_per_month: int | None = None

    #: Chain is priced "449 SAR / month per location"; the others are flat.
    priced_per_location: bool = False
    contract_months: int = 0
    included_features: list[str] = Field(default_factory=list)

    def subscription_amount(self, *, locations: int) -> Money:
        """What this plan bills per month for the given footprint."""
        multiplier = Decimal(locations) if self.priced_per_location else Decimal(1)
        return Money(amount=to_fils(self.monthly_price * multiplier), currency=self.currency)


#: The published price list. A dict rather than rows in a table on purpose:
#: these are OUR prices, they change by deploy and not by admin action, and a
#: plan that could be edited at runtime is one that can be edited wrongly at
#: runtime. A negotiated Chain contract is modelled as an override on the
#: subscription, not as a mutated plan.
PLANS: dict[PlanTier, Plan] = {
    PlanTier.SOLO: Plan(
        tier=PlanTier.SOLO,
        monthly_price=Decimal("0.00"),
        annual_price=None,
        new_client_commission_pct=Decimal("35.00"),
        max_seats=1,
        max_locations=1,
        whatsapp_reminders_per_month=100,
        included_features=[
            "marketplace_profile",
            "calendar",
            "queue_and_tickets",
            "ai_booking_agent",
            "ai_support_agent",
        ],
    ),
    PlanTier.STUDIO: Plan(
        tier=PlanTier.STUDIO,
        monthly_price=Decimal("199.00"),
        # Two months free, per docs/11 section 2.
        annual_price=Decimal("1990.00"),
        new_client_commission_pct=Decimal("30.00"),
        max_seats=None,
        max_locations=1,
        whatsapp_reminders_per_month=None,
        included_features=[
            "marketplace_profile",
            "calendar",
            "queue_and_tickets",
            "ai_booking_agent",
            "ai_support_agent",
            "ai_insights_agent",
            "ai_retention_campaigns",
            "pos_and_product_sales",
        ],
    ),
    PlanTier.CHAIN: Plan(
        tier=PlanTier.CHAIN,
        monthly_price=Decimal("449.00"),
        # "Negotiated" — no published annual price.
        annual_price=None,
        new_client_commission_pct=Decimal("25.00"),
        max_seats=None,
        max_locations=None,
        whatsapp_reminders_per_month=None,
        priced_per_location=True,
        contract_months=12,
        included_features=[
            "marketplace_profile",
            "calendar",
            "queue_and_tickets",
            "ai_booking_agent",
            "ai_support_agent",
            "ai_insights_agent",
            "ai_retention_campaigns",
            "pos_and_product_sales",
            "cross_location_reporting",
            "api_access",
        ],
    ),
}


def plan_for(tier: PlanTier) -> Plan:
    return PLANS[tier]


class BillingPeriod(BaseModel):
    """A closed month. Half-open at the end, like every other range here."""

    model_config = {"frozen": True}

    period_start: date
    period_end: date

    @classmethod
    def month_containing(cls, moment: date) -> "BillingPeriod":
        start = moment.replace(day=1)
        end = (
            date(start.year + 1, 1, 1)
            if start.month == 12
            else date(start.year, start.month + 1, 1)
        )
        return cls(period_start=start, period_end=end)

    @classmethod
    def previous_month(cls, today: date) -> "BillingPeriod":
        """The period a close on the 1st actually bills (docs/11 section 7)."""
        first_of_this_month = today.replace(day=1)
        return cls.month_containing(first_of_this_month - timedelta(days=1))

    def contains(self, moment: datetime) -> bool:
        return self.period_start <= moment.date() < self.period_end


# --- errors ----------------------------------------------------------------


class InvoiceAlreadyIssuedError(ConflictError):
    code = "invoice_already_issued"

    def __init__(self) -> None:
        super().__init__(
            "An issued invoice cannot be edited. Issue a credit note instead (docs/11 section 5)."
        )


class DowngradeBelowUsageError(ConflictError):
    code = "downgrade_below_usage"

    def __init__(self, *, what: str, requested: int, in_use: int) -> None:
        super().__init__(
            f"Cannot move to a plan allowing {requested} {what} while {in_use} are in use. "
            f"Remove the extras first."
        )


class LineAlreadyReversedError(ConflictError):
    code = "commission_line_already_reversed"

    def __init__(self) -> None:
        super().__init__("This commission line has already been reversed.")


class LineAlreadyInvoicedError(ConflictError):
    code = "commission_line_already_invoiced"

    def __init__(self) -> None:
        super().__init__("A line already closed into an issued invoice cannot be re-rated.")


# --- commission ------------------------------------------------------------


def classify_commission(
    *,
    source: str,
    is_first_booking_with_business: bool,
    completed: bool,
) -> CommissionClass:
    """Decides whether a completed booking is billable (docs/11 section 3).

    The order of these branches is the order of the documented rules, and it
    matters:

      - rule 5 first: nothing that did not COMPLETE is ever billable, whatever
        channel it came from.
      - rule 3 next: a booking through the salon's own link, WhatsApp, QR or
        walk-in queue is free even on the customer's first ever visit.
      - rule 2 next: a later booking by a customer the business already has is
        free regardless of channel, forever.
      - rule 1 last, as the only remaining case: NOVA introduced this customer
        through the marketplace and this is their first booking here.

    `is_first_booking_with_business` is answered by a UNIQUE index, not a
    query — see `service.BillingService.accrue_for_booking`.
    """
    if not completed:
        return CommissionClass.EXEMPT
    if source != _MARKETPLACE:
        return CommissionClass.DIRECT
    if not is_first_booking_with_business:
        return CommissionClass.REPEAT
    return CommissionClass.NEW_MARKETPLACE


#: The one `BookingSource` value that can carry commission. Compared as a
#: string rather than importing `booking.domain`, so the domain layer of
#: billing depends on no other module — the value is asserted against the real
#: enum in `tests/modules/billing/test_commission.py`.
_MARKETPLACE = "marketplace"


def commission_rate_for(plan: Plan, commission_class: CommissionClass) -> Decimal:
    """The percentage this class attracts on this plan."""
    if commission_class is CommissionClass.NEW_MARKETPLACE:
        return plan.new_client_commission_pct
    return Decimal("0")


def commission_base(service_price_gross: Money, *, discount: Money | None = None) -> Money:
    """What the percentage applies to (docs/11 section 3 rule 7).

    "The service price net of VAT and net of discounts, excluding tips and
    retail products." Catalog prices are VAT-inclusive as displayed to the
    customer, so VAT is removed here rather than assumed away — charging
    commission on the government's share would be charging the salon for tax
    it merely collected.

    Tips and retail are not subtracted because they never enter: a booking's
    `price` is the service price, and nothing else reaches this function.
    """
    net_of_discount = service_price_gross.amount - (discount.amount if discount else Decimal(0))
    if net_of_discount < 0:
        raise ValidationDomainError("A discount cannot exceed the service price.")

    net_of_vat = net_of_discount / (Decimal(1) + VAT_RATE)
    return Money(amount=to_fils(net_of_vat), currency=service_price_gross.currency)


@dataclass
class CommissionLine:
    """One booking's commission decision, frozen at accrual.

    Append-only (docs/11 section 10): a reversal is a *new* line pointing back
    at this one, never an edit. `amount` is therefore always non-negative and
    `signed_amount` carries the direction, which keeps `Money`'s own
    non-negative invariant intact instead of working around it.
    """

    id: UUID
    tenant_id: UUID
    business_id: UUID
    booking_id: UUID
    customer_id: UUID
    source: str
    commission_class: CommissionClass
    base_amount: Money
    rate_pct: Decimal
    amount: Money
    status: CommissionLineStatus = CommissionLineStatus.DRAFT
    #: Set on the ORIGINAL when a reversal is written against it. docs/11's
    #: `CommissionLineOut.reversed` is this flag.
    reversed: bool = False
    is_reversal: bool = False
    reverses_line_id: UUID | None = None
    invoice_id: UUID | None = None
    accrued_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def signed_amount(self) -> Decimal:
        """What this line contributes to an invoice total."""
        return -self.amount.amount if self.is_reversal else self.amount.amount

    @property
    def is_billable(self) -> bool:
        """Whether this line is money NOVA is still owed.

        `reversed` matters as much as the class does: the payout job nets
        billable commission out of the salon's takings, and deducting a
        commission that a refund already cancelled would take money the salon
        does not owe.
        """
        return (
            self.commission_class is CommissionClass.NEW_MARKETPLACE
            and not self.is_reversal
            and not self.reversed
        )

    def mark_reversed(self) -> None:
        if self.reversed:
            raise LineAlreadyReversedError()
        self.reversed = True

    def attach_to_invoice(self, invoice_id: UUID) -> None:
        if self.status is CommissionLineStatus.INVOICED:
            raise LineAlreadyInvoicedError()
        self.invoice_id = invoice_id
        self.status = CommissionLineStatus.INVOICED


def build_commission_line(
    *,
    id: UUID,
    tenant_id: UUID,
    business_id: UUID,
    booking_id: UUID,
    customer_id: UUID,
    source: str,
    plan: Plan,
    service_price_gross: Money,
    is_first_booking_with_business: bool,
    completed: bool = True,
    discount: Money | None = None,
    now: datetime | None = None,
) -> CommissionLine:
    """Accrues a line for one completed booking.

    The plan passed here is the one **in force at completion** (docs/11 section
    5). Reading it at invoice time instead would re-rate a month retroactively
    every time a salon changed plan.
    """
    commission_class = classify_commission(
        source=source,
        is_first_booking_with_business=is_first_booking_with_business,
        completed=completed,
    )
    base = commission_base(service_price_gross, discount=discount)
    rate = commission_rate_for(plan, commission_class)

    return CommissionLine(
        id=id,
        tenant_id=tenant_id,
        business_id=business_id,
        booking_id=booking_id,
        customer_id=customer_id,
        source=source,
        commission_class=commission_class,
        base_amount=base,
        rate_pct=rate,
        amount=percentage_of(base, rate),
        accrued_at=now or datetime.now(UTC),
    )


def build_reversal(
    original: CommissionLine, *, id: UUID, now: datetime | None = None
) -> CommissionLine:
    """The offsetting line a refund writes (docs/11 section 3 rule 6).

    Carries the original's amount and rate verbatim so the pair nets to exactly
    zero. Recomputing here would let a plan change between accrual and refund
    leave a residue on the invoice.
    """
    original.mark_reversed()
    return CommissionLine(
        id=id,
        tenant_id=original.tenant_id,
        business_id=original.business_id,
        booking_id=original.booking_id,
        customer_id=original.customer_id,
        source=original.source,
        commission_class=CommissionClass.EXEMPT,
        base_amount=original.base_amount,
        rate_pct=original.rate_pct,
        amount=original.amount,
        is_reversal=True,
        reverses_line_id=original.id,
        accrued_at=now or datetime.now(UTC),
    )


# --- subscription ----------------------------------------------------------


@dataclass
class Subscription:
    """What plan a business is on, and whether it is paid up.

    Belongs to exactly one tenant (docs/11 section 5) and is keyed to one
    business, which is what every schema in section 6 is keyed to.
    """

    id: UUID
    tenant_id: UUID
    business_id: UUID
    tier: PlanTier
    status: SubscriptionStatus
    current_period_start: date
    current_period_end: date
    seats: int = 1
    locations: int = 1
    annual: bool = False
    cancel_at_period_end: bool = False
    trial_ends_at: date | None = None
    cancelled_at: datetime | None = None
    #: A negotiated Chain price. `None` means the published rate applies.
    negotiated_monthly_price: Decimal | None = None
    #: docs/11 section 7 step 6. Set by dunning at day 21, cleared on payment.
    marketplace_listing_hidden: bool = False

    @property
    def plan(self) -> Plan:
        return plan_for(self.tier)

    def subscription_amount(self) -> Money:
        """The recurring charge for the current footprint."""
        if self.negotiated_monthly_price is not None:
            return Money(amount=to_fils(self.negotiated_monthly_price), currency=self.plan.currency)
        return self.plan.subscription_amount(locations=self.locations)

    def commission_rate(self, commission_class: CommissionClass) -> Decimal:
        return commission_rate_for(self.plan, commission_class)

    def change_plan(self, tier: PlanTier, *, annual: bool = False) -> None:
        """Moves plan, refusing a downgrade the current usage does not fit.

        docs/11 section 5: "Downgrading below current usage (seats, locations)
        is refused by the domain." Refusing here rather than silently dropping
        staff or branches means the salon decides what to remove, not us.
        """
        target = plan_for(tier)

        if target.max_seats is not None and self.seats > target.max_seats:
            raise DowngradeBelowUsageError(
                what="staff seats", requested=target.max_seats, in_use=self.seats
            )
        if target.max_locations is not None and self.locations > target.max_locations:
            raise DowngradeBelowUsageError(
                what="locations", requested=target.max_locations, in_use=self.locations
            )
        if annual and target.annual_price is None:
            raise ValidationDomainError(f"The {tier} plan has no annual price.")

        self.tier = tier
        self.annual = annual
        # Deliberately does NOT touch accrued commission lines. They carry the
        # rate that was in force when each booking completed (section 5), and
        # docs/11 section 11 asserts a mid-period change does not re-rate them.

    def add_location(self) -> None:
        limit = self.plan.max_locations
        if limit is not None and self.locations + 1 > limit:
            raise DowngradeBelowUsageError(
                what="locations", requested=limit, in_use=self.locations + 1
            )
        self.locations += 1

    def add_seat(self) -> None:
        limit = self.plan.max_seats
        if limit is not None and self.seats + 1 > limit:
            raise DowngradeBelowUsageError(
                what="staff seats", requested=limit, in_use=self.seats + 1
            )
        self.seats += 1

    def activate(self) -> None:
        self.status = SubscriptionStatus.ACTIVE
        self.marketplace_listing_hidden = False

    def mark_past_due(self) -> None:
        if self.status is SubscriptionStatus.CANCELLED:
            return
        self.status = SubscriptionStatus.PAST_DUE

    def hide_marketplace_listing(self) -> None:
        """Day 21 of dunning (docs/11 section 7 step 6).

        This is the ONLY thing non-payment does. The calendar, the queue,
        existing bookings, tickets and check-ins keep working — docs/11 is
        explicit that NOVA removes its own marketing, never the salon's
        operations.
        """
        self.marketplace_listing_hidden = True

    def cancel(self, *, at_period_end: bool = True, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        self.cancelled_at = now
        if at_period_end:
            self.cancel_at_period_end = True
        else:
            self.status = SubscriptionStatus.CANCELLED

    def has_access_on(self, day: date) -> bool:
        """docs/11 section 5: a cancelled subscription keeps read access to the
        end of the period it already paid for."""
        if self.status is not SubscriptionStatus.CANCELLED:
            return True
        return day < self.current_period_end


# --- invoice ---------------------------------------------------------------


@dataclass
class Invoice:
    """A closed month of charges for one business. Immutable once issued."""

    id: UUID
    tenant_id: UUID
    business_id: UUID
    period: BillingPeriod
    status: InvoiceStatus = InvoiceStatus.DRAFT
    currency: str = "SAR"
    subscription_amount: Decimal = Decimal("0.00")
    commission_amount: Decimal = Decimal("0.00")
    processing_amount: Decimal = Decimal("0.00")
    vat_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    issued_at: datetime | None = None
    due_at: datetime | None = None
    paid_at: datetime | None = None
    #: Dunning attempts made on days 3, 7 and 14 (docs/11 section 7 step 5).
    dunning_attempts: int = 0

    def assert_mutable(self) -> None:
        """docs/11 section 5: "An issued invoice is never edited."."""
        if self.status is not InvoiceStatus.DRAFT:
            raise InvoiceAlreadyIssuedError()

    @property
    def net_amount(self) -> Decimal:
        """Everything VAT is charged on."""
        return self.subscription_amount + self.commission_amount + self.processing_amount

    def set_charges(
        self,
        *,
        subscription: Money,
        commission: Decimal,
        processing: Money,
    ) -> None:
        """Writes the three charge lines and derives VAT and the total.

        `commission` is a bare Decimal, not Money, because it is a *net* of
        accruals and reversals and can legitimately be negative — a month whose
        only activity was refunding last month's bookings owes less than
        nothing in commission. `Money` forbids that, correctly, for an amount;
        this is a subtotal.
        """
        self.assert_mutable()

        if subscription.currency != processing.currency:
            raise ValidationDomainError("An invoice cannot mix currencies.")
        self.currency = subscription.currency

        self.subscription_amount = to_fils(subscription.amount)
        self.commission_amount = to_fils(commission)
        self.processing_amount = to_fils(processing.amount)

        # VAT on the net, then the total — computed in that order and stored,
        # so the document a salon downloads still adds up years later even if
        # the rate changes.
        self.vat_amount = to_fils(self.net_amount * VAT_RATE)
        self.total_amount = to_fils(self.net_amount + self.vat_amount)

    def reconciles(self) -> bool:
        """docs/11 section 11: totals reconcile to the fils."""
        return self.total_amount == to_fils(self.net_amount + self.vat_amount)

    def issue(self, *, now: datetime, due_at: datetime) -> None:
        self.assert_mutable()
        self.status = InvoiceStatus.ISSUED
        self.issued_at = now
        self.due_at = due_at

    def mark_paid(self, *, now: datetime) -> None:
        if self.status in (InvoiceStatus.VOID, InvoiceStatus.PAID):
            return
        self.status = InvoiceStatus.PAID
        self.paid_at = now

    def mark_overdue(self) -> None:
        if self.status is not InvoiceStatus.ISSUED:
            return
        self.status = InvoiceStatus.OVERDUE

    def record_dunning_attempt(self) -> None:
        self.dunning_attempts += 1

    def void(self) -> None:
        if self.status is InvoiceStatus.PAID:
            raise ConflictError("A paid invoice cannot be voided. Issue a credit note.")
        self.status = InvoiceStatus.VOID

    @property
    def is_payable(self) -> bool:
        return self.status in (InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE)


# --- payouts ---------------------------------------------------------------


@dataclass
class Payout:
    """One day's settlement to a business (docs/11 section 8).

        payout = collected - 2.5% processing - commission due

    Commission is netted here when a prepayment exists, which is why a payout
    references the bookings it settles: the salon's accountant has to be able
    to tie every deduction back to an appointment.
    """

    id: UUID
    tenant_id: UUID
    business_id: UUID
    payout_date: date
    collected_amount: Money
    processing_fee: Money
    commission_netted: Money
    booking_ids: list[UUID] = field(default_factory=list)
    paid_at: datetime | None = None

    @property
    def net_amount(self) -> Decimal:
        return to_fils(
            self.collected_amount.amount
            - self.processing_fee.amount
            - self.commission_netted.amount
        )


def build_payout(
    *,
    id: UUID,
    tenant_id: UUID,
    business_id: UUID,
    payout_date: date,
    collected: Money,
    plan: Plan,
    commission_due: Money,
    booking_ids: list[UUID],
) -> Payout:
    processing = percentage_of(collected, plan.processing_fee_pct)
    return Payout(
        id=id,
        tenant_id=tenant_id,
        business_id=business_id,
        payout_date=payout_date,
        collected_amount=collected,
        processing_fee=processing,
        commission_netted=commission_due,
        booking_ids=booking_ids,
    )


class PlanFeatureRequiredError(DomainError):
    """A plan-gated feature, asked for on a plan that does not include it.

    docs/11 section 2 sells the insights agents and cross-location reporting on
    paid tiers only. 403 rather than 402: nothing is wrong with the request or
    the account, the plan simply does not cover it.
    """

    status_code = 403
    code = "plan_feature_required"

    def __init__(self, feature: str, tier: PlanTier) -> None:
        super().__init__(f"The {tier} plan does not include '{feature}'.")
        self.feature = feature


__all__ = [
    "PLANS",
    "VAT_RATE",
    "BillingPeriod",
    "CommissionClass",
    "CommissionLine",
    "CommissionLineStatus",
    "DowngradeBelowUsageError",
    "Invoice",
    "InvoiceAlreadyIssuedError",
    "InvoiceStatus",
    "Payout",
    "Plan",
    "PlanFeatureRequiredError",
    "PlanTier",
    "Subscription",
    "SubscriptionStatus",
    "build_commission_line",
    "build_payout",
    "build_reversal",
    "classify_commission",
    "commission_base",
    "commission_rate_for",
    "percentage_of",
    "plan_for",
    "to_fils",
    "vat_on",
]
