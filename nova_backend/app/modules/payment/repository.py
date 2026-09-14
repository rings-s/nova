"""payment · PERSISTENCE layer — queries and domain<->row mapping.

Layer rule: models + `app.db` + this module's domain. Must not import
service, router, or fastapi.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.values import Money, TimeRange, to_minor_units
from app.db.repository import BaseRepository, TenantScopedRepository
from app.modules.payment.domain import (
    SETTLED_STATUSES,
    Payment,
    PaymentFact,
    PaymentStatus,
    Refund,
)
from app.modules.payment.models import PaymentRecord, RefundRecord, WebhookEventRecord


def _to_domain(record: PaymentRecord) -> Payment:
    return Payment(
        id=record.id,
        tenant_id=record.tenant_id,
        booking_id=record.booking_id,
        amount=Money(amount=record.amount, currency=record.currency),
        status=record.status,
        gateway=record.gateway,
        gateway_payment_id=record.gateway_payment_id,
        webhook_verified=record.webhook_verified,
        failure_code=record.failure_code,
        refunded_amount=record.refunded_amount,
        captured_at=record.captured_at,
        refunded_at=record.refunded_at,
        created_at=record.created_at,
    )


def _apply(payment: Payment, record: PaymentRecord) -> PaymentRecord:
    record.status = payment.status
    record.gateway_payment_id = payment.gateway_payment_id
    record.webhook_verified = payment.webhook_verified
    record.failure_code = payment.failure_code
    record.refunded_amount = payment.refunded_amount
    record.captured_at = payment.captured_at
    record.refunded_at = payment.refunded_at
    return record


class PaymentRepository(TenantScopedRepository[PaymentRecord]):
    model = PaymentRecord

    async def get_payment(self, payment_id: UUID) -> Payment | None:
        record = await super().get(payment_id)
        return _to_domain(record) if record else None

    async def add_payment(self, payment: Payment) -> Payment:
        record = PaymentRecord(
            id=payment.id,
            tenant_id=payment.tenant_id,
            booking_id=payment.booking_id,
            amount=payment.amount.amount,
            currency=payment.amount.currency,
            status=payment.status,
            gateway=payment.gateway,
            gateway_payment_id=payment.gateway_payment_id,
        )
        self.add(record)
        await self.session.flush()
        return _to_domain(record)

    async def save(self, payment: Payment) -> Payment:
        record = await super().get(payment.id)
        if record is None:
            raise LookupError(f"Payment '{payment.id}' vanished before save.")
        _apply(payment, record)
        await self.session.flush()
        return _to_domain(record)

    async def get_by_gateway_id(self, gateway_payment_id: str) -> Payment | None:
        stmt = self._scope(
            select(PaymentRecord).where(PaymentRecord.gateway_payment_id == gateway_payment_id)
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def list_for_booking(self, booking_id: UUID) -> list[Payment]:
        stmt = self._scope(
            select(PaymentRecord).where(PaymentRecord.booking_id == booking_id)
        ).order_by(PaymentRecord.created_at)
        result = await self.session.execute(stmt)
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_facts(self, *, window: TimeRange, limit: int) -> list[PaymentFact]:
        """Payments captured or refunded in a window, as analytics facts.

        Only payments tied to a booking: analytics attributes money to a
        business through its booking, and a payment with no booking has none.
        """
        captured_in = and_(
            PaymentRecord.captured_at >= window.starts_at,
            PaymentRecord.captured_at < window.ends_at,
        )
        refunded_in = and_(
            PaymentRecord.refunded_at >= window.starts_at,
            PaymentRecord.refunded_at < window.ends_at,
        )
        stmt = (
            self._scope(
                select(
                    PaymentRecord.booking_id,
                    PaymentRecord.status,
                    PaymentRecord.amount,
                    PaymentRecord.refunded_amount,
                    PaymentRecord.currency,
                    PaymentRecord.captured_at,
                    PaymentRecord.refunded_at,
                ).where(PaymentRecord.booking_id.is_not(None), or_(captured_in, refunded_in))
            )
            .order_by(PaymentRecord.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            PaymentFact(
                booking_id=row.booking_id,
                status=row.status,
                amount_minor=to_minor_units(row.amount),
                refunded_minor=to_minor_units(row.refunded_amount),
                currency=row.currency,
                captured_at=row.captured_at,
                refunded_at=row.refunded_at,
            )
            for row in result
        ]

    def add_refund(self, refund: Refund, *, tenant_id: UUID) -> RefundRecord:
        record = RefundRecord(
            id=refund.id,
            tenant_id=tenant_id,
            payment_id=refund.payment_id,
            amount=refund.amount.amount,
            currency=refund.amount.currency,
            reason=refund.reason,
            gateway_refund_id=refund.gateway_refund_id,
        )
        self.session.add(record)
        return record

    async def list_refunds(self, payment_id: UUID) -> list[RefundRecord]:
        # `_scope` filters on `self.model` (PaymentRecord), so refunds get an
        # explicit tenant filter of their own rather than borrowing it.
        stmt = (
            select(RefundRecord)
            .where(
                RefundRecord.tenant_id == self.tenant_id,
                RefundRecord.payment_id == payment_id,
            )
            .order_by(RefundRecord.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class CapturedPayment(NamedTuple):
    """One prepayment the daily payout has to settle.

    A projection, not a `Payment`: the payout job needs four columns from a
    day's worth of rows across every tenant, and hydrating full domain objects
    to read four fields would be wasteful.
    """

    tenant_id: UUID
    booking_id: UUID
    collected: Decimal
    currency: str


class SettlementRepository:
    """Cross-tenant reads for the daily payout worker (docs/11 section 8).

    Unscoped by necessity, exactly like `WebhookEventRepository` below and the
    outbox dispatcher: payouts run for the whole platform at 04:00, not for one
    salon inside a request. Callers must have set `app.bypass_rls` first (see
    `db.session.bypass_tenant_scope`), or RLS correctly returns nothing.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_captured_between(
        self, *, start: datetime, end: datetime, limit: int = 5000
    ) -> list[CapturedPayment]:
        """Prepayments captured in `[start, end)`.

        `amount - refunded_amount` rather than `amount`: money refunded before
        the payout ran was never NOVA's to pass on, and paying it out would
        make the salon's ledger disagree with the gateway's.

        Only `SETTLED_STATUSES` — the module's own definition of "money has
        actually moved to us". An authorized-but-uncaptured payment has not.
        """
        collected = (PaymentRecord.amount - PaymentRecord.refunded_amount).label("collected")
        stmt = (
            select(
                PaymentRecord.tenant_id,
                PaymentRecord.booking_id,
                collected,
                PaymentRecord.currency,
            )
            .where(
                PaymentRecord.status.in_(tuple(SETTLED_STATUSES)),
                PaymentRecord.booking_id.is_not(None),
                PaymentRecord.captured_at.is_not(None),
                PaymentRecord.captured_at >= start,
                PaymentRecord.captured_at < end,
            )
            .order_by(PaymentRecord.captured_at)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [CapturedPayment(row[0], row[1], row[2], row[3]) for row in rows]


class WebhookEventRepository(BaseRepository[WebhookEventRecord]):
    """Unscoped by necessity: a webhook has no tenant until it is resolved."""

    model = WebhookEventRecord

    async def find(self, *, provider: str, external_event_id: str) -> WebhookEventRecord | None:
        stmt = select(WebhookEventRecord).where(
            WebhookEventRecord.provider == provider,
            WebhookEventRecord.external_event_id == external_event_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record(
        self,
        *,
        provider: str,
        external_event_id: str,
        event_type: str | None,
        payload: dict[str, Any],
        signature_verified: bool,
    ) -> WebhookEventRecord:
        event = WebhookEventRecord(
            provider=provider,
            external_event_id=external_event_id,
            event_type=event_type,
            payload=payload,
            signature_verified=signature_verified,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def mark_processed(
        self,
        event: WebhookEventRecord,
        *,
        now: datetime,
        tenant_id: UUID | None = None,
        error: str | None = None,
    ) -> None:
        event.processed_at = now
        event.tenant_id = tenant_id
        event.error = error
        await self.session.flush()

    async def find_payment_tenant(self, gateway_payment_id: str) -> UUID | None:
        """Which tenant a gateway payment belongs to.

        The one genuinely cross-tenant read in this module. A webhook arrives
        with only the gateway's own id, so the tenant has to be discovered
        before any tenant-scoped repository can be built. The caller must have
        called `bypass_tenant_scope` first, or RLS correctly returns nothing.
        """
        stmt = select(PaymentRecord.tenant_id).where(
            PaymentRecord.gateway_payment_id == gateway_payment_id
        )
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()


__all__ = [
    "CapturedPayment",
    "PaymentRepository",
    "PaymentStatus",
    "SettlementRepository",
    "WebhookEventRepository",
]
