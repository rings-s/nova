"""queue · PERSISTENCE layer — queries and domain<->row mapping.

Layer rule: models + `app.db` + this module's domain. Must not import
service, router, or fastapi.

`QueueEntryRecord` and `TicketRecord` never escape this file; callers hand in
and get back `domain.QueueEntry` and `domain.Ticket`.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text

from app.core.values import TimeRange
from app.db.repository import TenantScopedRepository
from app.modules.queue.domain import (
    ACTIVE_QUEUE_STATUSES,
    QueueEntry,
    QueueEntryFact,
    QueueEntrySource,
    QueueEntryStatus,
    Ticket,
    TicketStatus,
)
from app.modules.queue.models import QueueEntryRecord, QueueRecord, TicketRecord


def _entry_to_domain(record: QueueEntryRecord) -> QueueEntry:
    return QueueEntry(
        id=record.id,
        tenant_id=record.tenant_id,
        queue_id=record.queue_id,
        location_id=record.location_id,
        customer_id=record.customer_id,
        service_id=record.service_id,
        provider_id=record.provider_id,
        status=record.status,
        position=record.position,
        source=record.source,
        party_size=record.party_size,
        booking_id=record.booking_id,
        joined_at=record.joined_at,
        scheduled_for=record.scheduled_for,
        called_at=record.called_at,
        checked_in_at=record.checked_in_at,
        completed_at=record.completed_at,
    )


def _apply_entry(entry: QueueEntry, record: QueueEntryRecord) -> QueueEntryRecord:
    record.status = entry.status
    record.position = entry.position
    record.provider_id = entry.provider_id
    record.called_at = entry.called_at
    record.checked_in_at = entry.checked_in_at
    record.completed_at = entry.completed_at
    return record


def _ticket_to_domain(record: TicketRecord) -> Ticket:
    return Ticket(
        id=record.id,
        tenant_id=record.tenant_id,
        ticket_code=record.ticket_code,
        qr_token_hash=record.qr_token_hash,
        status=record.status,
        expires_at=record.expires_at,
        booking_id=record.booking_id,
        queue_entry_id=record.queue_entry_id,
        redeemed_at=record.redeemed_at,
        revoked_at=record.revoked_at,
    )


class QueueRepository(TenantScopedRepository[QueueRecord]):
    model = QueueRecord

    async def get_for_location(self, location_id: UUID) -> QueueRecord | None:
        stmt = self._scope(
            select(QueueRecord).where(
                QueueRecord.location_id == location_id,
                QueueRecord.is_deleted.is_(False),
            )
        )
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def list_for_location(self, location_id: UUID) -> list[QueueRecord]:
        stmt = self._scope(
            select(QueueRecord).where(
                QueueRecord.location_id == location_id,
                QueueRecord.is_deleted.is_(False),
            )
        ).order_by(QueueRecord.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def lock_queue(self, queue_id: UUID) -> None:
        """Serialises position assignment within a transaction.

        Two people joining the same queue at the same instant would otherwise
        both read the same `max(position)` and both take it — and the unique
        constraint on (queue_id, position) would turn the second into a 500.
        """
        queue_key = queue_id.int % (2**31)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:scope, :queue_key)"),
            # A distinct scope constant from the booking lock, so a queue and a
            # provider calendar never collide on the same lock pair.
            {"scope": 77, "queue_key": queue_key},
        )


class QueueEntryRepository(TenantScopedRepository[QueueEntryRecord]):
    model = QueueEntryRecord

    async def get_entry(self, entry_id: UUID) -> QueueEntry | None:
        record = await super().get(entry_id)
        return _entry_to_domain(record) if record else None

    async def add_entry(self, entry: QueueEntry) -> QueueEntry:
        record = QueueEntryRecord(
            id=entry.id,
            tenant_id=entry.tenant_id,
            queue_id=entry.queue_id,
            location_id=entry.location_id,
            customer_id=entry.customer_id,
            service_id=entry.service_id,
            provider_id=entry.provider_id,
            booking_id=entry.booking_id,
            scheduled_for=entry.scheduled_for,
            status=entry.status,
            source=entry.source,
            position=entry.position,
            party_size=entry.party_size,
            joined_at=entry.joined_at,
        )
        self.add(record)
        await self.session.flush()
        return _entry_to_domain(record)

    async def save_entry(self, entry: QueueEntry) -> QueueEntry:
        record = await super().get(entry.id)
        if record is None:
            raise LookupError(f"Queue entry '{entry.id}' vanished before save.")
        _apply_entry(entry, record)
        await self.session.flush()
        return _entry_to_domain(record)

    async def list_active(self, queue_id: UUID) -> list[QueueEntry]:
        """Everyone still in the line. Ordering is the domain's job, not SQL's."""
        stmt = self._scope(
            select(QueueEntryRecord).where(
                QueueEntryRecord.queue_id == queue_id,
                QueueEntryRecord.status.in_(tuple(ACTIVE_QUEUE_STATUSES)),
            )
        ).order_by(QueueEntryRecord.position)
        result = await self.session.execute(stmt)
        return [_entry_to_domain(r) for r in result.scalars().all()]

    async def list_waiting(self, queue_id: UUID) -> list[QueueEntry]:
        stmt = self._scope(
            select(QueueEntryRecord).where(
                QueueEntryRecord.queue_id == queue_id,
                QueueEntryRecord.status == QueueEntryStatus.WAITING,
            )
        ).order_by(QueueEntryRecord.position)
        result = await self.session.execute(stmt)
        return [_entry_to_domain(r) for r in result.scalars().all()]

    async def max_position(self, queue_id: UUID) -> int:
        stmt = self._scope(
            select(func.max(QueueEntryRecord.position)).where(QueueEntryRecord.queue_id == queue_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def find_active_for_customer(
        self, *, queue_id: UUID, customer_id: UUID
    ) -> QueueEntry | None:
        """Stops one person occupying two places in the same line."""
        stmt = self._scope(
            select(QueueEntryRecord).where(
                QueueEntryRecord.queue_id == queue_id,
                QueueEntryRecord.customer_id == customer_id,
                QueueEntryRecord.status.in_(tuple(ACTIVE_QUEUE_STATUSES)),
            )
        )
        result = await self.session.execute(stmt.limit(1))
        record = result.scalar_one_or_none()
        return _entry_to_domain(record) if record else None

    async def find_for_booking(self, booking_id: UUID) -> QueueEntry | None:
        stmt = self._scope(
            select(QueueEntryRecord).where(QueueEntryRecord.booking_id == booking_id)
        )
        result = await self.session.execute(stmt.limit(1))
        record = result.scalar_one_or_none()
        return _entry_to_domain(record) if record else None

    async def list_for_customer(
        self, customer_id: UUID, *, limit: int = 20, offset: int = 0
    ) -> list[QueueEntry]:
        stmt = (
            self._scope(select(QueueEntryRecord).where(QueueEntryRecord.customer_id == customer_id))
            .order_by(QueueEntryRecord.joined_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [_entry_to_domain(r) for r in result.scalars().all()]

    async def list_facts(
        self, *, location_ids: Sequence[UUID], window: TimeRange, limit: int
    ) -> list[QueueEntryFact]:
        """Entries that joined a queue at these branches inside a window."""
        if not location_ids:
            return []
        stmt = (
            self._scope(
                select(
                    QueueEntryRecord.location_id,
                    QueueEntryRecord.service_id,
                    QueueEntryRecord.provider_id,
                    QueueEntryRecord.source,
                    QueueEntryRecord.status,
                    QueueEntryRecord.party_size,
                    QueueEntryRecord.joined_at,
                    QueueEntryRecord.called_at,
                    QueueEntryRecord.completed_at,
                ).where(
                    QueueEntryRecord.location_id.in_(tuple(location_ids)),
                    QueueEntryRecord.joined_at >= window.starts_at,
                    QueueEntryRecord.joined_at < window.ends_at,
                )
            )
            .order_by(QueueEntryRecord.joined_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            QueueEntryFact(
                location_id=row.location_id,
                service_id=row.service_id,
                provider_id=row.provider_id,
                source=row.source,
                status=row.status,
                party_size=row.party_size,
                joined_at=row.joined_at,
                called_at=row.called_at,
                completed_at=row.completed_at,
            )
            for row in result
        ]


class TicketRepository(TenantScopedRepository[TicketRecord]):
    model = TicketRecord

    async def get_ticket(self, ticket_id: UUID) -> Ticket | None:
        record = await super().get(ticket_id)
        return _ticket_to_domain(record) if record else None

    async def get_by_code(self, ticket_code: str) -> Ticket | None:
        stmt = self._scope(select(TicketRecord).where(TicketRecord.ticket_code == ticket_code))
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        return _ticket_to_domain(record) if record else None

    async def add_ticket(self, ticket: Ticket) -> Ticket:
        record = TicketRecord(
            id=ticket.id,
            tenant_id=ticket.tenant_id,
            booking_id=ticket.booking_id,
            queue_entry_id=ticket.queue_entry_id,
            ticket_code=ticket.ticket_code,
            qr_token_hash=ticket.qr_token_hash,
            status=ticket.status,
            expires_at=ticket.expires_at,
        )
        self.add(record)
        await self.session.flush()
        return _ticket_to_domain(record)

    async def save_ticket(self, ticket: Ticket) -> Ticket:
        record = await super().get(ticket.id)
        if record is None:
            raise LookupError(f"Ticket '{ticket.id}' vanished before save.")
        record.status = ticket.status
        record.redeemed_at = ticket.redeemed_at
        record.revoked_at = ticket.revoked_at
        await self.session.flush()
        return _ticket_to_domain(record)

    async def find_active_for_booking(self, booking_id: UUID) -> Ticket | None:
        stmt = self._scope(
            select(TicketRecord).where(
                TicketRecord.booking_id == booking_id,
                TicketRecord.status == TicketStatus.ACTIVE,
            )
        )
        result = await self.session.execute(stmt.limit(1))
        record = result.scalar_one_or_none()
        return _ticket_to_domain(record) if record else None

    async def find_active_for_queue_entry(self, queue_entry_id: UUID) -> Ticket | None:
        stmt = self._scope(
            select(TicketRecord).where(
                TicketRecord.queue_entry_id == queue_entry_id,
                TicketRecord.status == TicketStatus.ACTIVE,
            )
        )
        result = await self.session.execute(stmt.limit(1))
        record = result.scalar_one_or_none()
        return _ticket_to_domain(record) if record else None

    async def list_expired_active(self, *, now: datetime, limit: int = 200) -> list[Ticket]:
        """Active tickets whose time has passed. Swept by the worker."""
        stmt = self._scope(
            select(TicketRecord).where(
                TicketRecord.status == TicketStatus.ACTIVE,
                TicketRecord.expires_at <= now,
            )
        ).limit(limit)
        result = await self.session.execute(stmt)
        return [_ticket_to_domain(r) for r in result.scalars().all()]


__all__ = [
    "QueueEntryRepository",
    "QueueEntrySource",
    "QueueRepository",
    "TicketRepository",
]
