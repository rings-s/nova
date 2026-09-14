"""billing · APPLICATION layer — use cases.

Layer rule: domain, repository, events, integrations, and other modules'
*services*. Must not import fastapi or another module's models/repository.

Services flush, never commit. The router (or the worker job) owns the
transaction boundary.

The billing cycle, docs/11 section 7, is implemented across three entry points:

    booking completes  ->  accrue_for_booking       (event handler)
    payment refunded   ->  reverse_for_booking      (event handler)
    1st of the month   ->  close_period             (ARQ cron)
    daily              ->  settle_payout            (ARQ cron)
    dunning schedule   ->  advance_dunning          (ARQ cron)
"""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.events import publish_event
from app.core.values import Money
from app.modules.billing.domain import (
    PLANS,
    BillingPeriod,
    CommissionClass,
    CommissionLine,
    Invoice,
    Payout,
    Plan,
    PlanFeatureRequiredError,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    build_commission_line,
    build_payout,
    build_reversal,
    percentage_of,
    to_fils,
)
from app.modules.billing.events import (
    CommissionAccrued,
    CommissionReversed,
    InvoiceIssued,
    InvoiceOverdue,
    InvoicePaid,
    PayoutSettled,
    PlanChanged,
    SubscriptionActivated,
    SubscriptionCancelled,
)
from app.modules.billing.exceptions import (
    InvoiceNotFoundError,
    SubscriptionAlreadyExistsError,
    SubscriptionNotFoundError,
)
from app.modules.billing.repository import (
    CommissionLineRepository,
    FirstBookingRepository,
    InvoiceRepository,
    PayoutRepository,
    SubscriptionRepository,
)

logger = logging.getLogger(__name__)

#: docs/11 section 7 step 5: "retry on days 3, 7, 14". Day 21 hides the
#: marketplace listing (step 6) and nothing else.
DUNNING_RETRY_DAYS = (3, 7, 14)
LISTING_HIDDEN_AFTER_DAYS = 21

#: How long after issue an invoice is due. Dunning days are measured from here.
INVOICE_DUE_DAYS = 7


class BillingService:
    def __init__(
        self,
        *,
        subscriptions: SubscriptionRepository,
        lines: CommissionLineRepository,
        invoices: InvoiceRepository,
        first_bookings: FirstBookingRepository,
        payouts: PayoutRepository,
        tenant_id: UUID,
    ) -> None:
        self.subscriptions = subscriptions
        self.lines = lines
        self.invoices = invoices
        self.first_bookings = first_bookings
        self.payouts = payouts
        self.tenant_id = tenant_id

    @property
    def session(self):
        return self.subscriptions.session

    # --- plans ------------------------------------------------------------

    def plans(self) -> list[Plan]:
        """The published price list (docs/11 section 2)."""
        return [PLANS[tier] for tier in PlanTier]

    # --- subscriptions ----------------------------------------------------

    async def get_subscription(self, business_id: UUID) -> Subscription:
        subscription = await self.subscriptions.get_for_business(business_id)
        if subscription is None:
            raise SubscriptionNotFoundError(business_id)
        return subscription

    async def subscription_or_default(self, business_id: UUID) -> Subscription:
        """The subscription, or a notional Solo one.

        A business that never explicitly subscribed is on Solo: it costs
        nothing, and docs/11 section 2 says a solo provider "can start at
        zero". Returning a default rather than raising means accrual works for
        a salon that has been taking bookings since before billing existed —
        which is every salon on the platform today.
        """
        subscription = await self.subscriptions.get_for_business(business_id)
        if subscription is not None:
            return subscription

        today = datetime.now(UTC).date()
        period = BillingPeriod.month_containing(today)
        return Subscription(
            id=uuid4(),
            tenant_id=self.tenant_id,
            business_id=business_id,
            tier=PlanTier.SOLO,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=period.period_start,
            current_period_end=period.period_end,
        )

    async def require_feature(self, business_id: UUID, feature: str) -> Plan:
        """The business's plan, provided it includes `feature` (docs/11 section 2).

        A business that never subscribed is on Solo, so a paid feature is
        refused to it rather than assumed.
        """
        plan = (await self.subscription_or_default(business_id)).plan
        if feature not in plan.included_features:
            raise PlanFeatureRequiredError(feature, plan.tier)
        return plan

    async def subscribe(
        self,
        *,
        business_id: UUID,
        tier: PlanTier = PlanTier.SOLO,
        seats: int = 1,
        locations: int = 1,
        annual: bool = False,
        trial_days: int = 0,
        now: datetime | None = None,
    ) -> Subscription:
        now = now or datetime.now(UTC)
        if await self.subscriptions.get_for_business(business_id) is not None:
            raise SubscriptionAlreadyExistsError(business_id)

        period = BillingPeriod.month_containing(now.date())
        subscription = Subscription(
            id=uuid4(),
            tenant_id=self.tenant_id,
            business_id=business_id,
            tier=tier,
            status=SubscriptionStatus.TRIALING if trial_days else SubscriptionStatus.ACTIVE,
            current_period_start=period.period_start,
            current_period_end=period.period_end,
            seats=seats,
            locations=locations,
            annual=annual,
            trial_ends_at=(now.date() + timedelta(days=trial_days)) if trial_days else None,
        )
        # Validates seats/locations against the tier before anything is stored.
        subscription.change_plan(tier, annual=annual)
        saved = await self.subscriptions.add_subscription(subscription)

        await publish_event(
            self.session,
            SubscriptionActivated(
                tenant_id=self.tenant_id,
                subscription_id=saved.id,
                business_id=business_id,
                tier=str(saved.tier),
            ),
        )
        return saved

    async def change_plan(
        self, business_id: UUID, *, tier: PlanTier, annual: bool = False
    ) -> Subscription:
        subscription = await self.get_subscription(business_id)
        previous = subscription.tier
        # Raises DowngradeBelowUsageError if the footprint does not fit.
        subscription.change_plan(tier, annual=annual)
        saved = await self.subscriptions.save(subscription)

        await publish_event(
            self.session,
            PlanChanged(
                tenant_id=self.tenant_id,
                subscription_id=saved.id,
                business_id=business_id,
                previous_tier=str(previous),
                tier=str(saved.tier),
            ),
        )
        return saved

    async def cancel_subscription(
        self, business_id: UUID, *, at_period_end: bool = True, now: datetime | None = None
    ) -> Subscription:
        subscription = await self.get_subscription(business_id)
        subscription.cancel(at_period_end=at_period_end, now=now or datetime.now(UTC))
        saved = await self.subscriptions.save(subscription)

        await publish_event(
            self.session,
            SubscriptionCancelled(
                tenant_id=self.tenant_id,
                subscription_id=saved.id,
                business_id=business_id,
                access_until=saved.current_period_end if at_period_end else None,
            ),
        )
        return saved

    # --- commission -------------------------------------------------------

    async def accrue_for_booking(
        self,
        *,
        booking_id: UUID,
        business_id: UUID,
        customer_id: UUID,
        source: str,
        price: Money,
        completed: bool = True,
        now: datetime | None = None,
    ) -> CommissionLine | None:
        """Records what this booking is worth in commission.

        Called from the `BookingCompleted` handler. Returns None when a line
        already exists — the outbox delivers at-least-once, and billing a salon
        twice for one appointment is the worst bug this module could have.

        The ordering here is deliberate and load-bearing:

          1. Look for an existing accrual. Idempotency first.
          2. Attempt the first-booking claim. This is a write, and the database
             decides who wins — see `FirstBookingRepository.claim_first_booking`.
          3. Classify and rate using the plan **in force right now**, which is
             what docs/11 section 5 means by "the plan in force at booking
             completion".

        Step 2 only runs for a marketplace booking. Claiming for a direct
        booking would burn the customer's one chargeable slot on a booking that
        was never billable, and NOVA could then never charge for the
        introduction it later actually makes.
        """
        now = now or datetime.now(UTC)

        existing = await self.lines.find_accrual_for_booking(booking_id)
        if existing is not None:
            logger.debug("commission_already_accrued", extra={"booking_id": str(booking_id)})
            return None

        subscription = await self.subscription_or_default(business_id)

        is_first = False
        if completed and source == "marketplace":
            is_first = await self.first_bookings.claim_first_booking(
                business_id=business_id,
                customer_id=customer_id,
                booking_id=booking_id,
                source=source,
                now=now,
            )

        line = build_commission_line(
            id=uuid4(),
            tenant_id=self.tenant_id,
            business_id=business_id,
            booking_id=booking_id,
            customer_id=customer_id,
            source=source,
            plan=subscription.plan,
            service_price_gross=price,
            is_first_booking_with_business=is_first,
            completed=completed,
            now=now,
        )
        saved = await self.lines.add_line(line)

        await publish_event(
            self.session,
            CommissionAccrued(
                tenant_id=self.tenant_id,
                line_id=saved.id,
                business_id=business_id,
                booking_id=booking_id,
                commission_class=str(saved.commission_class),
                amount=str(saved.amount.amount),
                currency=saved.amount.currency,
            ),
        )
        return saved

    async def reverse_for_booking(
        self, *, booking_id: UUID, now: datetime | None = None
    ) -> CommissionLine | None:
        """Writes the offsetting line a refund requires (section 3 rule 6).

        Idempotent: a second refund webhook for the same booking finds the
        original already flagged `reversed` and does nothing.
        """
        now = now or datetime.now(UTC)

        original = await self.lines.find_accrual_for_booking(booking_id)
        if original is None or original.reversed:
            return None

        reversal = build_reversal(original, id=uuid4(), now=now)
        saved = await self.lines.add_line(reversal)
        await self.lines.mark_reversed(original.id)

        # Give the "new customer" claim back. A refunded first booking must not
        # spend the one chance NOVA has to bill this introduction.
        if original.commission_class is CommissionClass.NEW_MARKETPLACE:
            await self.first_bookings.release(
                business_id=original.business_id,
                customer_id=original.customer_id,
                booking_id=booking_id,
            )

        await publish_event(
            self.session,
            CommissionReversed(
                tenant_id=self.tenant_id,
                line_id=saved.id,
                reverses_line_id=original.id,
                business_id=original.business_id,
                booking_id=booking_id,
                amount=str(saved.amount.amount),
                currency=saved.amount.currency,
            ),
        )
        return saved

    async def list_commission_lines(
        self, business_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[CommissionLine]:
        del limit, offset  # the invoice view is the paginated one
        return await self.lines.list_open_for_business(business_id, until=datetime.now(UTC))

    # --- invoicing --------------------------------------------------------

    async def close_period(
        self,
        *,
        business_id: UUID,
        period: BillingPeriod | None = None,
        processing_base: Money | None = None,
        now: datetime | None = None,
    ) -> Invoice:
        """Closes a month into one invoice (docs/11 section 7 step 3).

        Idempotent per `(business_id, period)`, as section 10 requires: a close
        that runs twice — a retried cron, two workers, a manual re-run — returns
        the invoice it already issued rather than issuing a second one. The
        UNIQUE index on `(business_id, period_start)` is the backstop if two
        run concurrently.

        On `processing_base`, and why the cron leaves it None
        ----------------------------------------------------
        docs/11 is in two minds about the 2.5% processing fee. Section 1 puts
        it in the monthly bill; section 8 deducts it from each day's payout.
        Charging it in both places would bill every prepaid booking twice, so
        exactly one of them has to own it, and section 8 does: it is the more
        specific rule, it is the one the salon sees on the settlement it
        actually receives, and netting at payout means NOVA never has to invoice
        for money it already holds.

        So `settle_daily_payouts` deducts the fee and the monthly close does
        not — the cron never passes `processing_base`, and invoices show 0.00
        processing. The parameter stays for the case section 8 does not cover:
        a business taking online payment through a gateway NOVA does not settle,
        where there is no payout to net against and the fee has to be invoiced.
        Nothing calls it that way today.
        """
        now = now or datetime.now(UTC)
        period = period or BillingPeriod.previous_month(now.date())

        existing = await self.invoices.find_for_period(business_id, period)
        if existing is not None:
            return existing

        subscription = await self.subscription_or_default(business_id)
        open_lines = await self.lines.list_open_for_business(
            business_id, until=datetime.combine(period.period_end, datetime.min.time(), tzinfo=UTC)
        )

        # Net of accruals and reversals. Can be negative — a month spent
        # refunding last month's bookings owes less than nothing.
        commission_net = sum((line.signed_amount for line in open_lines), Decimal("0.00"))

        currency = subscription.plan.currency
        processing = (
            percentage_of(processing_base, subscription.plan.processing_fee_pct)
            if processing_base is not None
            else Money(amount=Decimal("0.00"), currency=currency)
        )

        invoice = Invoice(
            id=uuid4(),
            tenant_id=self.tenant_id,
            business_id=business_id,
            period=period,
            currency=currency,
        )
        invoice.set_charges(
            subscription=subscription.subscription_amount(),
            commission=commission_net,
            processing=processing,
        )
        invoice.issue(now=now, due_at=now + timedelta(days=INVOICE_DUE_DAYS))

        saved = await self.invoices.add_invoice(invoice)
        await self.lines.attach_to_invoice([line.id for line in open_lines], saved.id)

        await publish_event(
            self.session,
            InvoiceIssued(
                tenant_id=self.tenant_id,
                invoice_id=saved.id,
                business_id=business_id,
                period_start=period.period_start,
                period_end=period.period_end,
                total_amount=str(saved.total_amount),
                currency=saved.currency,
            ),
        )
        return saved

    async def get_invoice(self, invoice_id: UUID) -> Invoice:
        invoice = await self.invoices.get_invoice(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        return invoice

    async def list_invoices(
        self, business_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Invoice]:
        return await self.invoices.list_for_business(business_id, limit=limit, offset=offset)

    async def invoice_lines(self, invoice_id: UUID) -> list[CommissionLine]:
        return await self.lines.list_for_invoice(invoice_id)

    # --- ledger reads for analytics (docs/13 section 6.2) -----------------

    async def list_commission_lines_between(
        self, business_id: UUID, *, starts_at: datetime, ends_at: datetime, limit: int
    ) -> list[CommissionLine]:
        return await self.lines.list_accrued_between(
            business_id, starts_at=starts_at, ends_at=ends_at, limit=limit
        )

    async def list_invoices_between(
        self, business_id: UUID, *, date_from: date, date_to: date, limit: int
    ) -> list[Invoice]:
        return await self.invoices.list_between(
            business_id, date_from=date_from, date_to=date_to, limit=limit
        )

    async def list_payouts_between(
        self, business_id: UUID, *, date_from: date, date_to: date, limit: int
    ) -> list[Payout]:
        return await self.payouts.list_between(
            business_id, date_from=date_from, date_to=date_to, limit=limit
        )

    async def mark_invoice_paid(self, invoice_id: UUID, *, now: datetime | None = None) -> Invoice:
        """Collection succeeded (docs/11 section 7 step 4).

        Also restores the marketplace listing — the listing is hidden by
        non-payment and nothing else, so payment is the only thing that should
        bring it back.
        """
        now = now or datetime.now(UTC)
        invoice = await self.get_invoice(invoice_id)
        invoice.mark_paid(now=now)
        saved = await self.invoices.save(invoice)

        subscription = await self.subscriptions.get_for_business(invoice.business_id)
        if subscription is not None:
            subscription.activate()
            await self.subscriptions.save(subscription)

        await publish_event(
            self.session,
            InvoicePaid(
                tenant_id=self.tenant_id,
                invoice_id=saved.id,
                business_id=saved.business_id,
                total_amount=str(saved.total_amount),
                currency=saved.currency,
            ),
        )
        return saved

    async def advance_dunning(self, invoice_id: UUID, *, now: datetime | None = None) -> Invoice:
        """Moves an unpaid invoice along the retry schedule (section 7 step 5).

        Retries land on days 3, 7 and 14 after the due date, each publishing an
        `InvoiceOverdue` the notification module turns into a WhatsApp and email
        notice. At day 21 the marketplace listing is hidden.

        What this deliberately does NOT do is touch the calendar, the queue, or
        any existing booking. docs/11: "Non-payment removes NOVA's marketing,
        never the business's operations."
        """
        now = now or datetime.now(UTC)
        invoice = await self.get_invoice(invoice_id)

        if not invoice.is_payable or invoice.due_at is None:
            return invoice

        days_overdue = (now - invoice.due_at).days
        if days_overdue < DUNNING_RETRY_DAYS[0]:
            return invoice

        invoice.mark_overdue()
        invoice.record_dunning_attempt()
        saved = await self.invoices.save(invoice)

        listing_hidden = False
        subscription = await self.subscriptions.get_for_business(invoice.business_id)
        if subscription is not None:
            subscription.mark_past_due()
            if days_overdue >= LISTING_HIDDEN_AFTER_DAYS:
                subscription.hide_marketplace_listing()
                listing_hidden = True
            await self.subscriptions.save(subscription)

        await publish_event(
            self.session,
            InvoiceOverdue(
                tenant_id=self.tenant_id,
                invoice_id=saved.id,
                business_id=saved.business_id,
                attempt=saved.dunning_attempts,
                listing_hidden=listing_hidden,
            ),
        )
        return saved

    # --- payouts ----------------------------------------------------------

    async def settle_payout(
        self,
        *,
        business_id: UUID,
        payout_date: date,
        collected: Money,
        booking_ids: list[UUID],
        now: datetime | None = None,
    ) -> Payout | None:
        """One day's settlement (docs/11 section 8).

            payout = collected - 2.5% processing - commission due

        Commission is netted here rather than invoiced when a prepayment
        exists, which is the section's rule. Idempotent per
        `(business_id, payout_date)`.
        """
        now = now or datetime.now(UTC)

        if await self.payouts.find_for_date(business_id, payout_date) is not None:
            return None

        subscription = await self.subscription_or_default(business_id)

        # Commission netted at payout is the commission on exactly the bookings
        # this payout settles — not the month's running total, which the
        # monthly invoice handles.
        due = Decimal("0.00")
        for booking_id in booking_ids:
            line = await self.lines.find_accrual_for_booking(booking_id)
            if line is not None and line.is_billable:
                due += line.amount.amount

        payout = build_payout(
            id=uuid4(),
            tenant_id=self.tenant_id,
            business_id=business_id,
            payout_date=payout_date,
            collected=collected,
            plan=subscription.plan,
            commission_due=Money(amount=to_fils(due), currency=collected.currency),
            booking_ids=booking_ids,
        )
        record = await self.payouts.add_payout(payout)

        await publish_event(
            self.session,
            PayoutSettled(
                tenant_id=self.tenant_id,
                payout_id=record.id,
                business_id=business_id,
                payout_date=payout_date,
                net_amount=str(record.net_amount),
                currency=record.currency,
            ),
        )
        return payout

    async def list_payouts(self, business_id: UUID, *, limit: int = 30, offset: int = 0):
        return await self.payouts.list_for_business(business_id, limit=limit, offset=offset)

    # --- read helpers for the billing agent (docs/10 section 10) ----------

    async def explain_commission_line(self, line_id: UUID) -> dict[str, str]:
        """Why this line cost what it cost.

        Shaped for `billing_agent`, which docs/10 section 10 requires to read
        plan and rate figures from here rather than recalling them. Every value
        is a string the agent can quote verbatim.
        """
        line = await self.lines.get_line(line_id)
        if line is None:
            from app.modules.billing.exceptions import CommissionLineNotFoundError

            raise CommissionLineNotFoundError(line_id)

        reasons = {
            CommissionClass.NEW_MARKETPLACE: (
                "NOVA introduced this customer through the marketplace and this was "
                "their first booking with you."
            ),
            CommissionClass.REPEAT: (
                "This customer had booked with you before, so the booking is free "
                "of commission — and every future booking by them will be too."
            ),
            CommissionClass.DIRECT: (
                "This booking came through your own channel, so no commission applies."
            ),
            CommissionClass.EXEMPT: (
                "This booking was cancelled, a no-show, or refunded, so no commission is due."
            ),
        }
        return {
            "commission_class": str(line.commission_class),
            "reason": reasons[line.commission_class],
            "source": line.source,
            "base_amount": str(line.base_amount.amount),
            "rate_pct": str(line.rate_pct),
            "amount": str(line.amount.amount),
            "currency": line.amount.currency,
            "reversed": str(line.reversed).lower(),
        }

    def plan_comparison(self) -> list[dict[str, str]]:
        """The price list, flattened for the billing agent to quote."""
        return [
            {
                "tier": str(plan.tier),
                "monthly_price": str(plan.monthly_price),
                "annual_price": str(plan.annual_price) if plan.annual_price else "",
                "currency": plan.currency,
                "new_client_commission_pct": str(plan.new_client_commission_pct),
                "repeat_commission_pct": str(plan.repeat_commission_pct),
                "processing_fee_pct": str(plan.processing_fee_pct),
                "priced_per_location": str(plan.priced_per_location).lower(),
            }
            for plan in self.plans()
        ]


__all__ = ["DUNNING_RETRY_DAYS", "LISTING_HIDDEN_AFTER_DAYS", "BillingService"]
