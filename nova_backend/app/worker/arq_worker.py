"""Background jobs.

Two kinds of work run here, and they are here for the same reason: neither
belongs on a request path.

  - The OUTBOX DISPATCHER delivers domain events. A WhatsApp call inside a
    booking request would put a third party's latency on the customer's tap.
  - MAINTENANCE jobs sweep expired state — tickets, slot holds, deleted media —
    which nobody's request should ever pay for.

Everything is scheduled by cron rather than triggered, so a job that fails
simply runs again next tick.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.idempotency import IdempotencyKey
from app.core.logging import configure_logging
from app.core.values import Money
from app.db.session import (
    bypass_tenant_scope,
    get_engine,
    get_session_factory,
    set_tenant_scope,
)
from app.modules.media.models import MediaAssetRecord
from app.modules.notification.dependencies import build_notification_service
from app.modules.notification.domain import NotificationStatus
from app.modules.notification.models import NotificationRecord
from app.modules.payment.repository import CapturedPayment, SettlementRepository
from app.worker.outbox import dispatch_pending_events

logger = logging.getLogger(__name__)

_settings = get_settings()


async def ping(ctx: dict) -> str:
    """Trivial task proving the worker is wired to Redis correctly."""
    return "pong"


async def dispatch_outbox(ctx: dict) -> dict[str, int]:
    """Delivers pending domain events.

    The most important job in this file: without it, every event ever published
    sits in `domain_events` unread and no customer is ever notified of
    anything.
    """
    return await dispatch_pending_events(limit=200)


async def deliver_pending_notifications(ctx: dict) -> int:
    """Sends every message whose time has come.

    This is the job that turns a written notification into a sent one, and for
    the whole life of the codebase it delivered nothing. It filtered
    `scheduled_for IS NOT NULL`, which only marketing messages held by quiet
    hours ever satisfied; every booking confirmation, queue call and payment
    receipt sat PENDING forever.

    `scheduled_for` now means "not before" and is always set, so one comparison
    covers all three populations: send-now, held by quiet hours, and waiting
    out a retry backoff.

    The claim query is cross-tenant and therefore cannot use the tenant-scoped
    `NotificationRepository.list_due`; it mirrors that predicate deliberately.
    Change one and change the other.
    """
    now = datetime.now(UTC)
    session_factory = get_session_factory()
    sent = 0

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        stmt = (
            select(NotificationRecord)
            .where(
                NotificationRecord.status == NotificationStatus.PENDING,
                NotificationRecord.scheduled_for <= now,
            )
            # Oldest first: after an outage, the customer who has been waiting
            # longest hears back first.
            .order_by(NotificationRecord.created_at)
            .limit(200)
        )
        result = await session.execute(stmt)
        due = list(result.scalars().all())

    for record in due:
        try:
            async with session_factory() as session:
                # Load-bearing. `notifications` and `customers` are both under
                # FORCE RLS, and only the *read* session above bypassed it. A
                # write session with no scope set matches zero rows, so
                # `deliver` would raise NotificationNotFoundError on the first
                # record and take the whole sweep down with it.
                await set_tenant_scope(session, record.tenant_id)
                service = build_notification_service(session, record.tenant_id)
                await service.deliver(record.id, now=now)
                await session.commit()
                sent += 1
        except Exception:
            # One salon's bad record must not stop every other salon being
            # notified — the same isolation `close_monthly_invoices` uses.
            logger.exception(
                "notification_delivery_failed",
                extra={
                    "notification_id": str(record.id),
                    "tenant_id": str(record.tenant_id),
                },
            )

    if sent:
        logger.info("notifications_delivered", extra={"count": sent})
    return sent


async def expire_stale_tickets(ctx: dict) -> int:
    """Moves ACTIVE tickets past their expiry to EXPIRED.

    Cosmetic for security — `Ticket.is_redeemable` already refuses an expired
    ticket at scan time — but it keeps reception's screen honest rather than
    showing a wall of tickets that look valid and are not.
    """
    from app.modules.queue.domain import TicketStatus
    from app.modules.queue.models import TicketRecord

    now = datetime.now(UTC)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        stmt = (
            select(TicketRecord)
            .where(
                TicketRecord.status == TicketStatus.ACTIVE,
                TicketRecord.expires_at <= now,
            )
            .limit(500)
        )
        result = await session.execute(stmt)
        stale = list(result.scalars().all())

        for ticket in stale:
            ticket.status = TicketStatus.EXPIRED
        await session.commit()

    if stale:
        logger.info("tickets_expired", extra={"count": len(stale)})
    return len(stale)


async def purge_expired_slot_holds(ctx: dict) -> int:
    """Deletes slot holds that expired more than a day ago.

    Expiry is by timestamp, so an expired hold already stops blocking
    availability the moment it lapses. This just stops the table growing
    forever, and keeps a day of history for "why did my slot disappear".
    """
    from app.modules.booking.models import SlotHoldRecord

    cutoff = datetime.now(UTC) - timedelta(days=1)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        result = await session.execute(
            select(SlotHoldRecord).where(SlotHoldRecord.expires_at < cutoff).limit(1000)
        )
        stale = list(result.scalars().all())
        for hold in stale:
            await session.delete(hold)
        await session.commit()

    return len(stale)


async def purge_expired_idempotency_keys(ctx: dict) -> int:
    """Idempotency keys have a 24-hour TTL; this is what enforces it."""
    now = datetime.now(UTC)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        result = await session.execute(
            select(IdempotencyKey).where(IdempotencyKey.expires_at < now).limit(1000)
        )
        stale = list(result.scalars().all())
        for key in stale:
            await session.delete(key)
        await session.commit()

    return len(stale)


async def abandon_stale_media_uploads(ctx: dict) -> int:
    """Soft-deletes assets whose upload window closed with nothing uploaded.

    These are rows pointing at bytes that were never written — a business's
    media list would otherwise fill with permanently-loading placeholders.
    """
    now = datetime.now(UTC)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        result = await session.execute(
            select(MediaAssetRecord)
            .where(
                MediaAssetRecord.is_ready.is_(False),
                MediaAssetRecord.is_deleted.is_(False),
                MediaAssetRecord.upload_expires_at < now,
            )
            .limit(500)
        )
        stale = list(result.scalars().all())
        for asset in stale:
            asset.mark_deleted(now=now)
        await session.commit()

    return len(stale)


async def close_monthly_invoices(ctx: dict) -> int:
    """Issues one invoice per business for the month just ended.

    docs/11 section 7 step 3: "On the 1st of each month an ARQ worker closes
    the previous period and issues one Invoice per tenant."

    Idempotent twice over — `close_period` returns the existing invoice for a
    period already closed, and a UNIQUE index on (business_id, period_start)
    catches two workers racing. So a re-run, a retry, or a manual invocation
    costs nothing.

    Each business commits in its own transaction: one salon with corrupt data
    must not stop every other salon on the platform being invoiced.
    """
    from app.modules.billing.dependencies import build_billing_service
    from app.modules.billing.domain import BillingPeriod
    from app.modules.billing.repository import UnscopedInvoiceRepository

    now = datetime.now(UTC)
    period = BillingPeriod.previous_month(now.date())
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        targets = await UnscopedInvoiceRepository(session).list_active_subscription_ids()

    issued = 0
    for tenant_id, business_id in targets:
        try:
            async with session_factory() as session:
                await set_tenant_scope(session, tenant_id)
                billing = build_billing_service(session, tenant_id)
                await billing.close_period(business_id=business_id, period=period, now=now)
                await session.commit()
                issued += 1
        except Exception:
            logger.exception(
                "monthly_close_failed",
                extra={"tenant_id": str(tenant_id), "business_id": str(business_id)},
            )

    logger.info(
        "monthly_invoices_closed",
        extra={"count": issued, "period_start": period.period_start.isoformat()},
    )
    return issued


@dataclass
class _DayTakings:
    """What one business collected on one day, as the payout needs it."""

    currency: str
    collected: Decimal = Decimal("0.00")
    booking_ids: list[UUID] = field(default_factory=list)


def _group_takings(
    payments: Sequence[CapturedPayment], business_of: dict[UUID, UUID]
) -> dict[UUID, _DayTakings]:
    """Turns a day of payments into one settlement per business.

    Pure, so the arithmetic that decides what a salon is paid can be tested
    without a database or a worker.

    Two rows get dropped rather than guessed at, both logged:

      - a payment whose booking is not in `business_of`. Either it belongs to
        another tenant or the booking is gone; paying somebody for it means
        guessing who.
      - a payment in a second currency for the same business. A payout row
        carries one currency, and silently adding halalas to fils would corrupt
        the figure the salon reconciles against.
    """
    takings: dict[UUID, _DayTakings] = {}
    for payment in payments:
        business_id = business_of.get(payment.booking_id)
        if business_id is None:
            logger.warning(
                "payout_booking_unresolved", extra={"booking_id": str(payment.booking_id)}
            )
            continue

        day = takings.setdefault(business_id, _DayTakings(currency=payment.currency))
        if payment.currency != day.currency:
            logger.warning(
                "payout_currency_mismatch",
                extra={
                    "business_id": str(business_id),
                    "expected": day.currency,
                    "found": payment.currency,
                },
            )
            continue

        day.collected += payment.collected
        day.booking_ids.append(payment.booking_id)
    return takings


async def settle_daily_payouts(ctx: dict) -> int:
    """Pays each business yesterday's takings (docs/11 section 8).

        payout = collected - 2.5% processing - commission due

    Runs on yesterday rather than today because a day is only settleable once
    it is over: a capture at 23:50 has to land in the same payout as one at
    09:00, and a job running against the current day would split them.

    04:00 rather than midnight for the same reason `close_monthly_invoices`
    runs at 02:00 — the refund and completion events from late last night need
    to have made it through the outbox first, so that a booking refunded at
    23:55 is not paid out at 00:01 and clawed back afterwards.

    Idempotent per `(business_id, payout_date)`: `settle_payout` returns None
    for a day already settled, and a UNIQUE index catches two workers racing.
    Each tenant commits separately so one salon's bad data cannot stop the
    platform being paid.
    """
    from app.modules.billing.dependencies import build_billing_service
    from app.modules.booking.dependencies import build_booking_service

    now = datetime.now(UTC)
    payout_date = now.date() - timedelta(days=1)
    start = datetime.combine(payout_date, time.min, tzinfo=UTC)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        captured = await SettlementRepository(session).list_captured_between(
            start=start, end=start + timedelta(days=1)
        )

    by_tenant: dict[UUID, list[CapturedPayment]] = defaultdict(list)
    for payment in captured:
        by_tenant[payment.tenant_id].append(payment)

    settled = 0
    for tenant_id, payments in by_tenant.items():
        try:
            async with session_factory() as session:
                await set_tenant_scope(session, tenant_id)

                bookings = build_booking_service(session, tenant_id)
                business_of = await bookings.businesses_for([p.booking_id for p in payments])

                billing = build_billing_service(session, tenant_id)
                for business_id, day in _group_takings(payments, business_of).items():
                    payout = await billing.settle_payout(
                        business_id=business_id,
                        payout_date=payout_date,
                        collected=Money(amount=day.collected, currency=day.currency),
                        booking_ids=day.booking_ids,
                        now=now,
                    )
                    if payout is not None:
                        settled += 1
                await session.commit()
        except Exception:
            logger.exception("payout_failed", extra={"tenant_id": str(tenant_id)})

    logger.info("payouts_settled", extra={"count": settled, "payout_date": payout_date.isoformat()})
    return settled


async def advance_dunning(ctx: dict) -> int:
    """Chases unpaid invoices on the docs/11 section 7 step 5 schedule.

    Retries land on days 3, 7 and 14 past due; day 21 hides the marketplace
    listing. Nothing here touches the calendar, the queue, or a single existing
    booking — docs/11 is emphatic that non-payment removes NOVA's marketing and
    never the salon's operations.
    """
    from app.modules.billing.dependencies import build_billing_service
    from app.modules.billing.repository import UnscopedInvoiceRepository

    now = datetime.now(UTC)
    session_factory = get_session_factory()

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        repo = UnscopedInvoiceRepository(session)
        invoice_ids = await repo.list_payable_before(now)
        tenants = {i: await repo.tenant_of(i) for i in invoice_ids}

    chased = 0
    for invoice_id, tenant_id in tenants.items():
        if tenant_id is None:
            continue
        try:
            async with session_factory() as session:
                await set_tenant_scope(session, tenant_id)
                billing = build_billing_service(session, tenant_id)
                await billing.advance_dunning(invoice_id, now=now)
                await session.commit()
                chased += 1
        except Exception:
            logger.exception("dunning_failed", extra={"invoice_id": str(invoice_id)})

    if chased:
        logger.info("dunning_advanced", extra={"count": chased})
    return chased


async def startup(ctx: dict) -> None:
    configure_logging()
    logger.info("worker_started")


async def shutdown(ctx: dict) -> None:
    await get_engine().dispose()


class WorkerSettings:
    functions = [
        ping,
        dispatch_outbox,
        deliver_pending_notifications,
        expire_stale_tickets,
        purge_expired_slot_holds,
        purge_expired_idempotency_keys,
        abandon_stale_media_uploads,
        close_monthly_invoices,
        settle_daily_payouts,
        advance_dunning,
    ]

    cron_jobs = [
        # Every 10 seconds. This is the delivery latency a customer feels
        # between paying and receiving their confirmation, so it is the one
        # schedule here worth keeping tight.
        cron(dispatch_outbox, second={0, 10, 20, 30, 40, 50}, run_at_startup=True),
        # Every 30 seconds. The five-minute schedule this replaces was chosen
        # when the job only released quiet-hours marketing, where lateness is
        # free. It is now the delay a customer feels between booking and being
        # told they are booked, so it belongs next to `dispatch_outbox` in
        # cadence rather than next to the nightly sweeps.
        cron(deliver_pending_notifications, second={0, 30}),
        cron(expire_stale_tickets, minute={7, 37}),
        cron(purge_expired_slot_holds, hour={3}, minute={11}),
        cron(purge_expired_idempotency_keys, hour={3}, minute={21}),
        cron(abandon_stale_media_uploads, minute={17, 47}),
        # docs/11 section 7 step 3: the 1st of each month. 02:00 rather than
        # midnight so a booking completed late on the last night of the month
        # has had its outbox event delivered and its commission accrued before
        # the period closes over it.
        cron(close_monthly_invoices, day={1}, hour={2}, minute={0}),
        # docs/11 section 8: "Payouts run daily". 04:00 settles the day that
        # just ended, once its refunds and completions have cleared the outbox.
        cron(settle_daily_payouts, hour={4}, minute={0}),
        # Daily. The retry schedule lives in the domain (days 3, 7, 14 past
        # due); this job only asks "is anything owing?" and lets
        # `advance_dunning` decide whether today is a retry day.
        cron(advance_dunning, hour={9}, minute={0}),
    ]

    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(str(_settings.redis_url))
