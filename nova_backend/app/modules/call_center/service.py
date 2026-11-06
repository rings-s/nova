"""call_center · APPLICATION layer — Sara on the phone (ADR-0017).

A call is a loop of webhook turns (`integrations/voice/unifonic.py`): Unifonic
asks what to say, Sara answers, Unifonic sends back what the caller said or
pressed. This service runs one turn in three steps, so no database connection
is held while the model thinks:

    begin_answer    the call row, locked: repeat delivery, turn cap, keypad.
                    A key never reaches the model.
    converse        Sara's turn, through `AiChatService` (ai_agents), which
                    opens a unit of work per tool call. No session here.
    finish_answer   the call row again: what the turn produced (a booking, a
                    queue place, a cancellation to confirm, a code to send),
                    and the words to say, with what to press.

The router commits between them. A turn is answered even when the model is
not: a timeout asks the caller to say it again.

Whenever Sara tells a caller someone from the business will call them, a
follow-up opens in the business's inbox (`support`) in the same transaction,
with the caller's number and why. Saying it without opening one is the bug
this rule exists to prevent.

Who is calling: a phone number, which can be forged. It finds the customer
record to book for, and nothing more until the caller types the code Sara
sends to that customer's WhatsApp (`Call.check_code`). A reminder call rang
the number on file, so it starts verified.

Every link Unifonic is given is a credential, because Unifonic calls it with no
Authorization header: a line's URL is signed with the line's `token_version`,
and each turn's URL is a purpose token naming the call, with the tenant in the
path. A forged or expired one answers 404 (`CallNotFoundError`).
"""

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.events import publish_event
from app.core.exceptions import DomainError
from app.core.rate_limit import RateLimiter, RateLimitPolicy, get_rate_limiter
from app.core.security import (
    AuthenticationError,
    Principal,
    PrincipalKind,
    decode_purpose_token,
    issue_purpose_token,
    purpose_key,
)
from app.core.spoken import speakable
from app.core.validators import validate_gcc_phone
from app.integrations.base import IntegrationNotConfiguredError
from app.integrations.voice.speech import AudioStore, SpeechSynthesizer, audio_key
from app.integrations.voice.unifonic import VoiceGateway, VoiceGatewayError, VoiceReply
from app.integrations.whatsapp.client import WhatsAppClient
from app.modules.ai_agents.service import AiChatService, ChatTurn
from app.modules.billing.service import BillingService
from app.modules.booking.service import BookingService, BookingStatus
from app.modules.call_center.domain import (
    CALL_LINK_TTL,
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
from app.modules.call_center.events import BookingDetailsRequested, CallbackRequested
from app.modules.call_center.exceptions import (
    CallNotFoundError,
    PhoneLineNotFoundError,
    PhoneNumberTakenError,
)
from app.modules.call_center.models import PhoneLineRecord
from app.modules.call_center.repository import (
    PhoneLineRepository,
    UnscopedCallRepository,
    VoiceCallRepository,
)
from app.modules.catalog.service import CatalogService
from app.modules.identity.domain import ConsentSource
from app.modules.identity.service import CustomerService
from app.modules.support.domain import FollowUpReason
from app.modules.support.service import SupportService

logger = logging.getLogger(__name__)

#: The plan feature that switches Sara on (docs/11 section 2).
CALL_CENTER_FEATURE = "ai_call_center"
#: The agent that answers a line unless the line names another voice agent.
DEFAULT_AGENT = "call_center_agent"

LINE_PURPOSE = "voice_line"
CALL_PURPOSE = "voice_call"
CODE_PURPOSE = "voice_code"
AUDIO_PURPOSE = "voice_audio"
_AUDIO_KEY = re.compile(r"^[0-9a-f]{64}$")
#: Less time than this left in a turn, and Sara's voice is not even asked:
#: a clip that misses the deadline is a wait for nothing.
MIN_SPEECH_SECONDS = 0.5
#: The WhatsApp template carrying the caller's code. To be approved with the BSP.
CODE_TEMPLATE = "call_verification_code"
#: Codes sent to one number. Caller ID can be forged, and each fresh code
#: brings fresh guesses (`MAX_CODE_ATTEMPTS`): without a cap, a caller using
#: someone else's number could ask for code after code, call after call, until
#: a guess landed, and every code is a paid WhatsApp message to that number.
#: Keyed by the number, not the call or the business, so neither hanging up
#: nor calling another salon resets it: at most 18 guesses a day at 1 in 10,000.
CODE_POLICIES = (
    RateLimitPolicy(limit=3, window_seconds=60 * 60),
    RateLimitPolicy(limit=6, window_seconds=24 * 60 * 60),
)
#: Reminders go out at least this long before the booking: a call minutes
#: before the appointment reminds nobody of anything.
REMINDER_LEAD = timedelta(hours=2)

#: What a key press says to the model when it confirms the held time.
_PRESSED_ONE = {"ar": "ضغطت واحد، أكدوا لي الحجز.", "en": "I pressed 1: book it."}

#: Everything Sara says that the model does not write. Arabic is the Saudi
#: dialect, in the polite plural (تبون، اضغطوا) that fits any caller.
_SAY = {
    "greeting": {
        "ar": "حياكم الله، معكم سارة من {business}. كيف أقدر أخدمكم؟",
        "en": "Hello, this is Sara at {business}. How can I help you?",
    },
    "closed": {
        "ar": "حياكم الله في {business}. المعذرة، ما نقدر نستقبل مكالمات الحين، "
        "وتقدرون تحجزون من التطبيق.",
        "en": "Hello, this is {business}. We can't take calls right now; please book in the app.",
    },
    "again": {
        "ar": "المعذرة، ما وضح لي الكلام. ممكن تعيدونه؟",
        "en": "Sorry, I didn't catch that. Could you say it again?",
    },
    "goodbye": {
        "ar": "تشرفنا باتصالكم، في أمان الله.",
        "en": "Thank you for calling. Goodbye.",
    },
    "press_to_book": {
        "ar": "إذا تبون أأكد لكم الحجز اضغطوا واحد.",
        "en": "To book it, press 1.",
    },
    "press_to_cancel": {
        "ar": "وإذا تبون نلغي الموعد اضغطوا اثنين.",
        "en": "To cancel it, press 2.",
    },
    "code_sent": {
        "ar": "أرسلت لكم رمز من أربعة أرقام على الواتساب، اكتبوه بلوحة الأرقام.",
        "en": "I sent a four-digit code to your WhatsApp; type it on the keypad.",
    },
    "code_unsent": {
        "ar": "المعذرة، ما قدرت أرسل لكم الرمز الحين، وبيتواصل معكم أحد من المحل إن شاء الله.",
        "en": "I couldn't send you a code just now. Someone from the business will call you.",
    },
    "code_limit": {
        "ar": "المعذرة، ما أقدر أرسل لكم رمز ثاني الحين. جربوا بعدين إن شاء الله.",
        "en": "I can't send you another code right now. Please try again later.",
    },
    "verified": {
        "ar": "أبشروا، تم التحقق. وش تبون تعرفون عن مواعيدكم؟",
        "en": "Thank you, you're verified. What would you like to know about your bookings?",
    },
    "code_wrong": {
        "ar": "الرمز مو صحيح، جربوا مرة ثانية.",
        "en": "That code isn't right. Please try again.",
    },
    "code_spent": {
        "ar": "ما قدرت أتحقق من الرمز. إذا تبون أرسل لكم رمز جديد قولوا لي.",
        "en": "I couldn't verify that code. I can send you a new one if you like.",
    },
    "cancelled": {"ar": "أبشروا، انلغى موعدكم.", "en": "Your booking is cancelled."},
    "not_cancelled": {
        "ar": "المعذرة، ما قدرت ألغي الموعد، وبيتواصل معكم أحد من المحل إن شاء الله.",
        "en": "I couldn't cancel that booking. Someone from the business will call you.",
    },
    "offer_details": {
        "ar": "تبون نرسل لكم تفاصيل الحجز على الواتساب؟ اضغطوا ثلاثة.",
        "en": "To get the booking details on WhatsApp, press 3.",
    },
    "details_sent": {
        "ar": "بنرسل لكم تفاصيل الحجز على الواتساب الحين.",
        "en": "We'll send the booking details to your WhatsApp now.",
    },
    "callback": {
        # No «أبشروا»: this often follows a complaint, where good cheer jars.
        "ar": "بيتواصل معكم أحد من المحل قريب إن شاء الله.",
        "en": "Someone from the business will call you back soon.",
    },
    "reminder": {
        "ar": "حياكم الله{name}، معكم سارة من {business}. حبيت أذكركم بموعد {service} {time}. "
        "للتأكيد اضغطوا واحد، ولو تبون تكلموني اضغطوا اثنين.",
        "en": "Hello{name}, this is Sara from {business}, reminding you of your {service} "
        "{time}. Press 1 to keep it, or 2 to talk to me.",
    },
    "reminder_kept": {
        "ar": "أبشروا، ننتظركم في موعدكم. في أمان الله.",
        "en": "Great, see you then. Goodbye.",
    },
    "talk": {"ar": "تفضلوا، كيف أقدر أخدمكم؟", "en": "Of course. How can I help?"},
}


def _say(key: str, locale: str, **values: str) -> str:
    texts = _SAY[key]
    return texts.get(locale, texts["en"]).format(**values)


class SaraVoice:
    """Sara's own voice (`integrations/voice/speech.py`): each reply as a clip
    Unifonic plays from a URL we host, generated once per voice and wording.

    Never in the way: no synthesiser, a failure, a timeout, a language the
    voice does not speak, or a clip that could not be stored leaves the reply
    as text, which Unifonic reads.
    """

    def __init__(
        self,
        synthesizer: SpeechSynthesizer | None,
        store: AudioStore,
        secret_key: str,
        ttl_seconds: int,
    ) -> None:
        self.synthesizer = synthesizer
        self.store = store
        self._key = purpose_key(secret_key, AUDIO_PURPOSE)
        self.ttl_seconds = ttl_seconds

    async def speak(
        self, reply: VoiceReply, *, base_url: str, deadline: float | None = None
    ) -> VoiceReply:
        """`deadline` (`time.monotonic()`) is when the caller's turn runs out:
        speech that cannot be made before it is left to Unifonic's voice."""
        if self.synthesizer is None:
            return reply
        key = audio_key(reply.say, voice=self.synthesizer.identity, secret=self._key)
        if await self.store.get(key) is None:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining < MIN_SPEECH_SECONDS:
                logger.info("voice_tts_skipped_for_time", extra={"seconds_left": remaining})
                return reply
            audio = await self.synthesizer.synthesize(
                reply.say, locale=reply.locale, timeout_seconds=remaining
            )
            # A clip that was not kept would be a link to a 404: silence on the line.
            if audio is None or not await self.store.put(key, audio, self.ttl_seconds):
                return reply
        url = f"{base_url.rstrip('/')}/api/v1/webhooks/voice/audio/{key}.wav"
        return replace(reply, audio_url=url)

    async def clip(self, key: str) -> bytes | None:
        """A clip by its key, or None: unknown, expired, or not a key at all."""
        if not _AUDIO_KEY.match(key):
            return None
        return await self.store.get(key)


@dataclass(frozen=True)
class LineSetup:
    line: PhoneLineRecord
    #: The URL to paste into the number's inbound application in Unifonic.
    answer_url: str


@dataclass(frozen=True)
class ReminderPlan:
    """A reminder call saved by `prepare_reminder`, for `dial_reminder` to ring."""

    call_id: UUID
    to: str
    caller_id: str
    reply: VoiceReply


@dataclass(frozen=True)
class DialOutcome:
    """Whether a reminder may have rung, and Unifonic's id for it when known."""

    placed: bool
    gateway_call_id: str | None = None


@dataclass(frozen=True)
class AnswerPlan:
    """What `begin_answer` decided. `reply` set: say it, no model. Otherwise converse."""

    call_id: UUID
    key: str
    locale: str
    reply: VoiceReply | None = None
    message: str | None = None
    confirm_latest_offer: bool = False
    customer_id: UUID | None = None
    business_id: UUID | None = None
    agent_name: str = DEFAULT_AGENT
    verified: bool = False


class CallCenterService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        lines: PhoneLineRepository,
        calls: VoiceCallRepository,
        customers: CustomerService,
        bookings: BookingService,
        catalog: CatalogService,
        billing: BillingService,
        support: SupportService,
        gateway: VoiceGateway,
        whatsapp: WhatsAppClient,
        secret_key: str,
        max_turns: int,
        min_speech_confidence: float = 0.0,
        chat: AiChatService | None = None,
        voice: SaraVoice | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.lines = lines
        self.calls = calls
        self.customers = customers
        self.bookings = bookings
        self.catalog = catalog
        self.billing = billing
        self.support = support
        self.gateway = gateway
        self.whatsapp = whatsapp
        self.secret_key = secret_key
        self.max_turns = max_turns
        #: Speech Unifonic recognised with less confidence is asked for again.
        self.min_speech_confidence = min_speech_confidence
        #: Sara's turns. None where nothing converses (the worker's reminders).
        self.chat = chat
        #: Her own voice. None: Unifonic's text-to-speech reads every reply.
        self.voice = voice
        #: Counts the codes sent to each number (`CODE_POLICIES`).
        self.limiter = limiter or get_rate_limiter()

    async def speak(
        self, reply: VoiceReply, *, base_url: str, deadline: float | None = None
    ) -> VoiceReply:
        """The reply as it is read aloud (`speakable`), in Sara's voice when one
        is configured, made before `deadline` or not at all. Every reply passes
        here, so Unifonic's voice reads the same words hers would. Holds no
        session: the router calls it after committing, so no transaction waits."""
        reply = replace(reply, say=speakable(reply.say, locale=reply.locale))
        if self.voice is None:
            return reply
        return await self.voice.speak(reply, base_url=base_url, deadline=deadline)

    # --- links ------------------------------------------------------------

    def _line_signature(self, line: PhoneLineRecord) -> str:
        message = f"{line.tenant_id}:{line.id}:{line.token_version}".encode()
        key = purpose_key(self.secret_key, LINE_PURPOSE).encode()
        return hmac.new(key, message, hashlib.sha256).hexdigest()[:32]

    def line_token(self, line: PhoneLineRecord) -> str:
        """`{line_id}.{signature}`: long-lived, revoked by `rotate_line`."""
        return f"{line.id}.{self._line_signature(line)}"

    def answer_url(self, line: PhoneLineRecord, base_url: str) -> str:
        token = self.line_token(line)
        return f"{base_url.rstrip('/')}/api/v1/webhooks/voice/{self.tenant_id}/lines/{token}"

    def _listen_url(self, call_id: UUID, base_url: str) -> str:
        token = issue_purpose_token(
            subject_id=call_id,
            purpose=CALL_PURPOSE,
            secret=self.secret_key,
            ttl_seconds=int(CALL_LINK_TTL.total_seconds()),
        )
        return f"{base_url.rstrip('/')}/api/v1/webhooks/voice/{self.tenant_id}/calls/{token}"

    def call_id_from(self, call_token: str) -> UUID:
        """The call a turn link names. Forged, expired or another purpose: 404."""
        try:
            claims = decode_purpose_token(call_token, purpose=CALL_PURPOSE, secret=self.secret_key)
            return UUID(str(claims["sub"]))
        except (AuthenticationError, KeyError, ValueError):
            raise CallNotFoundError() from None

    async def _line_for(self, line_token: str) -> PhoneLineRecord:
        line_id, _, signature = line_token.partition(".")
        try:
            line = await self.lines.get(UUID(line_id))
        except ValueError:
            line = None
        if (
            line is None
            or not line.is_active
            or not hmac.compare_digest(signature, self._line_signature(line))
        ):
            raise PhoneLineNotFoundError(line_id)
        return line

    # --- lines ------------------------------------------------------------

    async def provision_line(
        self,
        business_id: UUID,
        number_e164: str,
        locale: str,
        base_url: str,
        agent_name: str = DEFAULT_AGENT,
    ) -> LineSetup:
        """A Unifonic number for one business. The number is bought in Unifonic's console."""
        validate_line(number_e164=number_e164, locale=locale)
        await self.catalog.get_business(business_id)
        if await self.lines.number_in_use(number_e164):
            raise PhoneNumberTakenError(number_e164)
        line = PhoneLineRecord(
            tenant_id=self.tenant_id,
            business_id=business_id,
            number_e164=number_e164,
            locale=locale,
            agent_name=agent_name,
            is_active=True,
            token_version=0,
        )
        self.lines.add(line)
        await self.session.flush()
        return LineSetup(line=line, answer_url=self.answer_url(line, base_url))

    async def rotate_line(self, line_id: UUID, *, base_url: str) -> LineSetup:
        """A new URL for the line; the old one stops answering at once."""
        line = await self.lines.get(line_id)
        if line is None:
            raise PhoneLineNotFoundError(line_id)
        line.token_version += 1
        await self.session.flush()
        return LineSetup(line=line, answer_url=self.answer_url(line, base_url))

    async def list_lines(self) -> list[PhoneLineRecord]:
        return await self.lines.list_all()

    async def recent_calls(self, *, limit: int = 50, offset: int = 0) -> list[Call]:
        return await self.calls.recent(limit=limit, offset=offset)

    # --- an inbound call ----------------------------------------------------

    async def answer(
        self, line_token: str, params: dict[str, str], *, base_url: str, now: datetime
    ) -> VoiceReply:
        """The first thing Sara says when the line rings, and the call it starts."""
        line = await self._line_for(line_token)
        incoming = self.gateway.parse_incoming(params)
        if incoming.gateway_call_id is not None:
            existing = await self.calls.by_gateway_id(incoming.gateway_call_id)
            if existing is not None and existing.last_reply is not None:
                # Unifonic asked twice for the same call: the same greeting, and
                # for a call that already ended (a closed business), no listening.
                return self._reply(existing, existing.last_reply, line.locale, base_url)

        business = await self.catalog.get_business(line.business_id)
        name = business.name_ar if line.locale == "ar" else business.name_en
        call = Call(
            tenant_id=self.tenant_id,
            line_id=line.id,
            business_id=line.business_id,
            direction=CallDirection.INBOUND,
            purpose=CallPurpose.CONVERSATION,
            started_at=now,
            gateway_call_id=incoming.gateway_call_id,
            caller_e164=incoming.caller,
        )
        try:
            # A locked business, or a plan without Sara: a polite no, not a ring-out.
            await self.billing.require_feature(line.business_id, CALL_CENTER_FEATURE)
        except DomainError:
            call.end(CallOutcome.UNAVAILABLE, now=now)
            reply = _say("closed", line.locale, business=name)
            call.remember(None, reply)
            await self.calls.add_call(call)
            return VoiceReply(reply, line.locale)

        call.customer_id = await self._customer_for(incoming.caller)
        reply = _say("greeting", line.locale, business=name)
        call.remember(None, reply)
        await self.calls.add_call(call)
        return VoiceReply(reply, line.locale, self._listen_url(call.id, base_url))

    async def _customer_for(self, caller: str | None) -> UUID | None:
        """The customer record a call books for: found by the caller's number, or
        opened for it. Booking only; reading needs the code (`Call.check_code`)."""
        if not caller:
            return None
        try:
            validate_gcc_phone(caller, self.customers.allowed_phone_country_codes)
        except DomainError:
            return None
        customer = await self.customers.find_by_phone(caller)
        if customer is None:
            customer = await self.customers.create(
                full_name=caller, phone=caller, notes="Opened by Sara from a phone call."
            )
        return customer.id

    # --- one turn -----------------------------------------------------------

    async def begin_answer(
        self, call_id: UUID, payload: dict, raw: bytes, *, base_url: str, now: datetime
    ) -> AnswerPlan:
        """Everything about a turn that needs no model, decided under the call's lock."""
        call = await self.calls.get_call(call_id, for_update=True)
        if call is None:
            raise CallNotFoundError()
        line = await self.lines.get(call.line_id)
        locale = line.locale if line is not None else "ar"
        key = answer_key(raw)

        def said(reply: VoiceReply) -> AnswerPlan:
            return AnswerPlan(call_id, key, locale, reply=reply)

        if call.is_repeat(key):
            return said(self._reply(call, call.last_reply or "", locale, base_url))
        if call.ended:
            return said(VoiceReply(_say("goodbye", locale), locale))
        if not call.begin_turn(now=now, max_turns=self.max_turns):
            # This long without being helped: a person calls them back.
            await self._promise_callback(call, FollowUpReason.CALL_TOO_LONG)
            text = f"{_say('callback', locale)} {_say('goodbye', locale)}"
            return said(await self._save_reply(call, key, text, locale, base_url))

        answer = self.gateway.parse_answer(payload)
        if answer.digits:
            action = call.keypad(answer.digits, now=now)
            if action is KeypadAction.CONFIRM_HOLD:
                await self.calls.save_call(call)
                return self._converse(call, key, locale, line, _PRESSED_ONE[locale], confirm=True)
            text = await self._on_keys(call, action, answer.digits, locale, now)
            if action is KeypadAction.KEEP_APPOINTMENT:
                call.end(now=now)
            return said(await self._save_reply(call, key, text, locale, base_url))
        if not heard_clearly(answer.text, answer.confidence, minimum=self.min_speech_confidence):
            if answer.text:
                # Counted, never logged: the words are the caller's.
                metrics.count("nova_voice_unclear_speech_total")
            text = _say("again", locale)
            return said(await self._save_reply(call, key, text, locale, base_url))
        # The calls lock is released when the router commits, before the model runs.
        await self.calls.save_call(call)
        return self._converse(call, key, locale, line, answer.text, confirm=False)

    def _converse(
        self,
        call: Call,
        key: str,
        locale: str,
        line: PhoneLineRecord | None,
        message: str,
        confirm: bool,
    ) -> AnswerPlan:
        return AnswerPlan(
            call.id,
            key,
            locale,
            message=message,
            confirm_latest_offer=confirm,
            customer_id=call.customer_id,
            business_id=call.business_id,
            agent_name=line.agent_name if line is not None else DEFAULT_AGENT,
            verified=call.verified,
        )

    async def _on_keys(
        self, call: Call, action: KeypadAction, digits: str, locale: str, now: datetime
    ) -> str:
        if action is KeypadAction.KEEP_APPOINTMENT:
            call.answer_reminder()
            call.record(CallOutcome.REMINDER_KEPT)
            return _say("reminder_kept", locale)
        if action is KeypadAction.TALK_TO_SARA:
            call.answer_reminder()
            return _say("talk", locale)
        if action is KeypadAction.VERIFICATION_CODE:
            digest = code_digest(digits, key=self._code_key(), call_id=call.id)
            result = call.check_code(digest, now=now)
            return _say(
                {
                    CodeCheck.VERIFIED: "verified",
                    CodeCheck.WRONG: "code_wrong",
                    CodeCheck.SPENT: "code_spent",
                }[result],
                locale,
            )
        if action is KeypadAction.SEND_DETAILS:
            booking_id = call.take_details_offer()
            if booking_id is None or call.customer_id is None:  # pragma: no cover
                return _say("again", locale)
            # The caller's own key, as for 1 and 2: their consent, not staff's.
            # Caller ID could be forged, so this is consent for the number on
            # file to get the business's transactional messages, nothing more.
            await self.customers.update_consent(
                call.customer_id, source=ConsentSource.CUSTOMER, by=None, whatsapp_consent=True
            )
            await self._send_details(call, booking_id)
            return _say("details_sent", locale)
        if action is KeypadAction.CONFIRM_CANCELLATION:
            booking_id = call.take_cancellation()
            if booking_id is None:  # pragma: no cover - `keypad` checked it
                return _say("again", locale)
            try:
                # The customer's own cancellation, under the business's policy.
                await self.bookings.cancel(booking_id, reason="Cancelled by phone, with Sara.")
            except DomainError as exc:
                logger.info("voice_cancel_refused", extra={"code": exc.code})
                await self._promise_callback(
                    call,
                    FollowUpReason.CANCELLATION_FAILED,
                    summary=f"Pressed 2 to cancel; refused: {exc.message} ({exc.code})",
                    booking_id=booking_id,
                )
                return _say("not_cancelled", locale)
            call.record(CallOutcome.CANCELLED)
            return _say("cancelled", locale)
        return _say("again", locale)

    async def _save_reply(
        self, call: Call, key: str, text: str, locale: str, base_url: str
    ) -> VoiceReply:
        """Remembers the answer for a retried delivery, saves the call, and says it."""
        call.remember(key, text)
        await self.calls.save_call(call)
        return self._reply(call, text, locale, base_url)

    def _reply(self, call: Call, text: str, locale: str, base_url: str) -> VoiceReply:
        """Then listen for the caller, unless the call has ended."""
        if call.ended:
            return VoiceReply(text, locale)
        return VoiceReply(text, locale, self._listen_url(call.id, base_url))

    async def converse(self, plan: AnswerPlan) -> ChatTurn:
        """Sara's turn. Holds no session: each tool call opens its own."""
        if self.chat is None:  # pragma: no cover - wiring
            raise RuntimeError("This call center was built without a chat service.")
        return await self.chat.chat(
            message=plan.message or "",
            session_id=str(plan.call_id),
            # The call is the principal: its own conversation memory, and staff-
            # side booking for the named customer, as reception books.
            principal=Principal(subject_id=plan.call_id, kind=PrincipalKind.SERVICE),
            customer_id=plan.customer_id,
            self_service=False,
            business_id=plan.business_id,
            locale=plan.locale,
            agent_name=plan.agent_name,
            voice=True,
            caller_verified=plan.verified,
            confirm_latest_offer=plan.confirm_latest_offer,
        )

    async def finish_answer(
        self, plan: AnswerPlan, turn: ChatTurn | None, *, base_url: str, now: datetime
    ) -> VoiceReply:
        """Records what Sara's turn did and says it, with what to press next.

        `turn` is None when the model could not be asked at all (busy, or a
        locked plan mid-call): the caller is asked to say it again.
        """
        call = await self.calls.get_call(plan.call_id, for_update=True)
        if call is None:  # pragma: no cover - it was there a moment ago
            raise CallNotFoundError()
        locale = plan.locale
        if turn is None:
            return await self._save_reply(call, plan.key, _say("again", locale), locale, base_url)

        parts: list[str] = []
        result = turn.result
        nothing_done = not (
            turn.held_slots or turn.tickets or turn.queue_places or turn.pending_cancellations
        )
        if result.new_turn is None and result.degraded and nothing_done:
            # No model answered (a timeout, most likely). Ask again rather than
            # promising the "someone will help" a chat fallback says.
            parts.append(_say("again", locale))
        else:
            parts.append(result.reply)

        if turn.tickets:
            call.record(CallOutcome.BOOKED, booking_id=turn.tickets[-1].booking_id)
        elif turn.queue_places:
            call.record(CallOutcome.QUEUED)
        if turn.held_slots and not turn.tickets:
            parts.append(_say("press_to_book", locale))
        if turn.tickets:
            parts.append(await self._offer_details(call, turn.tickets[-1].booking_id, locale))
        if turn.pending_cancellations and call.verified:
            call.offer_cancellation(turn.pending_cancellations[-1].booking_id)
            parts.append(_say("press_to_cancel", locale))
        if turn.verification_requested and not call.verified:
            parts.append(await self._send_code(call, locale, now))
        if result.requires_human_handoff and result.new_turn is not None:
            await self._promise_callback(
                call,
                FollowUpReason.ESCALATED
                if turn.handoff_reason
                else FollowUpReason.AGENT_COULD_NOT_HELP,
                summary=turn.handoff_reason,
                customer_message=plan.message,
                booking_id=turn.related_booking_id,
            )
            parts.append(_say("callback", locale))

        text = " ".join(part for part in parts if part)
        return await self._save_reply(call, plan.key, text, locale, base_url)

    async def _offer_details(self, call: Call, booking_id: UUID, locale: str) -> str:
        """After a booking: its details go to WhatsApp, at once when the customer
        already agreed to WhatsApp, or once they press 3 for it.

        Without this a caller heard "booked, the business will confirm" and then
        nothing at all: no ticket, and no message until staff confirmed it.
        """
        if call.customer_id is None:
            return ""
        customer = await self.customers.get(call.customer_id)
        if customer.whatsapp_consent:
            await self._send_details(call, booking_id)
            return _say("details_sent", locale)
        call.offer_details(booking_id)
        return _say("offer_details", locale)

    async def _send_details(self, call: Call, booking_id: UUID) -> None:
        if call.customer_id is None:  # pragma: no cover - both callers checked it
            return
        await publish_event(
            self.session,
            BookingDetailsRequested(
                tenant_id=self.tenant_id,
                call_id=call.id,
                booking_id=booking_id,
                customer_id=call.customer_id,
            ),
        )

    async def _promise_callback(
        self,
        call: Call,
        reason: FollowUpReason,
        summary: str | None = None,
        customer_message: str | None = None,
        booking_id: UUID | None = None,
    ) -> None:
        """What stands behind "someone will call you": a follow-up in the inbox,
        with the number that called, and the call marked for a call back."""
        follow_up_id = await self.support.open_for_call(
            call_id=call.id,
            business_id=call.business_id,
            customer_id=call.customer_id,
            caller_phone=call.caller_e164,
            reason=reason,
            summary=summary,
            customer_message=customer_message,
            booking_id=booking_id,
        )
        call.record(CallOutcome.CALLBACK_REQUESTED)
        await publish_event(
            self.session,
            CallbackRequested(
                tenant_id=self.tenant_id,
                call_id=call.id,
                business_id=call.business_id,
                customer_id=call.customer_id,
                follow_up_id=follow_up_id,
                reason=str(reason),
            ),
        )

    def _code_key(self) -> str:
        return purpose_key(self.secret_key, CODE_PURPOSE)

    async def _may_send_code(self, phone: str) -> bool:
        """Counts a code for the number, unless the hour's or the day's are used up."""
        for policy in CODE_POLICIES:
            key = f"voice-code:{policy.window_seconds}:{phone}"
            if not (await self.limiter.check(key, policy)).allowed:
                return False
        return True

    async def _send_code(self, call: Call, locale: str, now: datetime) -> str:
        """A code to the customer's number on file, which may not be the caller's."""
        if call.customer_id is None:
            await self._promise_callback(call, FollowUpReason.CODE_NOT_SENT)
            return _say("code_unsent", locale)
        customer = await self.customers.get(call.customer_id)
        if not await self._may_send_code(customer.phone):
            # No follow-up: someone forging caller ID would fill the inbox with them.
            metrics.count("nova_voice_code_limited_total")
            logger.info("voice_code_limited", extra={"call_id": str(call.id)})
            return _say("code_limit", locale)
        code = new_code()
        try:
            await self.whatsapp.send_template_message(
                to_phone=customer.phone,
                template_name=CODE_TEMPLATE,
                params={"code": code},
                language=locale,
            )
        except Exception:
            # Not configured, or the BSP refused: the caller is told, not left waiting.
            logger.warning("voice_code_not_sent", extra={"call_id": str(call.id)}, exc_info=True)
            await self._promise_callback(call, FollowUpReason.CODE_NOT_SENT)
            return _say("code_unsent", locale)
        call.issue_code(code_digest(code, key=self._code_key(), call_id=call.id), now=now)
        return _say("code_sent", locale)

    # --- reminder calls ------------------------------------------------------

    async def prepare_reminder(
        self,
        booking_id: UUID,
        base_url: str,
        now: datetime,
        window: tuple[int, int],
        daily_cap: int,
    ) -> ReminderPlan | None:
        """The reminder call for a confirmed booking, saved but not yet dialled.
        None when no call should ring.

        Only with the customer's voice consent (PDPL), from the business's own
        line, during the day where the branch is, within the daily cap, and on a
        plan that includes Sara. The caller commits the call before
        `dial_reminder`: Unifonic's first POST must find it, and a second sweep
        must find it whatever the dial does.
        """
        if await self.calls.reminder_for(booking_id) is not None:
            return None
        booking = await self.bookings.get(booking_id)
        if booking.status is not BookingStatus.CONFIRMED:
            return None
        customer = await self.customers.get(booking.customer_id)
        if not customer.voice_consent:
            return None
        try:
            validate_gcc_phone(customer.phone, self.customers.allowed_phone_country_codes)
        except DomainError:
            return None
        line = await self.lines.active_for_business(booking.business_id)
        if line is None:
            return None
        location = await self.catalog.get_location(booking.location_id)
        if not within_calling_hours(
            now, timezone=location.timezone, start_hour=window[0], end_hour=window[1]
        ):
            return None
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if await self.calls.outbound_since(day_start) >= daily_cap:
            logger.warning("voice_reminder_cap_reached", extra={"tenant_id": str(self.tenant_id)})
            return None
        try:
            await self.billing.require_feature(booking.business_id, CALL_CENTER_FEATURE)
        except DomainError:
            return None

        business = await self.catalog.get_business(booking.business_id)
        service = await self.catalog.get_service(booking.service_id)
        arabic = line.locale == "ar"
        text = _say(
            "reminder",
            line.locale,
            # A record Sara opened is named by its number: no name to greet.
            name=f" {customer.full_name}" if customer.full_name != customer.phone else "",
            business=business.name_ar if arabic else business.name_en,
            service=service.name_ar if arabic else service.name_en,
            time=spoken_time(
                booking.slot.starts_at, timezone=location.timezone, locale=line.locale, now=now
            ),
        )
        call = Call.outbound_reminder(
            tenant_id=self.tenant_id,
            line_id=line.id,
            business_id=booking.business_id,
            booking_id=booking.id,
            customer_id=customer.id,
            phone=customer.phone,
            now=now,
        )
        call.remember(None, text)
        await self.calls.add_call(call)
        return ReminderPlan(
            call_id=call.id,
            to=customer.phone,
            caller_id=line.number_e164,
            reply=VoiceReply(text, line.locale, self._listen_url(call.id, base_url)),
        )

    async def dial_reminder(self, plan: ReminderPlan, *, base_url: str) -> DialOutcome:
        """Rings the customer. Holds no session: the caller committed the call first.

        A dial that may have rung (a timeout after Unifonic had the request)
        counts as placed, with no call id: ringing twice is worse than not
        knowing the id. Only a dial that certainly did not ring is not placed.
        """
        first = await self.speak(plan.reply, base_url=base_url)
        try:
            gateway_call_id = await self.gateway.place_call(
                to=plan.to, caller_id=plan.caller_id, reply=first
            )
        except IntegrationNotConfiguredError:
            return DialOutcome(placed=False)
        except VoiceGatewayError as exc:
            if not exc.may_have_placed:
                return DialOutcome(placed=False)
            logger.warning("voice_reminder_outcome_unknown", extra={"call_id": str(plan.call_id)})
            return DialOutcome(placed=True)
        return DialOutcome(placed=True, gateway_call_id=gateway_call_id)

    async def record_dial(self, plan: ReminderPlan, outcome: DialOutcome) -> None:
        """What the dial did. A call that never rang is removed, so the next
        sweep tries the booking again; one that rang keeps its row for good."""
        if not outcome.placed:
            await self.calls.delete_call(plan.call_id)
            return
        if outcome.gateway_call_id is None:
            return
        # Locked: the customer may already be pressing a key on this call.
        call = await self.calls.get_call(plan.call_id, for_update=True)
        if call is None:  # pragma: no cover - committed before the dial
            return
        call.gateway_call_id = outcome.gateway_call_id
        await self.calls.save_call(call)


class CallSweeper:
    """The worker's cross-tenant call-log housekeeping: calls the caller hung up
    on, and personal details kept no longer than needed (PDPL)."""

    def __init__(self, calls: UnscopedCallRepository) -> None:
        self.calls = calls

    async def scrub_started_before(self, cutoff: datetime, *, limit: int = 500) -> int:
        """Clears who called and what Sara said from calls older than `cutoff`,
        `limit` at a time until none are left. Returns how many.

        The call itself stays (its outcome, turns, customer and booking), so the
        business's call log and its counts outlive the personal details.
        """
        total = 0
        while True:
            batch = await self.calls.scrub_started_before(cutoff, limit=limit)
            total += batch
            if batch < limit:
                return total

    async def end_abandoned(self, *, now: datetime, limit: int = 500) -> int:
        """Ends calls the caller hung up on, `limit` at a time. Returns how many.

        Unifonic posts nothing when a caller hangs up, so such a call stayed
        "in progress" for good. Once `CALL_LINK_TTL` has passed since its last
        turn, no link it was given still works, and it is over.
        """
        total = 0
        while True:
            batch = await self.calls.end_idle_since(now - CALL_LINK_TTL, limit=limit)
            total += batch
            if batch < limit:
                return total


__all__ = [
    "CALL_CENTER_FEATURE",
    "REMINDER_LEAD",
    "AnswerPlan",
    "CallCenterService",
    "CallSweeper",
    "DialOutcome",
    "LineSetup",
    "ReminderPlan",
    "SaraVoice",
]
