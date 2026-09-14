"""Queue and ticket rules — docs/03 section 4, docs/06 sections 5-6.

The two rules worth testing hardest, because both are easy to break and
expensive when broken: walk-ins and appointments share ONE ordered timeline,
and a QR ticket must be unforgeable and single-use.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError
from app.modules.queue.domain import (
    QueueEntry,
    QueueEntrySource,
    QueueEntryStatus,
    Ticket,
    TicketExpiredError,
    TicketInvalidError,
    TicketStatus,
    build_qr_payload,
    estimate_wait_minutes,
    generate_qr_token,
    generate_ticket_code,
    hash_qr_token,
    next_position,
    order_queue,
    parse_qr_payload,
    verify_qr_token,
)

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
SECRET = "queue-secret"


def make_entry(
    *,
    position=1,
    status=QueueEntryStatus.WAITING,
    source=QueueEntrySource.WALK_IN,
    joined_at=NOW,
    scheduled_for=None,
) -> QueueEntry:
    return QueueEntry(
        id=uuid4(),
        tenant_id=uuid4(),
        queue_id=uuid4(),
        location_id=uuid4(),
        customer_id=uuid4(),
        service_id=uuid4(),
        provider_id=None,
        status=status,
        position=position,
        source=source,
        joined_at=joined_at,
        scheduled_for=scheduled_for,
    )


class TestQueueEntryLifecycle:
    def test_happy_path_runs_to_completion(self):
        entry = make_entry()
        entry.call(now=NOW)
        entry.check_in(now=NOW)
        entry.start_service()
        entry.complete(now=NOW)
        assert entry.status is QueueEntryStatus.COMPLETED

    def test_cannot_check_in_before_being_called(self):
        entry = make_entry()
        with pytest.raises(ConflictError):
            entry.check_in(now=NOW)

    def test_only_a_called_customer_can_be_missed(self):
        entry = make_entry()
        with pytest.raises(ConflictError):
            entry.miss()

        entry.call(now=NOW)
        entry.miss()
        assert entry.status is QueueEntryStatus.MISSED

    def test_a_missed_customer_can_rejoin_the_line(self):
        # Someone who stepped outside should not have to start over.
        entry = make_entry()
        entry.call(now=NOW)
        entry.miss()
        entry.requeue()
        assert entry.status is QueueEntryStatus.WAITING
        assert entry.called_at is None

    def test_terminal_states_are_final(self):
        entry = make_entry()
        entry.cancel()
        with pytest.raises(ConflictError):
            entry.call(now=NOW)

    def test_completed_entries_leave_the_line(self):
        entry = make_entry()
        entry.call(now=NOW)
        entry.check_in(now=NOW)
        entry.start_service()
        entry.complete(now=NOW)
        assert not entry.is_active


class TestSharedTimelineOrdering:
    """docs/03 section 4: one timeline, different priority weights."""

    def test_walk_ins_are_served_in_arrival_order(self):
        first = make_entry(position=1, joined_at=NOW)
        second = make_entry(position=2, joined_at=NOW + timedelta(minutes=5))
        assert order_queue([second, first]) == [first, second]

    def test_an_appointment_beats_a_walk_in_who_arrived_at_the_same_moment(self):
        # Without the penalty, someone standing at the desk always beats the
        # customer who booked ahead — and booking would stop meaning anything.
        walk_in = make_entry(source=QueueEntrySource.WALK_IN, joined_at=NOW)
        appointment = make_entry(
            source=QueueEntrySource.APPOINTMENT, joined_at=NOW, scheduled_for=NOW
        )
        assert order_queue([walk_in, appointment])[0] is appointment

    def test_an_appointment_does_not_jump_the_queue_hours_early(self):
        # A 17:00 booking must not be called at 09:00 ahead of people waiting.
        walk_in = make_entry(joined_at=NOW)
        later_appointment = make_entry(
            source=QueueEntrySource.APPOINTMENT,
            joined_at=NOW,
            scheduled_for=NOW + timedelta(hours=8),
        )
        assert order_queue([later_appointment, walk_in])[0] is walk_in

    def test_a_walk_in_who_waited_long_enough_beats_a_later_appointment(self):
        walk_in = make_entry(joined_at=NOW - timedelta(hours=1))
        appointment = make_entry(
            source=QueueEntrySource.APPOINTMENT,
            joined_at=NOW,
            scheduled_for=NOW + timedelta(minutes=30),
        )
        assert order_queue([appointment, walk_in])[0] is walk_in

    def test_ordering_is_total_and_stable(self):
        # Identical timestamps must still produce one definite order, not one
        # that depends on how the rows came back from the database.
        entries = [make_entry(position=i, joined_at=NOW) for i in range(5)]
        assert order_queue(entries) == order_queue(list(reversed(entries)))

    def test_positions_are_monotonic_and_never_reused(self):
        assert next_position([]) == 1
        assert next_position([1, 2, 3]) == 4
        # A cancelled entry at position 2 must not free that number.
        assert next_position([1, 3]) == 4


class TestWaitEstimate:
    def test_the_person_at_the_front_waits_no_time(self):
        entries = [make_entry(position=i) for i in range(3)]
        ordered = order_queue(entries)
        assert estimate_wait_minutes(ordered, ordered[0].id, average_service_minutes=30) == 0

    def test_wait_grows_with_the_number_of_people_ahead(self):
        entries = [make_entry(position=i, joined_at=NOW + timedelta(minutes=i)) for i in range(3)]
        ordered = order_queue(entries)
        assert estimate_wait_minutes(ordered, ordered[2].id, average_service_minutes=30) == 60

    def test_more_providers_shorten_the_wait(self):
        entries = [make_entry(position=i, joined_at=NOW + timedelta(minutes=i)) for i in range(4)]
        ordered = order_queue(entries)
        assert (
            estimate_wait_minutes(
                ordered, ordered[3].id, average_service_minutes=30, active_providers=3
            )
            == 30
        )

    def test_an_unknown_entry_has_no_estimate(self):
        assert estimate_wait_minutes([], uuid4(), average_service_minutes=30) is None


class TestTicketSecurity:
    """docs/06 section 6, docs/07 section 7, docs/08 section 13."""

    def _ticket(self, token: str, *, expires_in_hours: int = 12) -> Ticket:
        return Ticket(
            id=uuid4(),
            tenant_id=uuid4(),
            ticket_code=generate_ticket_code(),
            qr_token_hash=hash_qr_token(token),
            status=TicketStatus.ACTIVE,
            expires_at=NOW + timedelta(hours=expires_in_hours),
        )

    def test_the_payload_carries_no_pii(self):
        token = generate_qr_token()
        ticket = self._ticket(token)
        payload = build_qr_payload(ticket_id=ticket.id, qr_token=token, secret=SECRET)

        # Three dot-separated parts and nothing else: id, token, signature.
        assert payload.count(".") == 2
        assert str(ticket.id) in payload
        for pii in ("@", "+966", "Sara", "Ahmed"):
            assert pii not in payload

    def test_only_a_hash_is_ever_stored(self):
        token = generate_qr_token()
        ticket = self._ticket(token)
        assert token not in ticket.qr_token_hash
        assert verify_qr_token(token, stored_hash=ticket.qr_token_hash)

    def test_round_trips_through_parse(self):
        token = generate_qr_token()
        ticket = self._ticket(token)
        payload = build_qr_payload(ticket_id=ticket.id, qr_token=token, secret=SECRET)
        parsed_id, parsed_token = parse_qr_payload(payload, secret=SECRET)
        assert (parsed_id, parsed_token) == (ticket.id, token)

    def test_a_tampered_payload_is_rejected(self):
        token = generate_qr_token()
        ticket = self._ticket(token)
        payload = build_qr_payload(ticket_id=ticket.id, qr_token=token, secret=SECRET)
        body, _, signature = payload.rpartition(".")
        forged = f"{body}.{'0' * len(signature)}"
        with pytest.raises(TicketInvalidError):
            parse_qr_payload(forged, secret=SECRET)

    def test_a_payload_signed_with_another_secret_is_rejected(self):
        token = generate_qr_token()
        ticket = self._ticket(token)
        payload = build_qr_payload(ticket_id=ticket.id, qr_token=token, secret="other-secret")
        with pytest.raises(TicketInvalidError):
            parse_qr_payload(payload, secret=SECRET)

    def test_garbage_is_rejected_without_a_distinguishing_message(self):
        # Every failure says the same thing, so a scanner cannot be used as an
        # oracle to work out which part of a forgery to fix.
        errors = []
        for bad in ("", "nonsense", "a.b", "a.b.c.d"):
            with pytest.raises(TicketInvalidError) as exc:
                parse_qr_payload(bad, secret=SECRET)
            errors.append(str(exc.value))
        assert len(set(errors)) == 1

    def test_a_wrong_token_does_not_verify_against_the_hash(self):
        ticket = self._ticket(generate_qr_token())
        assert not verify_qr_token(generate_qr_token(), stored_hash=ticket.qr_token_hash)

    def test_ticket_codes_avoid_ambiguous_characters(self):
        # Called out loud across a salon floor: no 0/O or 1/I/L confusion.
        for _ in range(50):
            code = generate_ticket_code().removeprefix("NV-")
            assert not set(code) & set("01OIL")


class TestTicketLifecycle:
    def _ticket(self, **overrides) -> Ticket:
        defaults = {
            "id": uuid4(),
            "tenant_id": uuid4(),
            "ticket_code": generate_ticket_code(),
            "qr_token_hash": hash_qr_token("t"),
            "status": TicketStatus.ACTIVE,
            "expires_at": NOW + timedelta(hours=12),
        }
        defaults.update(overrides)
        return Ticket(**defaults)

    def test_an_active_ticket_redeems(self):
        ticket = self._ticket()
        ticket.redeem(now=NOW)
        assert ticket.status is TicketStatus.REDEEMED
        assert ticket.redeemed_at == NOW

    def test_a_ticket_cannot_be_redeemed_twice(self):
        ticket = self._ticket()
        ticket.redeem(now=NOW)
        with pytest.raises(ConflictError):
            ticket.redeem(now=NOW)

    def test_an_expired_ticket_cannot_be_redeemed(self):
        ticket = self._ticket(expires_at=NOW - timedelta(minutes=1))
        with pytest.raises(TicketExpiredError):
            ticket.redeem(now=NOW)

    def test_expiry_is_evaluated_against_the_passed_clock(self):
        ticket = self._ticket()
        assert ticket.is_redeemable(now=NOW)
        assert not ticket.is_redeemable(now=NOW + timedelta(hours=13))

    def test_a_redeemed_ticket_cannot_be_revoked(self):
        # Revoking after the fact would be a way to deny someone was served.
        ticket = self._ticket()
        ticket.redeem(now=NOW)
        with pytest.raises(ConflictError):
            ticket.revoke(now=NOW)

    def test_an_active_ticket_can_be_revoked(self):
        ticket = self._ticket()
        ticket.revoke(now=NOW)
        assert ticket.status is TicketStatus.REVOKED
