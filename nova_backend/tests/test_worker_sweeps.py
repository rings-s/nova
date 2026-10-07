"""The cross-tenant questions the worker's cron jobs ask, through each module's sweeper.

The jobs in `app/worker/arq_worker.py` only wire these up: read across tenants
with `bypass_tenant_scope`, then act per tenant. Rows are seeded as the owner
and the sweepers run as `nova_app` with the bypass on, as the worker does.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.db.session import bypass_tenant_scope
from app.modules.booking.dependencies import build_slot_hold_sweeper
from app.modules.booking.models import SlotHoldRecord
from app.modules.notification.dependencies import build_notification_sweeper
from app.modules.notification.domain import MessageTemplate, NotificationStatus
from app.modules.notification.models import NotificationRecord
from app.modules.queue.dependencies import build_ticket_sweeper
from app.modules.queue.domain import TicketStatus
from app.modules.queue.models import TicketRecord

NOW = datetime.now(UTC)


def _ticket(tenant_id, *, expires_at, status=TicketStatus.ACTIVE) -> TicketRecord:
    return TicketRecord(
        tenant_id=tenant_id,
        booking_id=uuid4(),
        ticket_code=f"T-{uuid4().hex[:8]}",
        qr_token_hash=uuid4().hex,
        status=status,
        expires_at=expires_at,
    )


def _hold(tenant_id, *, expires_at) -> SlotHoldRecord:
    return SlotHoldRecord(
        tenant_id=tenant_id,
        provider_id=uuid4(),
        service_id=uuid4(),
        location_id=uuid4(),
        starts_at=NOW,
        ends_at=NOW + timedelta(hours=1),
        hold_token=uuid4().hex,
        expires_at=expires_at,
    )


def _notification(tenant_id, *, scheduled_for, status=NotificationStatus.PENDING):
    return NotificationRecord(
        tenant_id=tenant_id,
        customer_id=uuid4(),
        template=next(iter(MessageTemplate)),
        status=status,
        payload={},
        dedupe_key=uuid4().hex,
        scheduled_for=scheduled_for,
    )


async def test_the_ticket_sweep_expires_only_lapsed_active_tickets_in_every_tenant(
    db_session, as_owner, tenant_factory
):
    first, second = await tenant_factory(), await tenant_factory()
    lapsed = [_ticket(t.id, expires_at=NOW - timedelta(minutes=1)) for t in (first, second)]
    current = _ticket(first.id, expires_at=NOW + timedelta(hours=1))
    redeemed = _ticket(
        first.id, expires_at=NOW - timedelta(minutes=1), status=TicketStatus.REDEEMED
    )
    async with as_owner():
        db_session.add_all([*lapsed, current, redeemed])
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    await build_ticket_sweeper(db_session).expire_stale(now=NOW)

    statuses = dict(
        (await db_session.execute(select(TicketRecord.id, TicketRecord.status))).tuples().all()
    )
    assert all(statuses[t.id] is TicketStatus.EXPIRED for t in lapsed)
    assert statuses[current.id] is TicketStatus.ACTIVE
    assert statuses[redeemed.id] is TicketStatus.REDEEMED


async def test_the_hold_purge_deletes_only_holds_expired_before_the_cutoff(
    db_session, as_owner, tenant_factory
):
    tenant = await tenant_factory()
    old = _hold(tenant.id, expires_at=NOW - timedelta(days=2))
    recent = _hold(tenant.id, expires_at=NOW - timedelta(hours=1))
    async with as_owner():
        db_session.add_all([old, recent])
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    purged = await build_slot_hold_sweeper(db_session).purge_expired_before(NOW - timedelta(days=1))

    remaining = set((await db_session.execute(select(SlotHoldRecord.id))).scalars().all())
    assert purged >= 1
    assert old.id not in remaining
    assert recent.id in remaining


async def test_the_delivery_sweep_lists_due_pending_messages_across_tenants(
    db_session, as_owner, tenant_factory
):
    first, second = await tenant_factory(), await tenant_factory()
    due = [_notification(t.id, scheduled_for=NOW - timedelta(minutes=1)) for t in (first, second)]
    later = _notification(first.id, scheduled_for=NOW + timedelta(hours=1))
    sent = _notification(
        first.id, scheduled_for=NOW - timedelta(minutes=1), status=NotificationStatus.SENT
    )
    async with as_owner():
        db_session.add_all([*due, later, sent])
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    listed = set(await build_notification_sweeper(db_session).list_due(now=NOW))

    assert {(n.id, n.tenant_id) for n in due} <= listed
    assert all(n.id not in {i for i, _ in listed} for n in (later, sent))
