"""booking · PERSISTENCE layer — queries and domain<->row mapping.

Layer rule: models + `app.db` + this module's domain. Must not import
service, router, or fastapi.

This repository is the *only* place that knows both shapes. Callers hand it
`domain.Booking` and get `domain.Booking` back; `BookingRecord` never escapes
this file.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, case, delete, func, select, text

from app.core.values import Money, TimeRange, to_minor_units
from app.db.repository import TenantScopedRepository
from app.modules.booking.domain import (
    BLOCKING_STATUSES,
    Booking,
    BookingFact,
    BookingSource,
    BookingStatus,
    CustomerVisitFact,
    ScheduleException,
    WorkingWindow,
)
from app.modules.booking.models import (
    BookingRecord,
    ProviderScheduleRecord,
    ScheduleExceptionRecord,
    SlotHoldRecord,
)


def _to_domain(record: BookingRecord) -> Booking:
    return Booking(
        id=record.id,
        tenant_id=record.tenant_id,
        business_id=record.business_id,
        location_id=record.location_id,
        service_id=record.service_id,
        provider_id=record.provider_id,
        customer_id=record.customer_id,
        slot=TimeRange(starts_at=record.starts_at, ends_at=record.ends_at),
        price=Money(amount=record.price, currency=record.currency),
        status=record.status,
        source=record.source,
        cancellation_reason=record.cancellation_reason,
        notes=record.notes,
    )


def _apply_to_record(booking: Booking, record: BookingRecord) -> BookingRecord:
    """Copies the mutable domain state back onto the row.

    Identity and scheduling fields are deliberately not copied — rescheduling
    is a separate use case that must re-run the conflict check, so it cannot
    happen as a side effect of saving a status change. `reschedule_booking`
    below is the only place `starts_at` is allowed to move.
    """
    record.status = booking.status
    record.cancellation_reason = booking.cancellation_reason
    return record


class BookingRepository(TenantScopedRepository[BookingRecord]):
    model = BookingRecord

    async def lock_provider_calendar(self, provider_id: UUID) -> None:
        """Serialises booking attempts for one provider within a transaction.

        `pg_advisory_xact_lock` takes a lock held until the transaction ends —
        no explicit release, so an error path cannot leak it. Two concurrent
        requests for the same provider queue instead of both reading "no
        conflict" and both inserting.

        The lock key is derived from (tenant, provider) so unrelated providers
        never contend. Postgres advisory locks take two 32-bit ints; we hash
        the UUIDs down to that, accepting that a hash collision costs only a
        little unnecessary serialisation, never correctness.
        """
        tenant_key = self.tenant_id.int % (2**31)
        provider_key = provider_id.int % (2**31)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:tenant_key, :provider_key)"),
            {"tenant_key": tenant_key, "provider_key": provider_key},
        )

    async def get_booking(self, booking_id: UUID) -> Booking | None:
        record = await super().get(booking_id)
        return _to_domain(record) if record else None

    async def add_booking(self, booking: Booking) -> Booking:
        record = BookingRecord(
            id=booking.id,
            tenant_id=booking.tenant_id,
            business_id=booking.business_id,
            location_id=booking.location_id,
            service_id=booking.service_id,
            provider_id=booking.provider_id,
            customer_id=booking.customer_id,
            starts_at=booking.slot.starts_at,
            ends_at=booking.slot.ends_at,
            price=booking.price.amount,
            currency=booking.price.currency,
            status=booking.status,
            source=booking.source,
            notes=booking.notes,
        )
        self.add(record)
        await self.session.flush()
        return _to_domain(record)

    async def save(self, booking: Booking) -> Booking:
        record = await super().get(booking.id)
        if record is None:
            raise LookupError(f"Booking '{booking.id}' vanished before save.")
        _apply_to_record(booking, record)
        await self.session.flush()
        return _to_domain(record)

    async def find_conflicting(
        self,
        *,
        provider_id: UUID,
        slot: TimeRange,
        exclude_booking_id: UUID | None = None,
    ) -> Booking | None:
        """Returns an existing booking that would collide, if any.

        Overlap test is `existing.starts_at < new.ends_at AND
        new.starts_at < existing.ends_at` — the half-open comparison, so
        back-to-back appointments do not collide.

        This is a check-then-act read: it narrows the race but does not close
        it. The unique/exclusion constraint in the migration is what actually
        guarantees no double-booking under concurrency.
        """
        stmt = self._scope(
            select(BookingRecord).where(
                BookingRecord.provider_id == provider_id,
                BookingRecord.status.in_(tuple(BLOCKING_STATUSES)),
                BookingRecord.starts_at < slot.ends_at,
                BookingRecord.ends_at > slot.starts_at,
            )
        )
        if exclude_booking_id is not None:
            stmt = stmt.where(BookingRecord.id != exclude_booking_id)

        result = await self.session.execute(stmt.limit(1))
        record = result.scalar_one_or_none()
        return _to_domain(record) if record else None

    async def list_for_provider(self, *, provider_id: UUID, window: TimeRange) -> list[Booking]:
        stmt = self._scope(
            select(BookingRecord)
            .where(
                BookingRecord.provider_id == provider_id,
                BookingRecord.starts_at < window.ends_at,
                BookingRecord.ends_at > window.starts_at,
            )
            .order_by(BookingRecord.starts_at)
        )
        result = await self.session.execute(stmt)
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_for_customer(
        self, *, customer_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[Booking]:
        stmt = (
            self._scope(select(BookingRecord).where(BookingRecord.customer_id == customer_id))
            .order_by(BookingRecord.starts_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_due_for_no_show(self, *, before: datetime) -> list[Booking]:
        """Confirmed bookings whose start time has passed without check-in."""
        stmt = self._scope(
            select(BookingRecord).where(
                BookingRecord.status == BookingStatus.CONFIRMED,
                BookingRecord.starts_at < before,
            )
        )
        result = await self.session.execute(stmt)
        return [_to_domain(r) for r in result.scalars().all()]

    async def map_business_ids(self, booking_ids: Sequence[UUID]) -> dict[UUID, UUID]:
        """Which business each booking belongs to.

        Two columns rather than whole bookings, for the same reason as
        `list_blocking_in_window`: the caller (the daily payout job, which has
        payments and needs somebody to pay) asked one narrow question, and
        handing it customer data it did not ask for is how that data ends up
        somewhere it should not be.
        """
        if not booking_ids:
            return {}
        stmt = self._scope(
            select(BookingRecord.id, BookingRecord.business_id).where(
                BookingRecord.id.in_(tuple(booking_ids))
            )
        )
        result = await self.session.execute(stmt)
        return {row.id: row.business_id for row in result}

    async def list_blocking_in_window(
        self, *, provider_id: UUID, window: TimeRange
    ) -> list[TimeRange]:
        """Intervals already taken by bookings, for availability generation.

        Returns bare `TimeRange`s rather than bookings: availability only needs
        to know *that* a time is gone, and handing the generator whole
        aggregates would tempt it into reading customer data it has no business
        seeing.
        """
        stmt = self._scope(
            select(BookingRecord.starts_at, BookingRecord.ends_at).where(
                BookingRecord.provider_id == provider_id,
                BookingRecord.status.in_(tuple(BLOCKING_STATUSES)),
                BookingRecord.starts_at < window.ends_at,
                BookingRecord.ends_at > window.starts_at,
            )
        )
        result = await self.session.execute(stmt)
        return [TimeRange(starts_at=row.starts_at, ends_at=row.ends_at) for row in result]

    async def list_facts(
        self, *, business_id: UUID, window: TimeRange, limit: int
    ) -> list[BookingFact]:
        """One business's bookings starting in a window, as analytics facts.

        Named columns rather than rows, like `map_business_ids`: the report
        asked a narrow question, so it gets a narrow answer (docs/13 s6.2).
        """
        stmt = (
            self._scope(
                select(
                    BookingRecord.id,
                    BookingRecord.location_id,
                    BookingRecord.service_id,
                    BookingRecord.provider_id,
                    BookingRecord.customer_id,
                    BookingRecord.starts_at,
                    BookingRecord.ends_at,
                    BookingRecord.created_at,
                    BookingRecord.status,
                    BookingRecord.source,
                    BookingRecord.price,
                    BookingRecord.currency,
                ).where(
                    BookingRecord.business_id == business_id,
                    BookingRecord.starts_at >= window.starts_at,
                    BookingRecord.starts_at < window.ends_at,
                )
            )
            .order_by(BookingRecord.starts_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            BookingFact(
                id=row.id,
                location_id=row.location_id,
                service_id=row.service_id,
                provider_id=row.provider_id,
                customer_id=row.customer_id,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
                created_at=row.created_at,
                status=row.status,
                source=row.source,
                price_minor=to_minor_units(row.price),
                currency=row.currency,
            )
            for row in result
        ]

    async def list_customer_visit_facts(
        self, *, business_id: UUID, as_of: datetime, limit: int
    ) -> list[CustomerVisitFact]:
        """Each customer's visit history with one business, aggregated in SQL.

        Aggregated here rather than in pandas because it spans all time, not a
        window: a customer's first visit decides whether they count as new, and
        it may be years before any window a dashboard asks about.
        """
        completed = BookingRecord.status == BookingStatus.COMPLETED
        completed_start = case((completed, BookingRecord.starts_at))
        upcoming = and_(
            BookingRecord.status.in_(tuple(BLOCKING_STATUSES)),
            BookingRecord.starts_at >= as_of,
        )
        stmt = (
            self._scope(
                select(
                    BookingRecord.customer_id,
                    func.min(completed_start).label("first_completed_at"),
                    func.max(completed_start).label("last_completed_at"),
                    func.count().filter(completed).label("completed_count"),
                    func.bool_or(upcoming).label("has_upcoming"),
                ).where(BookingRecord.business_id == business_id)
            )
            .group_by(BookingRecord.customer_id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [
            CustomerVisitFact(
                customer_id=row.customer_id,
                first_completed_at=row.first_completed_at,
                last_completed_at=row.last_completed_at,
                completed_count=row.completed_count,
                has_upcoming=bool(row.has_upcoming),
            )
            for row in result
        ]

    async def reschedule_booking(self, booking: Booking, *, provider_id: UUID) -> Booking:
        """Moves a booking to a new time, the one place that is permitted.

        Kept off `save()` on purpose: moving a booking has to re-run the
        conflict check first, and a status change must never be able to shift a
        time as a side effect.
        """
        record = await super().get(booking.id)
        if record is None:
            raise LookupError(f"Booking '{booking.id}' vanished before reschedule.")
        record.provider_id = provider_id
        record.starts_at = booking.slot.starts_at
        record.ends_at = booking.slot.ends_at
        await self.session.flush()
        return _to_domain(record)


class ScheduleRepository(TenantScopedRepository[ProviderScheduleRecord]):
    """Weekly working hours and the dated exceptions that override them."""

    model = ProviderScheduleRecord

    async def list_windows(self, provider_id: UUID) -> list[WorkingWindow]:
        stmt = self._scope(
            select(ProviderScheduleRecord).where(ProviderScheduleRecord.provider_id == provider_id)
        ).order_by(ProviderScheduleRecord.weekday, ProviderScheduleRecord.start_minute)
        result = await self.session.execute(stmt)
        return [
            WorkingWindow(weekday=r.weekday, start_minute=r.start_minute, end_minute=r.end_minute)
            for r in result.scalars().all()
        ]

    async def list_windows_for_providers(
        self, provider_ids: Sequence[UUID]
    ) -> dict[UUID, list[WorkingWindow]]:
        """Weekly windows for several providers in one query, for capacity reports."""
        if not provider_ids:
            return {}
        stmt = self._scope(
            select(ProviderScheduleRecord).where(
                ProviderScheduleRecord.provider_id.in_(tuple(provider_ids))
            )
        ).order_by(ProviderScheduleRecord.weekday, ProviderScheduleRecord.start_minute)
        result = await self.session.execute(stmt)
        windows: dict[UUID, list[WorkingWindow]] = {}
        for r in result.scalars().all():
            windows.setdefault(r.provider_id, []).append(
                WorkingWindow(
                    weekday=r.weekday, start_minute=r.start_minute, end_minute=r.end_minute
                )
            )
        return windows

    async def replace_windows(
        self, *, provider_id: UUID, location_id: UUID, windows: list[WorkingWindow]
    ) -> list[WorkingWindow]:
        """Sets a provider's whole week at once.

        Replace rather than merge: a partial update makes "delete Thursday"
        impossible to express, and a schedule half-applied is worse than one
        that failed outright.
        """
        await self.session.execute(
            delete(ProviderScheduleRecord).where(
                ProviderScheduleRecord.tenant_id == self.tenant_id,
                ProviderScheduleRecord.provider_id == provider_id,
            )
        )
        for window in windows:
            self.session.add(
                ProviderScheduleRecord(
                    tenant_id=self.tenant_id,
                    provider_id=provider_id,
                    location_id=location_id,
                    weekday=window.weekday,
                    start_minute=window.start_minute,
                    end_minute=window.end_minute,
                )
            )
        await self.session.flush()
        return sorted(windows)

    async def list_exceptions(
        self, *, provider_id: UUID, date_from: date, date_to: date
    ) -> dict[date, ScheduleException]:
        """Exceptions keyed by date, with same-day windows folded together.

        Note the explicit `tenant_id` filter instead of `self._scope`: this
        repository's `model` is `ProviderScheduleRecord`, so `_scope` would add
        a predicate on the *wrong* table and silently produce a cartesian
        product between schedules and exceptions.
        """
        stmt = (
            select(ScheduleExceptionRecord)
            .where(
                ScheduleExceptionRecord.tenant_id == self.tenant_id,
                ScheduleExceptionRecord.provider_id == provider_id,
                ScheduleExceptionRecord.on_date >= date_from,
                ScheduleExceptionRecord.on_date <= date_to,
            )
            .order_by(ScheduleExceptionRecord.on_date, ScheduleExceptionRecord.start_minute)
        )
        result = await self.session.execute(stmt)

        exceptions: dict[date, ScheduleException] = {}
        for row in result.scalars().all():
            existing = exceptions.get(row.on_date)
            windows = existing.windows if existing else ()
            if not row.is_closed and row.start_minute is not None and row.end_minute is not None:
                windows = (
                    *windows,
                    WorkingWindow(
                        weekday=row.on_date.weekday(),
                        start_minute=row.start_minute,
                        end_minute=row.end_minute,
                    ),
                )
            exceptions[row.on_date] = ScheduleException(
                on_date=row.on_date,
                windows=windows,
                reason=row.reason or (existing.reason if existing else None),
            )
        return exceptions

    def add_exception(
        self,
        *,
        provider_id: UUID,
        on_date: date,
        is_closed: bool,
        start_minute: int | None = None,
        end_minute: int | None = None,
        reason: str | None = None,
    ) -> ScheduleExceptionRecord:
        record = ScheduleExceptionRecord(
            tenant_id=self.tenant_id,
            provider_id=provider_id,
            on_date=on_date,
            is_closed=is_closed,
            start_minute=start_minute,
            end_minute=end_minute,
            reason=reason,
        )
        self.session.add(record)
        return record


class SlotHoldRepository(TenantScopedRepository[SlotHoldRecord]):
    """Short-lived reservations taken during checkout or by the booking agent."""

    model = SlotHoldRecord

    async def list_active(
        self, *, provider_id: UUID, window: TimeRange, now: datetime | None = None
    ) -> list[TimeRange]:
        """Live holds blocking a provider's calendar within a window."""
        now = now or datetime.now(UTC)
        stmt = self._scope(
            select(SlotHoldRecord.starts_at, SlotHoldRecord.ends_at).where(
                SlotHoldRecord.provider_id == provider_id,
                SlotHoldRecord.consumed_at.is_(None),
                SlotHoldRecord.expires_at > now,
                SlotHoldRecord.starts_at < window.ends_at,
                SlotHoldRecord.ends_at > window.starts_at,
            )
        )
        result = await self.session.execute(stmt)
        return [TimeRange(starts_at=row.starts_at, ends_at=row.ends_at) for row in result]

    async def find_conflicting(
        self, *, provider_id: UUID, slot: TimeRange, now: datetime | None = None
    ) -> SlotHoldRecord | None:
        now = now or datetime.now(UTC)
        stmt = self._scope(
            select(SlotHoldRecord).where(
                SlotHoldRecord.provider_id == provider_id,
                SlotHoldRecord.consumed_at.is_(None),
                SlotHoldRecord.expires_at > now,
                SlotHoldRecord.starts_at < slot.ends_at,
                SlotHoldRecord.ends_at > slot.starts_at,
            )
        )
        result = await self.session.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def lock_holder(self, held_by: UUID) -> None:
        """Serialises one holder's hold attempts at this tenant.

        Without it, two holds sent at once both count the same live holds and
        both slip under the cap. Scope 78, beside the queue lock's 77.
        """
        holder_key = (self.tenant_id.int ^ held_by.int) % (2**31)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:scope, :holder_key)"),
            {"scope": 78, "holder_key": holder_key},
        )

    async def count_active_for_holder(self, held_by: UUID, *, now: datetime) -> int:
        """Live holds one principal has at this tenant: neither consumed nor expired."""
        stmt = self._scope(
            select(func.count())
            .select_from(SlotHoldRecord)
            .where(
                SlotHoldRecord.held_by == held_by,
                SlotHoldRecord.consumed_at.is_(None),
                SlotHoldRecord.expires_at > now,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_by_token(self, hold_token: str) -> SlotHoldRecord | None:
        stmt = self._scope(select(SlotHoldRecord).where(SlotHoldRecord.hold_token == hold_token))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_hold(self, record: SlotHoldRecord) -> SlotHoldRecord:
        self.add(record)
        await self.session.flush()
        return record

    async def purge_expired(self, *, before: datetime) -> int:
        """Sweeps holds that expired long ago. Called by the worker."""
        result = await self.session.execute(
            delete(SlotHoldRecord).where(
                SlotHoldRecord.tenant_id == self.tenant_id,
                SlotHoldRecord.expires_at < before,
            )
        )
        # execute() of a DELETE returns a CursorResult at runtime; the
        # declared Result type does not expose rowcount.
        return result.rowcount or 0  # type: ignore[attr-defined]


__all__ = [
    "BookingRepository",
    "BookingSource",
    "BookingStatus",
    "ScheduleRepository",
    "SlotHoldRepository",
]
