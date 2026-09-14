"""Availability generation — docs/09 #4, "availability is deterministic".

No database and no clock of their own: `generate_availability` takes working
hours, exceptions, and taken intervals and returns slots, so every case here is
exact rather than approximately-right-on-a-good-day.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.values import TimeRange
from app.modules.booking.domain import (
    ScheduleError,
    ScheduleException,
    WorkingWindow,
    generate_availability,
    sign_slot_id,
    validate_windows,
    verify_slot_id,
    windows_for_date,
)

PROVIDER = uuid4()
SERVICE = uuid4()
LOCATION = uuid4()
TENANT = uuid4()

# A Monday. 05:00 UTC is 08:00 in Riyadh, an hour before the salon opens.
MONDAY_MORNING = datetime(2026, 8, 17, 5, 0, tzinfo=UTC)
NINE_TO_ONE = WorkingWindow(weekday=0, start_minute=9 * 60, end_minute=13 * 60)


def _generate(**overrides):
    kwargs = {
        "weekly": [NINE_TO_ONE],
        "exceptions": {},
        "taken": [],
        "provider_id": PROVIDER,
        "service_id": SERVICE,
        "location_id": LOCATION,
        "timezone": "Asia/Riyadh",
        "date_from": MONDAY_MORNING,
        "date_to": MONDAY_MORNING + timedelta(days=1),
        "duration_minutes": 60,
        "granularity_minutes": 30,
        "now": MONDAY_MORNING,
    }
    kwargs.update(overrides)
    return generate_availability(**kwargs)


class TestWorkingWindow:
    def test_rejects_end_before_start(self):
        with pytest.raises(ScheduleError):
            WorkingWindow(weekday=0, start_minute=600, end_minute=540)

    def test_rejects_weekday_outside_the_week(self):
        with pytest.raises(ScheduleError):
            WorkingWindow(weekday=7, start_minute=540, end_minute=600)

    def test_split_shift_is_two_windows_and_does_not_overlap(self):
        morning = WorkingWindow(weekday=0, start_minute=9 * 60, end_minute=13 * 60)
        evening = WorkingWindow(weekday=0, start_minute=16 * 60, end_minute=21 * 60)
        assert not morning.overlaps(evening)
        assert validate_windows([evening, morning]) == [morning, evening]

    def test_overlapping_windows_are_rejected(self):
        # Two overlapping windows would generate the same slot twice, and
        # "deterministic availability" would stop being true.
        with pytest.raises(ScheduleError, match="overlap"):
            validate_windows(
                [
                    WorkingWindow(weekday=0, start_minute=540, end_minute=720),
                    WorkingWindow(weekday=0, start_minute=600, end_minute=780),
                ]
            )


class TestSlotGeneration:
    def test_generates_slots_across_the_working_window(self):
        # 09:00-13:00 local, 60-minute service, 30-minute grid:
        # 09:00, 09:30, 10:00, 10:30, 11:00, 11:30, 12:00 — and nothing at
        # 12:30, which would run past closing.
        slots = _generate()
        assert len(slots) == 7
        assert slots[0].starts_at == datetime(2026, 8, 17, 6, 0, tzinfo=UTC)  # 09:00 Riyadh
        assert slots[-1].ends_at == datetime(2026, 8, 17, 10, 0, tzinfo=UTC)  # 13:00 Riyadh

    def test_a_slot_never_runs_past_closing_time(self):
        # A 90-minute treatment in a 4-hour window: the last start that fits is
        # 11:30, not 12:00.
        slots = _generate(duration_minutes=90)
        assert all(s.ends_at <= datetime(2026, 8, 17, 10, 0, tzinfo=UTC) for s in slots)

    def test_is_deterministic(self):
        first = [s.starts_at for s in _generate()]
        second = [s.starts_at for s in _generate()]
        assert first == second == sorted(first)

    def test_existing_bookings_remove_overlapping_slots(self):
        # 10:00-11:00 local is taken. 09:30, 10:00 and 10:30 all overlap it.
        taken = [
            TimeRange(
                starts_at=datetime(2026, 8, 17, 7, 0, tzinfo=UTC),
                ends_at=datetime(2026, 8, 17, 8, 0, tzinfo=UTC),
            )
        ]
        assert len(_generate(taken=taken)) == 4

    def test_back_to_back_slots_do_not_block_each_other(self):
        # Half-open intervals: a 09:00-10:00 booking must leave 10:00 bookable.
        taken = [
            TimeRange(
                starts_at=datetime(2026, 8, 17, 6, 0, tzinfo=UTC),
                ends_at=datetime(2026, 8, 17, 7, 0, tzinfo=UTC),
            )
        ]
        starts = [s.starts_at for s in _generate(taken=taken)]
        assert datetime(2026, 8, 17, 7, 0, tzinfo=UTC) in starts

    def test_slots_in_the_past_are_not_offered(self):
        # "Now" is 11:00 local, midway through the window.
        now = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)
        slots = _generate(now=now)
        assert all(s.starts_at >= now for s in slots)

    def test_lead_time_pushes_the_first_bookable_slot_out(self):
        slots = _generate(lead_time_minutes=120)
        assert slots[0].starts_at >= MONDAY_MORNING + timedelta(minutes=120)

    def test_a_day_with_no_window_yields_nothing(self):
        # The schedule only covers Monday; asking about Tuesday is empty, not
        # an error.
        tuesday = MONDAY_MORNING + timedelta(days=1)
        assert _generate(date_from=tuesday, date_to=tuesday + timedelta(days=1)) == []

    def test_local_timezone_decides_the_weekday(self):
        # 22:00 UTC Sunday is already Monday 01:00 in Riyadh. Generating from
        # there must still find Monday's window — a UTC-based weekday would
        # miss it entirely.
        sunday_late = datetime(2026, 8, 16, 22, 0, tzinfo=UTC)
        slots = _generate(date_from=sunday_late, date_to=sunday_late + timedelta(days=1))
        assert len(slots) == 7


class TestScheduleExceptions:
    def test_a_closure_removes_the_whole_day(self):
        closed = {MONDAY_MORNING.date(): ScheduleException(on_date=MONDAY_MORNING.date())}
        assert _generate(exceptions=closed) == []

    def test_an_override_replaces_the_weekly_hours(self):
        # Eid hours: 10:00-12:00 only. Three 60-minute starts fit on the
        # 30-minute grid — 10:00, 10:30, 11:00 — and 11:30 would run past
        # closing.
        override = ScheduleException(
            on_date=MONDAY_MORNING.date(),
            windows=(WorkingWindow(weekday=0, start_minute=600, end_minute=720),),
            reason="Eid hours",
        )
        slots = _generate(exceptions={MONDAY_MORNING.date(): override})
        assert len(slots) == 3
        assert slots[0].starts_at == datetime(2026, 8, 17, 7, 0, tzinfo=UTC)  # 10:00 Riyadh
        assert slots[-1].ends_at == datetime(2026, 8, 17, 9, 0, tzinfo=UTC)  # 12:00 Riyadh

    def test_windows_for_date_prefers_the_override(self):
        override = ScheduleException(on_date=MONDAY_MORNING.date())
        assert (
            windows_for_date(
                MONDAY_MORNING.date(),
                weekly=[NINE_TO_ONE],
                exceptions={MONDAY_MORNING.date(): override},
            )
            == []
        )


class TestSignedSlotIds:
    """docs/07 section 5: agents may query availability but must not invent slots."""

    def _sign(self, starts_at, secret="s3cret"):
        return sign_slot_id(
            tenant_id=TENANT,
            provider_id=PROVIDER,
            service_id=SERVICE,
            starts_at=starts_at,
            secret=secret,
        )

    def test_the_same_slot_always_gets_the_same_id(self):
        assert self._sign(MONDAY_MORNING) == self._sign(MONDAY_MORNING)

    def test_verifies_its_own_signature(self):
        assert verify_slot_id(
            self._sign(MONDAY_MORNING),
            tenant_id=TENANT,
            provider_id=PROVIDER,
            service_id=SERVICE,
            starts_at=MONDAY_MORNING,
            secret="s3cret",
        )

    def test_a_different_time_does_not_verify(self):
        assert not verify_slot_id(
            self._sign(MONDAY_MORNING),
            tenant_id=TENANT,
            provider_id=PROVIDER,
            service_id=SERVICE,
            starts_at=MONDAY_MORNING + timedelta(minutes=30),
            secret="s3cret",
        )

    def test_another_tenant_cannot_reuse_a_slot_id(self):
        assert not verify_slot_id(
            self._sign(MONDAY_MORNING),
            tenant_id=uuid4(),
            provider_id=PROVIDER,
            service_id=SERVICE,
            starts_at=MONDAY_MORNING,
            secret="s3cret",
        )

    def test_a_forged_id_without_the_secret_does_not_verify(self):
        assert not verify_slot_id(
            self._sign(MONDAY_MORNING, secret="wrong-secret"),
            tenant_id=TENANT,
            provider_id=PROVIDER,
            service_id=SERVICE,
            starts_at=MONDAY_MORNING,
            secret="s3cret",
        )
