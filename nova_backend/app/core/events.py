"""Domain event publishing via a transactional outbox.

The previous implementation logged the event and returned. That is
fire-and-forget, and it was wrong in both directions:

  - If the transaction later rolled back, the event had already escaped. A
    "BookingConfirmed" WhatsApp message could be sent for a booking that never
    existed.
  - If the process died between commit and delivery, the event was simply lost
    with nothing to replay.

Now `publish_event` INSERTs into the `domain_events` table using the caller's
session, so the event commits atomically with the business change it describes.
Either both land or neither does. A separate dispatcher (see
`app/worker/outbox.py`) delivers committed events afterwards, retrying until it
succeeds — at-least-once delivery, which is why handlers must be idempotent.

Docs: 08-Database-Models-and-Persistence.md section 16.
"""

import logging
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainEvent:
    """Base for every module's domain events."""

    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        kw_only=True,
    )

    @property
    def name(self) -> str:
        return type(self).__name__

    def to_dict(self) -> dict[str, Any]:
        if not is_dataclass(self):
            raise TypeError(f"{self.name} must be a dataclass.")
        return asdict(self)


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


async def publish_event(session: AsyncSession, event: DomainEvent) -> None:
    """Records an event in the outbox, inside the caller's transaction.

    Deliberately takes the session: an event that is not part of the business
    transaction cannot be trusted. There is no way to publish "outside" a
    transaction with this signature, which is the point.

    Does NOT flush — the caller's existing flush/commit carries it, so
    publishing never forces extra round trips.
    """
    # Imported here rather than at module scope: app.db.base imports nothing
    # from core, but the models module pulls in SQLAlchemy metadata, and a
    # top-level import would make core depend on the ORM for every consumer.
    from app.db.outbox import OutboxEvent

    payload = _json_safe(event.to_dict())
    payload.pop("occurred_at", None)

    session.add(
        OutboxEvent(
            event_name=event.name,
            tenant_id=getattr(event, "tenant_id", None),
            payload=payload,
            occurred_at=event.occurred_at,
        )
    )
    logger.debug("event_enqueued", extra={"event": event.name})
