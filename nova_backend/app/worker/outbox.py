"""The outbox dispatcher — the process that actually delivers domain events.

`core/events.publish_event` writes an event into `domain_events` in the same
transaction as the change it describes, which guarantees the event exists if
and only if the change committed. This file is the other half: it reads those
rows and runs the handlers.

Without it, events accumulate forever and nothing reacts — a booking is
confirmed and the customer is never told.

Delivery semantics are AT-LEAST-ONCE, and deliberately so. The alternative,
marking an event published before running its handlers, is at-most-once and
silently drops notifications when a worker dies mid-handler. Handlers are
therefore required to be idempotent (see `handlers.py`).

Concurrency: claiming uses `FOR UPDATE SKIP LOCKED` plus a lease. Several
dispatcher processes can run against one database — each claims a disjoint
batch, and a process that dies mid-batch releases its rows when the lease
expires rather than parking them forever.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.outbox import OutboxEvent, claim_pending_events
from app.db.session import bypass_tenant_scope, get_session_factory, set_tenant_scope
from app.worker.handlers import handlers_for

logger = logging.getLogger(__name__)

#: How long a claimed event is invisible to other dispatchers. Long enough for
#: a slow WhatsApp call, short enough that a crashed worker's events are
#: retried within a minute or two.
LEASE_SECONDS = 120


async def _claim_batch(
    session_factory: async_sessionmaker[AsyncSession], *, limit: int
) -> list[tuple]:
    """Takes a batch and leases it, in its own committed transaction.

    Returns plain tuples rather than ORM objects: the session that loaded them
    closes here, and each event is then processed in a *separate* transaction
    so one poisonous event cannot roll back its whole batch.
    """
    async with session_factory() as session:
        # The dispatcher legitimately crosses tenants — it is delivering events
        # for every salon on the platform. RLS would otherwise show it nothing.
        await bypass_tenant_scope(session)

        events = await claim_pending_events(session, limit=limit)
        leased = []
        lease_until = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)

        for event in events:
            event.available_at = lease_until
            leased.append((event.id, event.event_name, event.tenant_id, dict(event.payload)))

        await session.commit()
        return leased


async def _process_one(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    event_id,
    event_name: str,
    tenant_id,
    payload: dict,
) -> bool:
    """Runs every handler for one event, in one transaction. Returns success."""
    handlers = handlers_for(event_name)

    async with session_factory() as session:
        await bypass_tenant_scope(session)
        event = await session.get(OutboxEvent, event_id)
        if event is None or event.published_at is not None:
            # Already delivered by another dispatcher.
            return True

        if not handlers:
            # Nothing subscribes to this event. That is normal — most events
            # exist for audit and future consumers — so mark it published
            # rather than retrying it forever.
            event.mark_published()
            await session.commit()
            return True

        try:
            if tenant_id is not None:
                # Handlers run against tenant-scoped services, so the
                # connection is scoped the same way a request would be.
                await set_tenant_scope(session, tenant_id)

            for handler in handlers:
                await handler(session, tenant_id, payload)

            event.mark_published()
            await session.commit()
            return True

        except Exception as exc:
            await session.rollback()
            logger.exception(
                "outbox_handler_failed",
                extra={"event_name": event_name, "event_id": str(event_id)},
            )
            # Reload in a clean transaction: the rollback above discarded the
            # instance's state along with the handler's work.
            async with session_factory() as retry_session:
                await bypass_tenant_scope(retry_session)
                failed = await retry_session.get(OutboxEvent, event_id)
                if failed is not None:
                    failed.schedule_retry(str(exc))
                    if failed.is_dead_lettered:
                        logger.error(
                            "outbox_event_dead_lettered",
                            extra={
                                "event_name": event_name,
                                "event_id": str(event_id),
                                "attempts": failed.attempts,
                            },
                        )
                await retry_session.commit()
            return False


async def dispatch_pending_events(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    limit: int = 100,
) -> dict[str, int]:
    """Delivers one batch. Returns counts for logging and tests."""
    factory = session_factory or get_session_factory()

    claimed = await _claim_batch(factory, limit=limit)
    if not claimed:
        return {"claimed": 0, "delivered": 0, "failed": 0}

    delivered = 0
    failed = 0
    for event_id, event_name, tenant_id, payload in claimed:
        ok = await _process_one(
            factory,
            event_id=event_id,
            event_name=event_name,
            tenant_id=tenant_id,
            payload=payload,
        )
        delivered += int(ok)
        failed += int(not ok)

    result = {"claimed": len(claimed), "delivered": delivered, "failed": failed}
    logger.info("outbox_batch_dispatched", extra=result)
    return result
