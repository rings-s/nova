"""call_center · DOMAIN layer — a phone call Sara answers or places (ADR-0017).

Pure: no framework, no database. `Call` is a rich entity because a call can be
in an invalid state (a code checked after it expired, a keypress after the
call ended), and the repository maps it to `VoiceCallRecord`.

What the keypad means is decided here, never by the model. The model hears
words; a key is the caller's own hand on their phone, the voice channel's
stand-in for the app's "Yes, book it" button (ADR-0015):

    1   books the time Sara is holding
    2   cancels the booking Sara offered to cancel (a verified caller only)
    3   after a booking: yes, send its details on WhatsApp. The caller's own
        consent to WhatsApp, which a record opened from a call starts without
    a 4-digit code, when one was sent: proves the caller holds the
        customer's phone, because caller ID can be forged

A reminder call asks one question first: 1 keeps the appointment, 2 talks to
Sara, and after that the call is an ordinary conversation.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.core.exceptions import ValidationDomainError
from app.core.spoken import saudi_time
from app.modules.call_center.exceptions import CallEndedError


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallPurpose(StrEnum):
    CONVERSATION = "conversation"
    REMINDER = "reminder"


class CallStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    ENDED = "ended"


class CallOutcome(StrEnum):
    """What the call achieved, for the business's call log."""

    BOOKED = "booked"
    QUEUED = "queued"
    CANCELLED = "cancelled"
    CALLBACK_REQUESTED = "callback_requested"
    REMINDER_KEPT = "reminder_kept"
    TURN_LIMIT = "turn_limit"
    UNAVAILABLE = "unavailable"
    #: A reminder call no one answered with a key: unanswered, voicemail, or
    #: hung up during the reminder (`CallSweeper.end_abandoned`).
    NO_ANSWER = "no_answer"


class CodeCheck(StrEnum):
    VERIFIED = "verified"
    WRONG = "wrong"
    #: Expired, never sent, or out of attempts: a new code is needed.
    SPENT = "spent"


class KeypadAction(StrEnum):
    CONFIRM_HOLD = "confirm_hold"
    CONFIRM_CANCELLATION = "confirm_cancellation"
    SEND_DETAILS = "send_details"
    VERIFICATION_CODE = "verification_code"
    KEEP_APPOINTMENT = "keep_appointment"
    TALK_TO_SARA = "talk_to_sara"
    UNKNOWN = "unknown"


CODE_LENGTH = 4
CODE_TTL = timedelta(minutes=5)
MAX_CODE_ATTEMPTS = 3
#: A call link outlives any real call; past it, Unifonic's next POST is refused.
#: Every reply issues a fresh one, so a call idle this long can never go on:
#: the caller hung up, and the sweep ends it.
CALL_LINK_TTL = timedelta(hours=2)

LOCALES = frozenset({"ar", "en"})


def validate_line(*, number_e164: str, locale: str) -> None:
    if not number_e164.startswith("+") or not number_e164[1:].isdigit():
        raise ValidationDomainError(f"'{number_e164}' is not an E.164 number, e.g. +9665XXXXXXXX.")
    if locale not in LOCALES:
        raise ValidationDomainError(f"Sara speaks {sorted(LOCALES)}, not '{locale}'.")


def new_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def code_digest(code: str, *, key: str, call_id: UUID) -> str:
    """The code as stored: keyed and bound to one call, so a leaked row is no code."""
    return hmac.new(key.encode(), f"{call_id}:{code}".encode(), hashlib.sha256).hexdigest()


def heard_clearly(text: str, confidence: float | None, *, minimum: float) -> bool:
    """Whether recognised speech is worth a model turn. Unsure speech is asked
    for again, never guessed at: a mis-heard day becomes a wrong hold. No score
    reported, or a `minimum` of 0, trusts the text."""
    if not text:
        return False
    return confidence is None or confidence >= minimum


def answer_key(raw: bytes) -> str:
    """Identifies one webhook delivery, so a retried POST is answered, not re-run."""
    return hashlib.sha256(raw).hexdigest()


@dataclass
class Call:
    tenant_id: UUID
    line_id: UUID
    business_id: UUID
    direction: CallDirection
    purpose: CallPurpose
    started_at: datetime
    id: UUID = field(default_factory=uuid4)
    status: CallStatus = CallStatus.IN_PROGRESS
    gateway_call_id: str | None = None
    caller_e164: str | None = None
    customer_id: UUID | None = None
    booking_id: UUID | None = None
    turns: int = 0
    ended_at: datetime | None = None
    outcome: CallOutcome | None = None
    verified_at: datetime | None = None
    code_hash: str | None = None
    code_attempts: int = 0
    code_expires_at: datetime | None = None
    pending_cancellation_id: UUID | None = None
    #: The booking whose details Sara offered to send on WhatsApp (press 3).
    details_offer_booking_id: UUID | None = None
    reminder_answered: bool = False
    last_answer_key: str | None = None
    last_reply: str | None = None

    @classmethod
    def outbound_reminder(
        cls,
        tenant_id: UUID,
        line_id: UUID,
        business_id: UUID,
        booking_id: UUID,
        customer_id: UUID,
        phone: str,
        now: datetime,
    ) -> "Call":
        """A reminder rings the number on file, so whoever answers holds that phone."""
        return cls(
            tenant_id=tenant_id,
            line_id=line_id,
            business_id=business_id,
            direction=CallDirection.OUTBOUND,
            purpose=CallPurpose.REMINDER,
            started_at=now,
            caller_e164=phone,
            customer_id=customer_id,
            booking_id=booking_id,
            verified_at=now,
        )

    @property
    def ended(self) -> bool:
        return self.status is CallStatus.ENDED

    @property
    def verified(self) -> bool:
        return self.verified_at is not None

    def awaiting_code(self, now: datetime) -> bool:
        return (
            not self.verified
            and self.code_hash is not None
            and self.code_expires_at is not None
            and now < self.code_expires_at
            and self.code_attempts < MAX_CODE_ATTEMPTS
        )

    def awaiting_reminder_answer(self) -> bool:
        return self.purpose is CallPurpose.REMINDER and not self.reminder_answered

    def is_repeat(self, key: str) -> bool:
        """The same delivery again: Unifonic retried a POST we already answered."""
        return self.last_answer_key == key and self.last_reply is not None

    def remember(self, key: str | None, reply: str) -> None:
        self.last_answer_key = key
        self.last_reply = reply

    def begin_turn(self, *, now: datetime, max_turns: int) -> bool:
        """Counts a caller's turn. False, and the call ends, past the cap."""
        if self.ended:
            raise CallEndedError()
        self.turns += 1
        if self.turns > max_turns:
            self.end(CallOutcome.TURN_LIMIT, now=now)
            return False
        return True

    def keypad(self, digits: str, *, now: datetime) -> KeypadAction:
        """What the keys pressed mean in the call's present state."""
        if self.awaiting_reminder_answer():
            return {
                "1": KeypadAction.KEEP_APPOINTMENT,
                "2": KeypadAction.TALK_TO_SARA,
            }.get(digits, KeypadAction.UNKNOWN)
        if len(digits) == CODE_LENGTH and self.code_hash is not None and not self.verified:
            return KeypadAction.VERIFICATION_CODE
        if digits == "1":
            return KeypadAction.CONFIRM_HOLD
        if digits == "2" and self.pending_cancellation_id is not None and self.verified:
            return KeypadAction.CONFIRM_CANCELLATION
        if digits == "3" and self.details_offer_booking_id is not None:
            return KeypadAction.SEND_DETAILS
        return KeypadAction.UNKNOWN

    def answer_reminder(self) -> None:
        self.reminder_answered = True

    def issue_code(self, code_hash: str, *, now: datetime) -> None:
        """A fresh code replaces any earlier one, with a fresh set of attempts."""
        self.code_hash = code_hash
        self.code_attempts = 0
        self.code_expires_at = now + CODE_TTL

    def check_code(self, candidate_hash: str, *, now: datetime) -> CodeCheck:
        if not self.awaiting_code(now):
            return CodeCheck.SPENT
        self.code_attempts += 1
        if hmac.compare_digest(candidate_hash, self.code_hash or ""):
            self.verified_at = now
            self.code_hash = None
            self.code_expires_at = None
            return CodeCheck.VERIFIED
        return CodeCheck.WRONG if self.code_attempts < MAX_CODE_ATTEMPTS else CodeCheck.SPENT

    def offer_cancellation(self, booking_id: UUID) -> None:
        self.pending_cancellation_id = booking_id

    def take_cancellation(self) -> UUID | None:
        booking_id, self.pending_cancellation_id = self.pending_cancellation_id, None
        return booking_id

    def offer_details(self, booking_id: UUID) -> None:
        self.details_offer_booking_id = booking_id

    def take_details_offer(self) -> UUID | None:
        booking_id, self.details_offer_booking_id = self.details_offer_booking_id, None
        return booking_id

    def record(self, outcome: CallOutcome, *, booking_id: UUID | None = None) -> None:
        """What the call has achieved so far. A booking outranks what came before it."""
        if booking_id is not None:
            self.booking_id = booking_id
        if self.outcome is not CallOutcome.BOOKED or outcome is CallOutcome.CANCELLED:
            self.outcome = outcome

    def end(self, outcome: CallOutcome | None = None, *, now: datetime) -> None:
        if outcome is not None:
            self.outcome = outcome
        self.status = CallStatus.ENDED
        self.ended_at = self.ended_at or now


_WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def spoken_time(
    moment: datetime, *, timezone: str, locale: str, now: datetime | None = None
) -> str:
    """A time as Sara says it, in the branch's own clock: "بكرة الساعة أربع ونص العصر"."""
    if locale == "ar":
        return saudi_time(moment, timezone=timezone, now=now)
    local = moment.astimezone(ZoneInfo(timezone))
    return f"{_WEEKDAYS_EN[local.weekday()]} at {local:%H:%M}"


def within_calling_hours(now: datetime, *, timezone: str, start_hour: int, end_hour: int) -> bool:
    """Whether a call may ring now in the customer's local day."""
    return start_hour <= now.astimezone(ZoneInfo(timezone)).hour < end_hour
