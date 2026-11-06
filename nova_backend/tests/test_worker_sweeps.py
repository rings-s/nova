"""The cross-tenant questions the worker's cron jobs ask, through each module's sweeper.

The jobs in `app/worker/arq_worker.py` only wire these up: read across tenants
with `bypass_tenant_scope`, then act per tenant. Rows are seeded as the owner
and the sweepers run as `nova_app` with the bypass on, as the worker does.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update

from app.db.session import bypass_tenant_scope
from app.modules.booking.dependencies import build_slot_hold_sweeper
from app.modules.booking.models import SlotHoldRecord
from app.modules.call_center.dependencies import build_call_sweeper
from app.modules.call_center.domain import CallDirection, CallOutcome, CallPurpose, CallStatus
from app.modules.call_center.models import PhoneLineRecord, VoiceCallRecord
from app.modules.notification.dependencies import build_notification_sweeper
from app.modules.notification.domain import MessageTemplate, NotificationStatus
from app.modules.notification.models import NotificationRecord
from app.modules.queue.dependencies import build_queue_sweeper, build_ticket_sweeper
from app.modules.queue.domain import QueueEntryStatus, TicketStatus
from app.modules.queue.models import QueueEntryRecord, QueueRecord, TicketRecord

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


async def test_the_queue_sweep_cancels_only_unserved_entries_from_before_the_cutoff(
    db_session, as_owner, tenant_factory
):
    tenant = await tenant_factory()
    queue = QueueRecord(tenant_id=tenant.id, location_id=uuid4())
    async with as_owner():
        db_session.add(queue)
        await db_session.flush()

    def entry(position, *, joined_at, status=QueueEntryStatus.WAITING) -> QueueEntryRecord:
        return QueueEntryRecord(
            tenant_id=tenant.id,
            queue_id=queue.id,
            location_id=queue.location_id,
            customer_id=uuid4(),
            service_id=uuid4(),
            status=status,
            position=position,
            joined_at=joined_at,
        )

    yesterday = NOW - timedelta(days=1)
    stale = [
        entry(1, joined_at=yesterday),
        entry(2, joined_at=yesterday, status=QueueEntryStatus.CALLED),
        entry(3, joined_at=yesterday, status=QueueEntryStatus.MISSED),
    ]
    in_the_chair = entry(4, joined_at=yesterday, status=QueueEntryStatus.IN_SERVICE)
    today = entry(5, joined_at=NOW)
    async with as_owner():
        db_session.add_all([*stale, in_the_chair, today])
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    cancelled = await build_queue_sweeper(db_session).cancel_stale(
        joined_before=NOW - timedelta(hours=14)
    )

    statuses = dict(
        (await db_session.execute(select(QueueEntryRecord.id, QueueEntryRecord.status)))
        .tuples()
        .all()
    )
    assert cancelled == 3
    assert all(statuses[e.id] is QueueEntryStatus.CANCELLED for e in stale)
    assert statuses[in_the_chair.id] is QueueEntryStatus.IN_SERVICE
    assert statuses[today.id] is QueueEntryStatus.WAITING


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


async def test_the_ticket_sweep_keeps_going_past_one_batch(db_session, as_owner, tenant_factory):
    tenant = await tenant_factory()
    async with as_owner():
        db_session.add_all(
            [_ticket(tenant.id, expires_at=NOW - timedelta(minutes=1)) for _ in range(5)]
        )
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    expired = await build_ticket_sweeper(db_session).expire_stale(now=NOW, limit=2)

    assert expired == 5
    remaining = (
        await db_session.execute(
            select(TicketRecord).where(TicketRecord.status == TicketStatus.ACTIVE)
        )
    ).all()
    assert remaining == []


async def test_the_hold_purge_keeps_going_past_one_batch(db_session, as_owner, tenant_factory):
    tenant = await tenant_factory()
    async with as_owner():
        db_session.add_all([_hold(tenant.id, expires_at=NOW - timedelta(days=2)) for _ in range(5)])
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    purged = await build_slot_hold_sweeper(db_session).purge_expired_before(
        NOW - timedelta(days=1), limit=2
    )

    assert purged == 5
    assert (await db_session.execute(select(SlotHoldRecord))).all() == []


def _call(tenant_id, line_id, *, started_at) -> VoiceCallRecord:
    return VoiceCallRecord(
        tenant_id=tenant_id,
        line_id=line_id,
        business_id=uuid4(),
        direction=CallDirection.INBOUND,
        purpose=CallPurpose.CONVERSATION,
        status=CallStatus.ENDED,
        outcome=CallOutcome.BOOKED,
        caller_e164="+966500000777",
        turns=4,
        started_at=started_at,
        code_hash="0" * 64,
        last_answer_key="1" * 64,
        last_reply="أبشروا، موعدكم بكرة الساعة أربع العصر يا نورة.",
    )


async def test_the_call_scrub_clears_who_called_from_old_calls_in_every_tenant(
    db_session, as_owner, tenant_factory
):
    first, second = await tenant_factory(), await tenant_factory()
    lines = [
        PhoneLineRecord(
            tenant_id=t.id,
            business_id=uuid4(),
            number_e164=f"+9668{uuid4().int % 10**8:08d}",
            locale="ar",
            agent_name="call_center_agent",
            is_active=True,
            token_version=0,
        )
        for t in (first, second)
    ]
    async with as_owner():
        db_session.add_all(lines)
        await db_session.flush()
        old = [
            _call(line.tenant_id, line.id, started_at=NOW - timedelta(days=91)) for line in lines
        ]
        recent = _call(first.id, lines[0].id, started_at=NOW - timedelta(days=1))
        db_session.add_all([*old, recent])
        await db_session.flush()

    await bypass_tenant_scope(db_session)
    scrubbed = await build_call_sweeper(db_session).scrub_started_before(NOW - timedelta(days=90))

    assert scrubbed >= 2
    rows = {
        row.id: row
        for row in (
            await db_session.execute(
                select(VoiceCallRecord).execution_options(populate_existing=True)
            )
        ).scalars()
    }
    for call in old:
        row = rows[call.id]
        assert (row.caller_e164, row.last_reply, row.last_answer_key, row.code_hash) == (
            None,
            None,
            None,
            None,
        )
        # The call log keeps what the call achieved.
        assert row.outcome is CallOutcome.BOOKED and row.turns == 4
    assert rows[recent.id].caller_e164 == "+966500000777"
    assert rows[recent.id].last_reply is not None


async def test_a_call_the_caller_hung_up_on_is_ended_once_its_links_expire(
    db_session, as_owner, tenant_factory
):
    tenant = await tenant_factory()
    line = PhoneLineRecord(
        id=uuid4(),
        tenant_id=tenant.id,
        business_id=uuid4(),
        number_e164=f"+9668{uuid4().int % 10**8:08d}",
        locale="ar",
        agent_name="call_center_agent",
        is_active=True,
        token_version=0,
    )

    def live(*, purpose=CallPurpose.CONVERSATION, outcome=None, turns=3) -> VoiceCallRecord:
        call = _call(tenant.id, line.id, started_at=NOW - timedelta(hours=5))
        call.status, call.purpose, call.outcome, call.turns = (
            CallStatus.IN_PROGRESS,
            purpose,
            outcome,
            turns,
        )
        return call

    hung_up = live()
    booked_then_gone = live(outcome=CallOutcome.BOOKED)
    unanswered_reminder = live(purpose=CallPurpose.REMINDER, turns=0)
    still_talking = live()
    async with as_owner():
        db_session.add(line)
        await db_session.flush()
        db_session.add_all([hung_up, booked_then_gone, unanswered_reminder, still_talking])
        await db_session.flush()
        # The last turn: three hours ago for all but one, a minute ago for it.
        last_turn = NOW - timedelta(hours=3)
        await db_session.execute(
            update(VoiceCallRecord)
            .where(VoiceCallRecord.tenant_id == tenant.id)
            .values(updated_at=last_turn)
        )
        await db_session.execute(
            update(VoiceCallRecord)
            .where(VoiceCallRecord.id == still_talking.id)
            .values(updated_at=NOW - timedelta(minutes=1))
        )

    await bypass_tenant_scope(db_session)
    ended = await build_call_sweeper(db_session).end_abandoned(now=NOW)

    assert ended >= 3
    rows = {
        row.id: row
        for row in (
            await db_session.execute(
                select(VoiceCallRecord).execution_options(populate_existing=True)
            )
        ).scalars()
    }
    for call in (hung_up, booked_then_gone, unanswered_reminder):
        assert rows[call.id].status is CallStatus.ENDED
        assert rows[call.id].ended_at == last_turn, "it ended at its last turn"
    assert rows[hung_up.id].outcome is None, "questions only"
    assert rows[booked_then_gone.id].outcome is CallOutcome.BOOKED
    assert rows[unanswered_reminder.id].outcome is CallOutcome.NO_ANSWER
    assert rows[still_talking.id].status is CallStatus.IN_PROGRESS
    assert rows[still_talking.id].ended_at is None
