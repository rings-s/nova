"""call_center domain: the keypad, the caller's code, the turn cap. Pure — no database."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.call_center.domain import (
    CODE_TTL,
    Call,
    CallDirection,
    CallOutcome,
    CallPurpose,
    CodeCheck,
    KeypadAction,
    answer_key,
    code_digest,
    heard_clearly,
    new_code,
    spoken_time,
    validate_line,
    within_calling_hours,
)
from app.modules.call_center.exceptions import CallEndedError

NOW = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
KEY = "test-key"


def _call(**overrides) -> Call:
    values = {
        "tenant_id": uuid4(),
        "line_id": uuid4(),
        "business_id": uuid4(),
        "direction": CallDirection.INBOUND,
        "purpose": CallPurpose.CONVERSATION,
        "started_at": NOW,
    }
    return Call(**{**values, **overrides})


def _reminder() -> Call:
    return Call.outbound_reminder(
        tenant_id=uuid4(),
        line_id=uuid4(),
        business_id=uuid4(),
        booking_id=uuid4(),
        customer_id=uuid4(),
        phone="+966500000001",
        now=NOW,
    )


def test_one_books_the_held_time_and_two_cancels_only_for_a_verified_caller():
    call = _call()
    assert call.keypad("1", now=NOW) is KeypadAction.CONFIRM_HOLD

    call.offer_cancellation(uuid4())
    # Caller ID can be forged: an unverified caller cannot cancel by keypad.
    assert call.keypad("2", now=NOW) is KeypadAction.UNKNOWN
    call.verified_at = NOW
    assert call.keypad("2", now=NOW) is KeypadAction.CONFIRM_CANCELLATION
    assert call.keypad("9", now=NOW) is KeypadAction.UNKNOWN


def test_a_cancellation_is_taken_once():
    call = _call(verified_at=NOW)
    booking_id = uuid4()
    call.offer_cancellation(booking_id)
    assert call.take_cancellation() == booking_id
    assert call.take_cancellation() is None
    assert call.keypad("2", now=NOW) is KeypadAction.UNKNOWN


def test_three_sends_the_details_of_the_booking_just_made_once():
    call = _call()
    # Nothing offered: 3 means nothing.
    assert call.keypad("3", now=NOW) is KeypadAction.UNKNOWN

    booking_id = uuid4()
    call.offer_details(booking_id)
    assert call.keypad("3", now=NOW) is KeypadAction.SEND_DETAILS
    assert call.take_details_offer() == booking_id
    assert call.take_details_offer() is None
    assert call.keypad("3", now=NOW) is KeypadAction.UNKNOWN


def test_a_reminder_asks_its_own_question_first():
    call = _reminder()
    assert call.verified, "a reminder rang the number on file"
    assert call.keypad("1", now=NOW) is KeypadAction.KEEP_APPOINTMENT
    assert call.keypad("2", now=NOW) is KeypadAction.TALK_TO_SARA
    call.answer_reminder()
    # After that, 1 is the ordinary "book it".
    assert call.keypad("1", now=NOW) is KeypadAction.CONFIRM_HOLD


def test_the_code_verifies_once_and_only_the_right_one():
    call = _call()
    code = new_code()
    assert len(code) == 4 and code.isdigit()
    call.issue_code(code_digest(code, key=KEY, call_id=call.id), now=NOW)
    assert call.awaiting_code(NOW)
    assert call.keypad(code, now=NOW) is KeypadAction.VERIFICATION_CODE

    wrong = "0000" if code != "0000" else "1111"
    assert call.check_code(code_digest(wrong, key=KEY, call_id=call.id), now=NOW) is (
        CodeCheck.WRONG
    )
    assert not call.verified
    assert call.check_code(code_digest(code, key=KEY, call_id=call.id), now=NOW) is (
        CodeCheck.VERIFIED
    )
    assert call.verified
    # Spent: the same code proves nothing a second time.
    assert call.check_code(code_digest(code, key=KEY, call_id=call.id), now=NOW) is (
        CodeCheck.SPENT
    )


def test_three_wrong_codes_spend_it():
    call = _call()
    call.issue_code(code_digest("1234", key=KEY, call_id=call.id), now=NOW)
    results = [
        call.check_code(code_digest("9999", key=KEY, call_id=call.id), now=NOW) for _ in range(3)
    ]
    assert results == [CodeCheck.WRONG, CodeCheck.WRONG, CodeCheck.SPENT]
    # Even the right one, now.
    right = code_digest("1234", key=KEY, call_id=call.id)
    assert call.check_code(right, now=NOW) is CodeCheck.SPENT
    assert not call.verified


def test_an_expired_code_is_spent():
    call = _call()
    call.issue_code(code_digest("1234", key=KEY, call_id=call.id), now=NOW)
    later = NOW + CODE_TTL + timedelta(seconds=1)
    assert call.check_code(code_digest("1234", key=KEY, call_id=call.id), now=later) is (
        CodeCheck.SPENT
    )


def test_a_code_is_bound_to_its_call():
    """The same four digits hash differently on another call."""
    assert code_digest("1234", key=KEY, call_id=uuid4()) != code_digest(
        "1234", key=KEY, call_id=uuid4()
    )


def test_the_turn_cap_ends_the_call():
    call = _call()
    assert call.begin_turn(now=NOW, max_turns=2)
    assert call.begin_turn(now=NOW, max_turns=2)
    assert not call.begin_turn(now=NOW, max_turns=2)
    assert call.ended
    assert call.outcome is CallOutcome.TURN_LIMIT
    with pytest.raises(CallEndedError):
        call.begin_turn(now=NOW, max_turns=2)


def test_a_retried_delivery_is_recognised():
    call = _call()
    key = answer_key(b'{"speech": "hello"}')
    assert not call.is_repeat(key)
    call.remember(key, "Hello!")
    assert call.is_repeat(key)
    assert not call.is_repeat(answer_key(b'{"speech": "hello again"}'))


def test_unsure_speech_is_asked_for_again_rather_than_guessed_at():
    assert heard_clearly("أبي موعد", 0.9, minimum=0.3)
    assert not heard_clearly("أبي موعد", 0.1, minimum=0.3)
    assert heard_clearly("أبي موعد", None, minimum=0.3), "no score: the text is trusted"
    assert heard_clearly("أبي موعد", 0.1, minimum=0.0), "0 switches the check off"
    assert not heard_clearly("", 0.9, minimum=0.3)


def test_a_booking_outranks_a_later_outcome_but_not_a_cancellation():
    call = _call()
    booking_id = uuid4()
    call.record(CallOutcome.BOOKED, booking_id=booking_id)
    call.record(CallOutcome.QUEUED)
    assert call.outcome is CallOutcome.BOOKED
    assert call.booking_id == booking_id
    call.record(CallOutcome.CANCELLED)
    assert call.outcome is CallOutcome.CANCELLED


def test_a_line_needs_an_e164_number_and_a_language_sara_speaks():
    validate_line(number_e164="+966800123456", locale="ar")
    with pytest.raises(ValidationDomainError):
        validate_line(number_e164="0500000000", locale="ar")
    with pytest.raises(ValidationDomainError):
        validate_line(number_e164="+966800123456", locale="fr")


def test_times_are_said_in_the_branchs_clock():
    moment = datetime(2026, 10, 22, 13, 30, tzinfo=UTC)  # 16:30 in Riyadh, a Thursday
    assert spoken_time(moment, timezone="Asia/Riyadh", locale="en") == "Thursday at 16:30"
    assert spoken_time(moment, timezone="Asia/Riyadh", locale="ar") == (
        "يوم الخميس الساعة أربع ونص العصر"
    )


def test_calls_ring_only_in_the_branchs_daytime():
    morning = datetime(2026, 10, 22, 7, 0, tzinfo=UTC)  # 10:00 in Riyadh
    night = datetime(2026, 10, 22, 19, 0, tzinfo=UTC)  # 22:00 in Riyadh
    assert within_calling_hours(morning, timezone="Asia/Riyadh", start_hour=10, end_hour=21)
    assert not within_calling_hours(night, timezone="Asia/Riyadh", start_hour=10, end_hour=21)
