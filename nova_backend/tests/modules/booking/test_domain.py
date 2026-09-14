"""Pure domain tests for booking — no database, no HTTP, no fixtures.

That these run without any infrastructure is the point of keeping domain.py
free of framework imports.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationDomainError
from app.core.values import Money, TimeRange
from app.modules.booking.domain import (
    BLOCKING_STATUSES,
    Booking,
    BookingStatus,
    CancellationPolicy,
    CancellationTooLate,
    InvalidBookingTransition,
    assert_slot_is_bookable,
    build_slot,
)

NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)


def make_booking(
    *,
    starts_at: datetime | None = None,
    duration_minutes: int = 60,
    status: BookingStatus = BookingStatus.DRAFT,
    provider_id=None,
) -> Booking:
    starts_at = starts_at or NOW + timedelta(days=2)
    return Booking(
        id=uuid4(),
        tenant_id=uuid4(),
        business_id=uuid4(),
        location_id=uuid4(),
        service_id=uuid4(),
        provider_id=provider_id or uuid4(),
        customer_id=uuid4(),
        slot=build_slot(starts_at=starts_at, duration_minutes=duration_minutes),
        price=Money(amount=Decimal("150.00")),
        status=status,
    )


class TestLifecycle:
    def test_happy_path_runs_to_completion(self):
        booking = make_booking()
        booking.require_payment()
        booking.confirm()
        booking.check_in()
        booking.start_service()
        booking.complete()
        assert booking.status is BookingStatus.COMPLETED

    def test_draft_can_confirm_without_payment_step(self):
        booking = make_booking()
        booking.confirm()
        assert booking.status is BookingStatus.CONFIRMED

    def test_cannot_complete_without_checking_in(self):
        """The corruption this whole entity exists to prevent."""
        booking = make_booking(status=BookingStatus.CONFIRMED)
        with pytest.raises(InvalidBookingTransition) as exc:
            booking.complete()
        assert exc.value.current is BookingStatus.CONFIRMED
        assert exc.value.attempted is BookingStatus.COMPLETED
        assert booking.status is BookingStatus.CONFIRMED  # unchanged

    def test_terminal_states_are_final(self):
        for terminal in (BookingStatus.COMPLETED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW):
            booking = make_booking(status=terminal)
            with pytest.raises(InvalidBookingTransition):
                booking.confirm()

    def test_only_confirmed_can_be_marked_no_show(self):
        booking = make_booking(status=BookingStatus.DRAFT)
        with pytest.raises(InvalidBookingTransition):
            booking.mark_no_show()

    def test_transition_error_names_the_legal_moves(self):
        booking = make_booking(status=BookingStatus.CONFIRMED)
        with pytest.raises(InvalidBookingTransition) as exc:
            booking.complete()
        assert "checked_in" in str(exc.value)


class TestCancellation:
    def test_cancels_before_the_deadline(self):
        booking = make_booking(starts_at=NOW + timedelta(hours=48))
        booking.cancel(policy=CancellationPolicy(24), now=NOW, reason="changed plans")
        assert booking.status is BookingStatus.CANCELLED
        assert booking.cancellation_reason == "changed plans"

    def test_rejects_cancellation_inside_the_window(self):
        booking = make_booking(starts_at=NOW + timedelta(hours=2))
        with pytest.raises(CancellationTooLate):
            booking.cancel(policy=CancellationPolicy(24), now=NOW)
        assert booking.status is BookingStatus.DRAFT

    def test_staff_may_cancel_inside_the_window(self):
        """The business cancelling its own appointment is not the customer's fault."""
        booking = make_booking(starts_at=NOW + timedelta(hours=2))
        booking.cancel(
            policy=CancellationPolicy(24), now=NOW, reason="provider ill", enforce_policy=False
        )
        assert booking.status is BookingStatus.CANCELLED

    def test_zero_hour_policy_allows_cancelling_until_start(self):
        booking = make_booking(starts_at=NOW + timedelta(minutes=1))
        booking.cancel(policy=CancellationPolicy(0), now=NOW)
        assert booking.status is BookingStatus.CANCELLED


class TestConflicts:
    def test_same_provider_overlapping_conflicts(self):
        provider = uuid4()
        a = make_booking(starts_at=NOW + timedelta(days=1), provider_id=provider)
        b = make_booking(starts_at=NOW + timedelta(days=1, minutes=30), provider_id=provider)
        assert a.conflicts_with(b)

    def test_back_to_back_bookings_do_not_conflict(self):
        """10:00-11:00 and 11:00-12:00 must both be bookable."""
        provider = uuid4()
        a = make_booking(
            starts_at=NOW + timedelta(days=1), duration_minutes=60, provider_id=provider
        )
        b = make_booking(
            starts_at=NOW + timedelta(days=1, hours=1), duration_minutes=60, provider_id=provider
        )
        assert not a.conflicts_with(b)

    def test_different_providers_never_conflict(self):
        a = make_booking(starts_at=NOW + timedelta(days=1))
        b = make_booking(starts_at=NOW + timedelta(days=1))
        assert not a.conflicts_with(b)

    def test_cancelled_booking_frees_its_slot(self):
        provider = uuid4()
        a = make_booking(starts_at=NOW + timedelta(days=1), provider_id=provider)
        b = make_booking(starts_at=NOW + timedelta(days=1), provider_id=provider)
        a.cancel(policy=CancellationPolicy(0), now=NOW)
        assert not a.conflicts_with(b)

    def test_booking_never_conflicts_with_itself(self):
        a = make_booking()
        assert not a.conflicts_with(a)

    def test_blocking_statuses_match_the_migration(self):
        """The EXCLUDE constraint hardcodes this list; drift breaks the guarantee."""
        assert {s.value for s in BLOCKING_STATUSES} == {
            "draft",
            "pending_payment",
            "confirmed",
            "checked_in",
            "in_service",
        }


class TestSlotConstruction:
    def test_end_is_derived_from_duration(self):
        slot = build_slot(starts_at=NOW, duration_minutes=90)
        assert slot.ends_at == NOW + timedelta(minutes=90)

    def test_naive_datetime_is_rejected(self):
        with pytest.raises(ValidationDomainError):
            build_slot(starts_at=datetime(2026, 8, 15, 10, 0), duration_minutes=60)

    def test_past_slot_is_rejected(self):
        slot = build_slot(starts_at=NOW - timedelta(hours=1), duration_minutes=60)
        with pytest.raises(ValidationDomainError):
            assert_slot_is_bookable(slot, now=NOW)


class TestTimeRange:
    def test_end_must_follow_start(self):
        with pytest.raises(ValueError):
            TimeRange(starts_at=NOW, ends_at=NOW)

    def test_money_rejects_mixed_currencies(self):
        with pytest.raises(ValueError):
            Money(amount=Decimal("10.00"), currency="SAR") + Money(
                amount=Decimal("10.00"), currency="AED"
            )
