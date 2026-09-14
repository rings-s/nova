"""billing · PERSISTENCE layer — queries and domain<->row mapping.

Layer rule: models + `app.db` + this module's domain. Must not import
service, router, or fastapi.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.values import Money
from app.db.repository import TenantScopedRepository
from app.modules.billing.domain import (
    BillingPeriod,
    CommissionLine,
    CommissionLineStatus,
    Invoice,
    InvoiceStatus,
    Payout,
    Subscription,
    SubscriptionStatus,
)
from app.modules.billing.models import (
    CommissionLineRecord,
    CustomerBusinessFirstBookingRecord,
    InvoiceRecord,
    PayoutRecord,
    SubscriptionRecord,
)

# --- subscriptions ---------------------------------------------------------


def _subscription_to_domain(record: SubscriptionRecord) -> Subscription:
    return Subscription(
        id=record.id,
        tenant_id=record.tenant_id,
        business_id=record.business_id,
        tier=record.tier,
        status=record.status,
        current_period_start=record.current_period_start,
        current_period_end=record.current_period_end,
        seats=record.seats,
        locations=record.locations,
        annual=record.annual,
        cancel_at_period_end=record.cancel_at_period_end,
        trial_ends_at=record.trial_ends_at,
        cancelled_at=record.cancelled_at,
        negotiated_monthly_price=record.negotiated_monthly_price,
        marketplace_listing_hidden=record.marketplace_listing_hidden,
    )


def _apply_subscription(subscription: Subscription, record: SubscriptionRecord) -> None:
    record.tier = subscription.tier
    record.status = subscription.status
    record.current_period_start = subscription.current_period_start
    record.current_period_end = subscription.current_period_end
    record.seats = subscription.seats
    record.locations = subscription.locations
    record.annual = subscription.annual
    record.cancel_at_period_end = subscription.cancel_at_period_end
    record.trial_ends_at = subscription.trial_ends_at
    record.cancelled_at = subscription.cancelled_at
    record.negotiated_monthly_price = subscription.negotiated_monthly_price
    record.marketplace_listing_hidden = subscription.marketplace_listing_hidden


class SubscriptionRepository(TenantScopedRepository[SubscriptionRecord]):
    model = SubscriptionRecord

    async def get_for_business(self, business_id: UUID) -> Subscription | None:
        stmt = self._scope(
            select(SubscriptionRecord).where(SubscriptionRecord.business_id == business_id)
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        return _subscription_to_domain(record) if record else None

    async def add_subscription(self, subscription: Subscription) -> Subscription:
        record = SubscriptionRecord(
            id=subscription.id,
            tenant_id=subscription.tenant_id,
            business_id=subscription.business_id,
            tier=subscription.tier,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            seats=subscription.seats,
            locations=subscription.locations,
            annual=subscription.annual,
            trial_ends_at=subscription.trial_ends_at,
            negotiated_monthly_price=subscription.negotiated_monthly_price,
        )
        self.add(record)
        await self.session.flush()
        return _subscription_to_domain(record)

    async def save(self, subscription: Subscription) -> Subscription:
        record = await super().get(subscription.id)
        if record is None:
            raise ValueError(f"Subscription {subscription.id} vanished mid-transaction.")
        _apply_subscription(subscription, record)
        await self.session.flush()
        return _subscription_to_domain(record)

    async def list_active(self, *, limit: int = 500) -> list[Subscription]:
        """Everything the monthly close has to bill."""
        stmt = (
            self._scope(select(SubscriptionRecord))
            .where(SubscriptionRecord.status != SubscriptionStatus.CANCELLED)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_subscription_to_domain(r) for r in rows]


# --- first-booking claim ---------------------------------------------------


class FirstBookingRepository(TenantScopedRepository[CustomerBusinessFirstBookingRecord]):
    """The "new exactly once" gate (docs/11 section 10)."""

    model = CustomerBusinessFirstBookingRecord

    async def claim_first_booking(
        self,
        *,
        business_id: UUID,
        customer_id: UUID,
        booking_id: UUID,
        source: str,
        now: datetime,
    ) -> bool:
        """Attempts to claim this customer as new for this business.

        Returns True only if this call won. Implemented as
        `INSERT ... ON CONFLICT DO NOTHING` on the unique
        `(business_id, customer_id)` index, deliberately NOT as a SELECT
        followed by an INSERT.

        That distinction is the whole point. docs/11 section 11 requires that
        "two concurrent first bookings for the same customer produce exactly
        one billable line" — a read-then-write loses that race whatever the
        isolation level, because both transactions read an empty table before
        either writes. Here the database arbitrates, and the loser is told it
        lost by the row count.

        A subsequent booking by the same customer finds the row already taken
        and is classified REPEAT, forever, which is the rule docs/11 says must
        never break.
        """
        stmt = (
            insert(CustomerBusinessFirstBookingRecord)
            .values(
                tenant_id=self.tenant_id,
                business_id=business_id,
                customer_id=customer_id,
                booking_id=booking_id,
                source=source,
                first_completed_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_first_booking_business_customer")
            .returning(CustomerBusinessFirstBookingRecord.id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def release(self, *, business_id: UUID, customer_id: UUID, booking_id: UUID) -> None:
        """Gives the claim back when the booking that won it is refunded.

        Without this a refunded first booking would burn the customer's one
        chargeable slot: they would be `REPEAT` forever and NOVA could never
        bill the introduction it actually made. Scoped to `booking_id` so it
        only ever releases a claim this booking won.
        """
        stmt = self._scope(
            select(CustomerBusinessFirstBookingRecord).where(
                CustomerBusinessFirstBookingRecord.business_id == business_id,
                CustomerBusinessFirstBookingRecord.customer_id == customer_id,
                CustomerBusinessFirstBookingRecord.booking_id == booking_id,
            )
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        if record is not None:
            await self.session.delete(record)
            await self.session.flush()


# --- commission lines ------------------------------------------------------


def _line_to_domain(record: CommissionLineRecord) -> CommissionLine:
    return CommissionLine(
        id=record.id,
        tenant_id=record.tenant_id,
        business_id=record.business_id,
        booking_id=record.booking_id,
        customer_id=record.customer_id,
        source=record.source,
        commission_class=record.commission_class,
        base_amount=Money(amount=record.base_amount, currency=record.currency),
        rate_pct=record.rate_pct,
        amount=Money(amount=record.amount, currency=record.currency),
        status=record.status,
        reversed=record.reversed,
        is_reversal=record.is_reversal,
        reverses_line_id=record.reverses_line_id,
        invoice_id=record.invoice_id,
        accrued_at=record.accrued_at,
    )


class CommissionLineRepository(TenantScopedRepository[CommissionLineRecord]):
    model = CommissionLineRecord

    async def add_line(self, line: CommissionLine) -> CommissionLine:
        record = CommissionLineRecord(
            id=line.id,
            tenant_id=line.tenant_id,
            business_id=line.business_id,
            booking_id=line.booking_id,
            customer_id=line.customer_id,
            source=line.source,
            commission_class=line.commission_class,
            base_amount=line.base_amount.amount,
            rate_pct=line.rate_pct,
            amount=line.amount.amount,
            currency=line.amount.currency,
            status=line.status,
            reversed=line.reversed,
            is_reversal=line.is_reversal,
            reverses_line_id=line.reverses_line_id,
            accrued_at=line.accrued_at,
        )
        self.add(record)
        await self.session.flush()
        return _line_to_domain(record)

    async def get_line(self, line_id: UUID) -> CommissionLine | None:
        record = await super().get(line_id)
        return _line_to_domain(record) if record else None

    async def find_accrual_for_booking(self, booking_id: UUID) -> CommissionLine | None:
        """The original (non-reversal) line for a booking, if one exists."""
        stmt = self._scope(
            select(CommissionLineRecord).where(
                CommissionLineRecord.booking_id == booking_id,
                CommissionLineRecord.is_reversal.is_(False),
            )
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        return _line_to_domain(record) if record else None

    async def mark_reversed(self, line_id: UUID) -> None:
        record = await super().get(line_id)
        if record is not None:
            record.reversed = True
            await self.session.flush()

    async def list_open_for_business(
        self, business_id: UUID, *, until: datetime
    ) -> list[CommissionLine]:
        """Draft lines accrued before the period closed.

        `until` rather than a full range: a line accrued *before* the period
        under close but never invoiced (because the close failed, say) belongs
        on this invoice rather than being stranded forever.
        """
        stmt = self._scope(
            select(CommissionLineRecord).where(
                CommissionLineRecord.business_id == business_id,
                CommissionLineRecord.status == CommissionLineStatus.DRAFT,
                CommissionLineRecord.accrued_at < until,
            )
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_line_to_domain(r) for r in rows]

    async def list_for_invoice(self, invoice_id: UUID) -> list[CommissionLine]:
        stmt = self._scope(
            select(CommissionLineRecord).where(CommissionLineRecord.invoice_id == invoice_id)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_line_to_domain(r) for r in rows]

    async def list_accrued_between(
        self, business_id: UUID, *, starts_at: datetime, ends_at: datetime, limit: int
    ) -> list[CommissionLine]:
        """Lines accrued in a window, reversals included, for the accountant."""
        stmt = (
            self._scope(
                select(CommissionLineRecord).where(
                    CommissionLineRecord.business_id == business_id,
                    CommissionLineRecord.accrued_at >= starts_at,
                    CommissionLineRecord.accrued_at < ends_at,
                )
            )
            .order_by(CommissionLineRecord.accrued_at)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_line_to_domain(r) for r in rows]

    async def attach_to_invoice(self, line_ids: list[UUID], invoice_id: UUID) -> None:
        if not line_ids:
            return
        stmt = self._scope(
            select(CommissionLineRecord).where(CommissionLineRecord.id.in_(line_ids))
        )
        for record in (await self.session.execute(stmt)).scalars().all():
            record.invoice_id = invoice_id
            record.status = CommissionLineStatus.INVOICED
        await self.session.flush()


# --- invoices --------------------------------------------------------------


def _invoice_to_domain(record: InvoiceRecord) -> Invoice:
    return Invoice(
        id=record.id,
        tenant_id=record.tenant_id,
        business_id=record.business_id,
        period=BillingPeriod(period_start=record.period_start, period_end=record.period_end),
        status=record.status,
        currency=record.currency,
        subscription_amount=record.subscription_amount,
        commission_amount=record.commission_amount,
        processing_amount=record.processing_amount,
        vat_amount=record.vat_amount,
        total_amount=record.total_amount,
        issued_at=record.issued_at,
        due_at=record.due_at,
        paid_at=record.paid_at,
        dunning_attempts=record.dunning_attempts,
    )


class InvoiceRepository(TenantScopedRepository[InvoiceRecord]):
    model = InvoiceRecord

    async def get_invoice(self, invoice_id: UUID) -> Invoice | None:
        record = await super().get(invoice_id)
        return _invoice_to_domain(record) if record else None

    async def find_for_period(self, business_id: UUID, period: BillingPeriod) -> Invoice | None:
        stmt = self._scope(
            select(InvoiceRecord).where(
                InvoiceRecord.business_id == business_id,
                InvoiceRecord.period_start == period.period_start,
            )
        )
        record = (await self.session.execute(stmt)).scalar_one_or_none()
        return _invoice_to_domain(record) if record else None

    async def add_invoice(self, invoice: Invoice) -> Invoice:
        record = InvoiceRecord(
            id=invoice.id,
            tenant_id=invoice.tenant_id,
            business_id=invoice.business_id,
            period_start=invoice.period.period_start,
            period_end=invoice.period.period_end,
            status=invoice.status,
            subscription_amount=invoice.subscription_amount,
            commission_amount=invoice.commission_amount,
            processing_amount=invoice.processing_amount,
            vat_amount=invoice.vat_amount,
            total_amount=invoice.total_amount,
            currency=invoice.currency,
            issued_at=invoice.issued_at,
            due_at=invoice.due_at,
        )
        self.add(record)
        await self.session.flush()
        return _invoice_to_domain(record)

    async def save(self, invoice: Invoice) -> Invoice:
        record = await super().get(invoice.id)
        if record is None:
            raise ValueError(f"Invoice {invoice.id} vanished mid-transaction.")
        record.status = invoice.status
        record.subscription_amount = invoice.subscription_amount
        record.commission_amount = invoice.commission_amount
        record.processing_amount = invoice.processing_amount
        record.vat_amount = invoice.vat_amount
        record.total_amount = invoice.total_amount
        record.currency = invoice.currency
        record.issued_at = invoice.issued_at
        record.due_at = invoice.due_at
        record.paid_at = invoice.paid_at
        record.dunning_attempts = invoice.dunning_attempts
        await self.session.flush()
        return _invoice_to_domain(record)

    async def list_for_business(
        self, business_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[Invoice]:
        stmt = (
            self._scope(select(InvoiceRecord).where(InvoiceRecord.business_id == business_id))
            .order_by(InvoiceRecord.period_start.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_invoice_to_domain(r) for r in rows]

    async def list_between(
        self, business_id: UUID, *, date_from: date, date_to: date, limit: int
    ) -> list[Invoice]:
        """Invoices whose billing period starts inside a date range, oldest first."""
        stmt = (
            self._scope(
                select(InvoiceRecord).where(
                    InvoiceRecord.business_id == business_id,
                    InvoiceRecord.period_start >= date_from,
                    InvoiceRecord.period_start <= date_to,
                )
            )
            .order_by(InvoiceRecord.period_start)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_invoice_to_domain(r) for r in rows]


class UnscopedInvoiceRepository:
    """Cross-tenant reads for the dunning worker.

    The monthly close and the retry schedule run for the whole platform, not
    for one salon, so they cannot use a tenant-scoped repository. Callers must
    have set `app.bypass_rls` (see `db.session.bypass_tenant_scope`) — the same
    posture as the outbox dispatcher, and for the same reason.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_payable_before(self, moment: datetime, *, limit: int = 500) -> list[UUID]:
        stmt = (
            select(InvoiceRecord.id)
            .where(
                InvoiceRecord.status.in_([InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]),
                InvoiceRecord.due_at.is_not(None),
                InvoiceRecord.due_at <= moment,
            )
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def tenant_of(self, invoice_id: UUID) -> UUID | None:
        stmt = select(InvoiceRecord.tenant_id).where(InvoiceRecord.id == invoice_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_active_subscription_ids(self, *, limit: int = 1000) -> list[tuple[UUID, UUID]]:
        """`(tenant_id, business_id)` for everything the close must bill."""
        stmt = (
            select(SubscriptionRecord.tenant_id, SubscriptionRecord.business_id)
            .where(SubscriptionRecord.status != SubscriptionStatus.CANCELLED)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]


# --- payouts ---------------------------------------------------------------


def _payout_to_domain(record: PayoutRecord) -> Payout:
    return Payout(
        id=record.id,
        tenant_id=record.tenant_id,
        business_id=record.business_id,
        payout_date=record.payout_date,
        collected_amount=Money(amount=record.collected_amount, currency=record.currency),
        processing_fee=Money(amount=record.processing_fee, currency=record.currency),
        commission_netted=Money(amount=record.commission_netted, currency=record.currency),
        booking_ids=list(record.booking_ids),
        paid_at=record.paid_at,
    )


class PayoutRepository(TenantScopedRepository[PayoutRecord]):
    model = PayoutRecord

    async def add_payout(self, payout: Payout) -> PayoutRecord:
        record = PayoutRecord(
            id=payout.id,
            tenant_id=payout.tenant_id,
            business_id=payout.business_id,
            payout_date=payout.payout_date,
            collected_amount=payout.collected_amount.amount,
            processing_fee=payout.processing_fee.amount,
            commission_netted=payout.commission_netted.amount,
            net_amount=payout.net_amount,
            currency=payout.collected_amount.currency,
            booking_ids=list(payout.booking_ids),
        )
        self.add(record)
        await self.session.flush()
        return record

    async def find_for_date(self, business_id: UUID, day: date) -> PayoutRecord | None:
        stmt = self._scope(
            select(PayoutRecord).where(
                PayoutRecord.business_id == business_id, PayoutRecord.payout_date == day
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_business(
        self, business_id: UUID, *, limit: int = 30, offset: int = 0
    ) -> list[PayoutRecord]:
        stmt = (
            self._scope(select(PayoutRecord).where(PayoutRecord.business_id == business_id))
            .order_by(PayoutRecord.payout_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_between(
        self, business_id: UUID, *, date_from: date, date_to: date, limit: int
    ) -> list[Payout]:
        """Payouts dated inside a range, oldest first, as domain values."""
        stmt = (
            self._scope(
                select(PayoutRecord).where(
                    PayoutRecord.business_id == business_id,
                    PayoutRecord.payout_date >= date_from,
                    PayoutRecord.payout_date <= date_to,
                )
            )
            .order_by(PayoutRecord.payout_date)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_payout_to_domain(r) for r in rows]

    async def total_collected_on(self, business_id: UUID, day: date) -> Decimal:
        stmt = self._scope(
            select(func.coalesce(func.sum(PayoutRecord.collected_amount), 0)).where(
                PayoutRecord.business_id == business_id, PayoutRecord.payout_date == day
            )
        )
        return (await self.session.execute(stmt)).scalar_one()


__all__ = [
    "CommissionLineRepository",
    "FirstBookingRepository",
    "InvoiceRepository",
    "PayoutRepository",
    "SubscriptionRepository",
    "UnscopedInvoiceRepository",
]
