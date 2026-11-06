"""ai_agents · APPLICATION layer — one turn of conversation, every guardrail in order.

Layer rule: other modules' *services* only. This module has NO repository, NO
models, and no `AsyncSession` anywhere in `AgentDeps`.

That absence is the whole design (docs/04, docs/10):

    ✅  services.booking.create(...)
    ❌  session.add(BookingRecord(...))

An agent cannot bypass a domain rule because it has nothing to bypass it with.

A turn holds no transaction. Inference takes seconds, while a pooled connection
and the advisory lock a hold or a queue join takes should last milliseconds. So
the checks before the model runs share one short unit of work, and each tool
call opens its own through `ServiceScope`. What a tool writes is committed when
it returns, and stays committed whatever the model does next.

A turn, in order (docs/13 sections 3 and 5):

    resolve the agent            aliases first, so an old name skips nothing
    staff-only                   before the model runs
    role permission              from this tenant's memberships, not the token
    one named business           required, and inside this tenant
    plan feature                 from the business's plan
    sanitise the message         PII masked, injection framed as data
    recall the conversation      this session's recent turns (`history.py`)
    run the model                PydanticAI through `runtime.py`, one unit of
                                 work per tool call
    remember the turn            unless no model answered
    attach what tools produced   charts, actions, holds and queue places from
                                 `TurnArtifacts`, never from the model's text
    open a follow-up             a customer's handoff at a business goes to
                                 its staff inbox (`support`), or no person is
                                 promised
"""

import logging
import re
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.core import metrics
from app.core.exceptions import ValidationDomainError
from app.core.security import AuthorizationError, Principal, PrincipalKind
from app.modules.ai_agents.agents import (
    AGENTS,
    AgentSpec,
    AgentUnavailableError,
    Audience,
    resolve_agent,
)
from app.modules.ai_agents.concurrency import InferenceGate
from app.modules.ai_agents.exceptions import AiBusyError, AiMemoryUnavailableError
from app.modules.ai_agents.guardrails import (
    GuardrailError,
    GuardrailViolation,
    ProposedAction,
    app_locale,
    assert_caller_may_use_agent,
    assert_tenant_matches,
    clean_reply,
    grounded_values_in,
    redact_pii,
    sanitize_untrusted_text,
)
from app.modules.ai_agents.history import ConversationKey, ConversationStore
from app.modules.ai_agents.runtime import InferenceEngine, InferenceResult, fallback_result
from app.modules.ai_agents.tools import (
    AgentToolkit,
    BookedTicket,
    HeldSlot,
    PendingCancellation,
    QueuePlace,
    decode_offers,
    encode_offers,
)
from app.modules.ai_agents.tools.facts import BusinessFacts, business_facts
from app.modules.analytics.service import AnalyticsService, ChartReport
from app.modules.billing.service import BillingService
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
from app.modules.discovery.service import DiscoveryService
from app.modules.identity.service import MembershipService
from app.modules.payment.service import PaymentService
from app.modules.queue.service import QueueService
from app.modules.support.domain import FollowUpReason
from app.modules.support.service import SupportService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TenantServices:
    """Every service a turn may call, all bound to one short transaction."""

    booking: BookingService
    queue: QueueService
    catalog: CatalogService
    payment: PaymentService
    billing: BillingService
    analytics: AnalyticsService
    #: Not a tool's: the turn reads the caller's role with it before inference.
    memberships: MembershipService
    #: Not a tool's either: a customer's handoff opens a follow-up after the turn.
    support: SupportService


class ServiceScope(Protocol):
    """Opens one unit of work for the turn's tenant and yields its services.

    Commits when the block exits normally and rolls back when it raises. The
    implementation is `dependencies.TenantServiceScope`, the one place in this
    module that sees a session.
    """

    def __call__(self) -> AbstractAsyncContextManager[TenantServices]: ...


class DiscoveryScope(Protocol):
    """Opens one unit of work in the public listing window (`set_discovery_scope`).

    For the marketplace assistant, which has no tenant until a customer picks a
    business. `dependencies.DiscoveryServiceScope` implements it.
    """

    def __call__(self) -> AbstractAsyncContextManager[DiscoveryService]: ...


#: How long offers are remembered. A hold lasts minutes; the offer outlives it
#: so a slow reply can still book the time while it is free.
OFFER_TTL_SECONDS = 30 * 60
#: Offers kept per conversation: the latest few times shown.
MAX_OFFERS = 6


@dataclass
class TurnArtifacts:
    """What tools produced this turn. The response is assembled from here."""

    charts: dict[str, ChartReport] = field(default_factory=dict)
    proposed_actions: dict[str, ProposedAction] = field(default_factory=dict)
    grounded_values: set[Decimal] = field(default_factory=set)
    metrics_used: set[str] = field(default_factory=set)
    booking_ids: list[UUID] = field(default_factory=list)
    #: What the client needs to act on a write: a hold's token, a queue place.
    held_slots: list[HeldSlot] = field(default_factory=list)
    queue_places: list[QueuePlace] = field(default_factory=list)
    #: Cancellations offered for the customer to confirm. Nothing was cancelled.
    pending_cancellations: list[PendingCancellation] = field(default_factory=list)
    #: Bookings made this turn, each with its QR ticket for the client.
    tickets: list[BookedTicket] = field(default_factory=list)
    #: Hold tokens of offers booked this turn, so they are not offered again.
    used_offers: set[str] = field(default_factory=set)
    #: Why `book_held_slot` was refused this turn, if it was: (code, reason).
    booking_failures: list[tuple[str, str]] = field(default_factory=list)
    #: Write tools that completed, in order. Each one's unit of work committed.
    committed_writes: list[str] = field(default_factory=list)
    handoff_reason: str | None = None
    #: `verify_caller` asked for a code to be sent; the call center sends it.
    verification_requested: bool = False

    def begin_attempt(self) -> None:
        """Clears what one model attempt presented, before the next begins.

        Charts, proposals, cited metrics and offered cancellations belong to the
        answer that named them, and a retry answers afresh. Writes, grounded
        figures and a requested handoff stay: they happened, whichever attempt
        caused them.
        """
        self.charts.clear()
        self.proposed_actions.clear()
        self.metrics_used.clear()
        self.pending_cancellations.clear()

    def nothing_committed(self) -> bool:
        """Whether starting the turn over could not repeat a write."""
        return not self.committed_writes


@dataclass
class AgentDeps:
    """docs/10 section 2's container, grown for docs/13. Services, never a session.

    `services` opens a short unit of work per call; tools reach every other
    module through it, and nothing here holds a connection between calls.
    `tenant_id` and `business_id` come from the authenticated request, never
    from the model; `principal` is what every per-row guard is checked against.
    """

    #: None for the marketplace assistant, until a tool resolves a listing.
    tenant_id: UUID | None
    session_id: str
    locale: str
    channel: str
    principal: Principal
    customer_id: UUID | None
    self_service: bool
    business_id: UUID | None
    #: The turn's own tenant; None for the marketplace assistant.
    services: ServiceScope | None
    artifacts: TurnArtifacts = field(default_factory=TurnArtifacts)
    #: Slots held and shown in EARLIER turns: all `book_held_slot` may book.
    offers: list[HeldSlot] = field(default_factory=list)
    #: The offer the customer confirmed by pressing its button this turn, from
    #: the request. `book_held_slot` books that offer and no other.
    confirmed_hold_token: str | None = None
    #: A marketplace referral the client holds (a storefront visit), checked by
    #: booking's own attribution; never trusted beyond that.
    referral_token: str | None = None
    #: A phone call (ADR-0017): Sara's turn, spoken rather than shown.
    voice: bool = False
    #: Whether the person is known to be who the customer record says. True for
    #: a signed-in caller; on a phone call, only once the caller typed the code
    #: sent to the customer's WhatsApp, because caller ID can be forged.
    caller_verified: bool = True
    #: Marketplace assistant only: the public listings, and a unit of work for
    #: a tenant a listing named.
    discovery: DiscoveryScope | None = None
    services_for: Callable[[UUID], ServiceScope] | None = None


@dataclass(frozen=True)
class ChatTurn:
    agent: AgentSpec
    result: InferenceResult
    charts: list[ChartReport]
    proposed_actions: list[ProposedAction]
    metrics_used: list[str]
    related_booking_id: UUID | None
    held_slots: list[HeldSlot]
    queue_places: list[QueuePlace]
    pending_cancellations: list[PendingCancellation]
    tickets: list[BookedTicket] = field(default_factory=list)
    verification_requested: bool = False
    #: The summary the agent gave `escalate_to_human`, for whoever follows up.
    handoff_reason: str | None = None
    #: A follow-up was opened in the business's inbox: a person will get back
    #: to the customer. False for a handoff no one was told about.
    follow_up_opened: bool = False


class AiChatService:
    def __init__(
        self,
        *,
        engine: InferenceEngine,
        services: ServiceScope | None,
        tenant_id: UUID | None,
        history: ConversationStore | None = None,
        discovery: DiscoveryScope | None = None,
        services_for: Callable[[UUID], ServiceScope] | None = None,
        gate_factory: Callable[[], InferenceGate] | None = None,
        gate_wait_seconds: float | None = None,
    ) -> None:
        """A tenant's chat (`tenant_id` and `services`), or the marketplace's
        (no tenant; `discovery` and `services_for` instead)."""
        self.engine = engine
        self.services = services
        self.tenant_id = tenant_id
        #: None turns memory off: every turn starts from its own message.
        self.history = history
        self.discovery = discovery
        self.services_for = services_for
        #: Builds the turn limiter inside the request's event loop (a semaphore
        #: binds to its loop, and dependencies are built outside it). None: no
        #: limit, as in tests that run one turn.
        self.gate_factory = gate_factory
        #: How long a turn queues for a slot. None: the gate's own wait.
        self.gate_wait_seconds = gate_wait_seconds

    async def chat(
        self,
        *,
        message: str,
        session_id: str,
        principal: Principal,
        customer_id: UUID | None,
        self_service: bool,
        business_id: UUID | None = None,
        locale: str = "ar",
        channel: str = "pwa",
        agent_name: str = "concierge_agent",
        requested_tenant_id: UUID | None = None,
        referral_token: str | None = None,
        confirmed_hold_token: str | None = None,
        voice: bool = False,
        caller_verified: bool = True,
        confirm_latest_offer: bool = False,
    ) -> ChatTurn:
        """Runs a turn. Refuses before inference; never raises for an inference problem.

        `voice` is a phone call (ADR-0017), from `call_center` alone. There the
        caller confirms by pressing 1, which `confirm_latest_offer` reports: the
        newest offer's hold token is read here, server-side, as the button's is
        sent by the client. `caller_verified` is False until the caller proved
        the customer's phone.
        """
        spec = resolve_agent(agent_name)
        # A marketplace agent works across tenants and a tenant's agent inside
        # one: each is reachable only through its own route. A voice agent
        # answers calls only, and only it does.
        if spec.marketplace != (self.tenant_id is None) or spec.voice_only != voice:
            raise AgentUnavailableError(agent_name)
        if voice:
            channel = "voice"
        # Both names: the alias the caller used and the agent it resolved to.
        assert_caller_may_use_agent(agent_name, caller_is_staff=principal.is_staff)
        assert_caller_may_use_agent(spec.name, caller_is_staff=principal.is_staff)
        if spec.audience is Audience.STAFF and not principal.is_staff:  # pragma: no cover
            raise GuardrailError(GuardrailViolation.OWNER_ONLY, "Staff only.")
        assert_tenant_matches(requested_tenant_id, self.tenant_id)

        if spec.needs_business and business_id is None:
            raise ValidationDomainError(f"'{spec.name}' works on one business: send business_id.")
        context_business = spec.needs_business or (spec.accepts_business and business_id)
        facts: BusinessFacts | None = None
        if self.services is None and spec.required_permission is not None:
            # No scope to read this tenant's membership through: refuse rather
            # than skip the check and answer an owner agent's question.
            raise AgentUnavailableError(agent_name)
        if self.services is not None and (spec.required_permission is not None or context_business):
            # One short unit of work for every check before the model runs.
            async with self.services() as services:
                if spec.required_permission is not None:
                    # This tenant's membership row decides, before any figure is read.
                    await services.memberships.require_permission(
                        principal, spec.required_permission
                    )
                if context_business and business_id is not None:
                    # 404 for a business outside this tenant, before any plan is read.
                    await services.catalog.get_business(business_id)
                    if spec.needs_business and spec.required_feature is not None:
                        await services.billing.require_feature(business_id, spec.required_feature)
                    # A locked business gets no AI (402 `subscription_required`).
                    # A trial's allowance is the owner's: only staff agents spend
                    # it (402 `trial_ai_limit_reached` once it is spent), or any
                    # customer could use it up from the storefront.
                    await services.billing.require_ai(business_id, spends_trial=_spends_trial(spec))
                    if spec.audience is Audience.CUSTOMER:
                        # What the storefront's assistant can say without a tool.
                        facts = await business_facts(services, business_id, locale)

        sanitized = sanitize_untrusted_text(message)
        if sanitized.injection_detected:
            metrics.count("nova_ai_injection_total")
            logger.warning(
                "ai_prompt_injection_detected", extra={"session_id": session_id, "agent": spec.name}
            )

        deps = AgentDeps(
            tenant_id=self.tenant_id,
            session_id=session_id,
            locale=locale,
            channel=channel,
            principal=principal,
            customer_id=customer_id,
            self_service=self_service,
            business_id=business_id if context_business else None,
            services=self.services,
            referral_token=referral_token,
            confirmed_hold_token=confirmed_hold_token,
            voice=voice,
            caller_verified=caller_verified,
            discovery=self.discovery if spec.marketplace else None,
            services_for=self.services_for if spec.marketplace else None,
        )
        artifacts = deps.artifacts
        instructions = self._instructions(spec, locale=locale, voice=voice)
        if facts is not None:
            instructions = f"{instructions}\n\n{facts.text}"
        toolkit = AgentToolkit(
            deps, spec=spec, tool_timeout_seconds=self.engine.tool_timeout_seconds
        )

        conversation = ConversationKey(
            tenant_id=self.tenant_id,
            principal_id=principal.subject_id,
            business_id=deps.business_id,
            session_id=session_id,
        )
        earlier_turns = await self.history.load(conversation) if self.history else []
        if self.history is not None:
            # Loaded before the model runs, so a hold made in this turn is not
            # among them: the customer has to see it before it can be booked.
            deps.offers = decode_offers(await self.history.load_offers(conversation))
        if confirm_latest_offer and deps.offers:
            deps.confirmed_hold_token = deps.offers[-1].hold_token
        if deps.offers:
            # Stated as a fact of the conversation, not left to memory: a turn
            # whose answer failed is not remembered, but its hold still stands.
            instructions = (
                f"{instructions}\n\n"
                f"{self._offers_note(deps.offers, deps.confirmed_hold_token, voice=voice)}"
            )
        if not voice:
            # Last, where a small model weighs it most. A call keeps its own
            # rule: Sara answers a caller who speaks English in English.
            instructions = f"{instructions}\n\n{_LANGUAGE_RULES[app_locale(locale)]}"
        # NOVA's own instructions are facts too: a reply may repeat a number they
        # state. Read once they are whole, so the open offers' times count.
        artifacts.grounded_values |= grounded_values_in(instructions)

        gate = self.gate_factory() if self.gate_factory is not None else None
        started = time.perf_counter()
        try:
            async with (
                gate.slot(str(principal.subject_id), self.gate_wait_seconds)
                if gate
                else nullcontext()
            ):
                result = await self.engine.run_turn(
                    agent_name=spec.name,
                    system_prompt=instructions,
                    user_message=sanitized.text,
                    deps=deps,
                    tools=toolkit.for_agent(),
                    locale=locale,
                    prefer_reasoning_model=spec.prefer_reasoning_model,
                    output_type=spec.output_type,
                    grounded=spec.grounded_numbers,
                    history=earlier_turns,
                    before_attempt=artifacts.begin_attempt,
                    retry_is_safe=artifacts.nothing_committed,
                    # The app's language is the reply's, checked, not asked for.
                    reply_locale=None if voice else locale,
                )
        except AiBusyError:
            metrics.record_ai_turn(
                agent=spec.name, outcome="busy", seconds=time.perf_counter() - started
            )
            raise
        if self.history and result.new_turn is not None:
            await self.history.append(conversation, result.new_turn)
        if result.new_turn is not None and _spends_trial(spec) and deps.business_id:
            # Counted once a model answered: a busy, refused or failed turn is free.
            await self._count_ai_message(deps.business_id)
        if self.history is not None and (artifacts.held_slots or artifacts.used_offers):
            await self.history.save_offers(
                conversation, encode_offers(self._offers_after(deps)), OFFER_TTL_SECONDS
            )

        reply, says_nothing = clean_reply(result.reply, message)
        if reply != result.reply:
            result = replace(result, reply=reply)

        if artifacts.handoff_reason is not None and not result.requires_human_handoff:
            result = replace(result, requires_human_handoff=True)
        elif says_nothing and not (artifacts.held_slots or artifacts.tickets):
            # The model gave the question back, or nothing at all. Say what the
            # assistant can do rather than show the customer their own words.
            logger.info("ai_reply_said_nothing", extra={"agent": spec.name})
            result = replace(
                result,
                reply=_unanswered_reply(locale, facts.branches if facts else (), voice=voice),
                requires_human_handoff=False,
            )
        elif artifacts.booking_failures and not artifacts.tickets:
            # A booking was attempted and refused, and nothing was booked. The
            # model's own text is not trusted here: live, qwen3-1.7b told a
            # customer "it has been booked" after exactly this refusal.
            code, reason = artifacts.booking_failures[-1]
            if code == "not_confirmed_yet" and artifacts.held_slots:
                # It tried to book what it had only just held: the honest
                # state is "held, waiting for your yes".
                reply = _after_write_reply(locale, booked=False, voice=voice)
            elif code == "not_confirmed":
                # Held in an earlier turn, but the customer never pressed its
                # button: whatever text persuaded the model, nothing is booked.
                reply = _press_to_book_reply(locale, voice=voice)
            else:
                reply = _booking_failed_reply(locale, reason, voice=voice)
            result = replace(result, reply=reply, requires_human_handoff=False)
        elif (
            artifacts.held_slots
            and not artifacts.tickets
            and not _mentions_time(result.reply, artifacts.held_slots[-1])
        ):
            # A small model, told to name the held time, answered only "Shall I
            # book it?". The customer must know what is held: say it for it.
            result = replace(
                result,
                reply=_holding_reply(locale, artifacts.held_slots[-1], voice=voice),
                requires_human_handoff=False,
            )
        elif result.new_turn is None and (artifacts.held_slots or artifacts.tickets):
            # No model answered, but a tool already held or booked: say what is
            # true rather than "someone will help", which reads as a failure
            # when the customer's time is in fact held or booked.
            result = replace(
                result,
                reply=_after_write_reply(locale, booked=bool(artifacts.tickets), voice=voice),
                requires_human_handoff=False,
            )

        follow_up_opened = False
        if result.requires_human_handoff and self._owes_follow_up(
            spec, principal, self_service=self_service, voice=voice
        ):
            follow_up_opened = await self._open_follow_up(
                user_id=principal.subject_id,
                business_id=deps.business_id,
                session_id=session_id,
                result=result,
                artifacts=artifacts,
                message=message,
            )
        if result.requires_human_handoff and result.degraded and not follow_up_opened and not voice:
            # The fallback says a person will help. Nobody was told, so say
            # what is true instead. A call is Sara's to word (`call_center`).
            result = replace(result, reply=_unavailable_reply(locale))

        turn = ChatTurn(
            agent=spec,
            result=result,
            charts=self._charts(result.chart_ids, artifacts),
            proposed_actions=self._actions(result.proposed_action_ids, artifacts),
            metrics_used=[
                metric for metric in result.metrics_used if metric in artifacts.metrics_used
            ],
            related_booking_id=artifacts.booking_ids[-1] if artifacts.booking_ids else None,
            held_slots=list(artifacts.held_slots),
            queue_places=list(artifacts.queue_places),
            pending_cancellations=list(artifacts.pending_cancellations),
            tickets=list(artifacts.tickets),
            verification_requested=artifacts.verification_requested,
            handoff_reason=artifacts.handoff_reason,
            follow_up_opened=follow_up_opened,
        )
        metrics.record_ai_turn(
            agent=spec.name,
            outcome="handoff"
            if result.requires_human_handoff
            else "degraded"
            if result.degraded
            else "ok",
            seconds=time.perf_counter() - started,
        )
        logger.info(
            "ai_turn_completed",
            extra={
                "session_id": session_id,
                "tenant_id": str(self.tenant_id or "market"),
                "agent": spec.name,
                "handoff": result.requires_human_handoff,
                "follow_up": follow_up_opened,
                "degraded": result.degraded,
                "model": result.model_used,
                "charts": len(turn.charts),
                "proposed_actions": len(turn.proposed_actions),
                "committed_writes": len(artifacts.committed_writes),
                "earlier_turns": len(earlier_turns),
            },
        )
        return turn

    @staticmethod
    def _offers_note(
        offers: list[HeldSlot], confirmed_hold_token: str | None, *, voice: bool = False
    ) -> str:
        """The open offers, for the model: times and places, never a hold token."""
        lines = [
            f"- starts_at {offer.starts_at.isoformat()}"
            + (f" at business_slug {offer.business_slug}" if offer.business_slug else "")
            # What was held, in local time: the words to repeat to the customer.
            + (f": {offer.label}" if offer.label else "")
            for offer in offers
        ]
        note = "Times already held for this customer and waiting for their answer:\n" + "\n".join(
            lines
        )
        confirmed = next((o for o in offers if o.hold_token == confirmed_hold_token), None)
        if voice:
            if confirmed is not None:
                return (
                    f"{note}\nThe caller just pressed 1 to book starts_at "
                    f"{confirmed.starts_at.isoformat()}. "
                    "Call book_held_slot with that starts_at now."
                )
            return (
                f"{note}\nThe caller books one by pressing 1 on the keypad. If they say yes out "
                "loud, ask them to press 1. Do not call book_held_slot, and do not hold it again."
            )
        if confirmed is not None:
            return (
                f'{note}\nThe customer just pressed "Yes, book it" on starts_at '
                f"{confirmed.starts_at.isoformat()}. Call book_held_slot with that starts_at now."
            )
        return (
            f'{note}\nThe customer books one by pressing "Yes, book it" under it. If they '
            "say yes in words, ask them to press it. Do not call book_held_slot, and do not "
            "hold it again."
        )

    def _owes_follow_up(
        self, spec: AgentSpec, principal: Principal, *, self_service: bool, voice: bool
    ) -> bool:
        """Whether a handoff in this turn is a business's to follow up.

        A signed-in customer, in their own name, at a business: someone staff
        can reach. Not the marketplace assistant, which has no business to
        tell; not staff, who are the people a handoff would go to; and not a
        call, whose follow-up `call_center` opens with the caller's number.
        """
        return (
            spec.audience is Audience.CUSTOMER
            and not voice
            and self.services is not None
            and self.tenant_id is not None
            and principal.kind is PrincipalKind.CUSTOMER
            and self_service
        )

    async def _open_follow_up(
        self,
        user_id: UUID,
        business_id: UUID | None,
        session_id: str,
        result: InferenceResult,
        artifacts: TurnArtifacts,
        message: str,
    ) -> bool:
        """Opens (or updates) this conversation's follow-up. False if it could not:
        the turn is answered either way, only without promising a person."""
        if self.services is None:  # pragma: no cover - `_owes_follow_up` checked it
            return False
        if artifacts.handoff_reason is not None:
            reason = FollowUpReason.ESCALATED
        elif result.degraded:
            reason = FollowUpReason.ASSISTANT_UNAVAILABLE
        else:
            reason = FollowUpReason.AGENT_COULD_NOT_HELP
        # Masked as the model saw it (numbers, emails, payment references): a
        # card number typed into the chat is not copied into the inbox. The
        # contact on file is how staff reach the customer.
        customer_message, _ = redact_pii(message.strip())
        try:
            async with self.services() as services:
                await services.support.open_for_chat(
                    user_id=user_id,
                    business_id=business_id,
                    session_id=session_id,
                    reason=reason,
                    summary=artifacts.handoff_reason,
                    customer_message=customer_message,
                    booking_id=artifacts.booking_ids[-1] if artifacts.booking_ids else None,
                )
        except Exception:
            logger.warning("ai_follow_up_not_opened", exc_info=True)
            return False
        return True

    @staticmethod
    def _offers_after(deps: AgentDeps) -> list[HeldSlot]:
        """Earlier offers still open, then this turn's, newest last."""
        now = datetime.now(UTC)
        kept = [
            offer
            for offer in [*deps.offers, *deps.artifacts.held_slots]
            if offer.hold_token not in deps.artifacts.used_offers and offer.starts_at > now
        ]
        return kept[-MAX_OFFERS:]

    async def _count_ai_message(self, business_id: UUID) -> None:
        if self.services is None:  # pragma: no cover - staff agents have a tenant
            return
        try:
            async with self.services() as services:
                await services.billing.use_ai_message(business_id)
        except Exception:
            # The answer is given; a lost count must not take it away.
            logger.warning("ai_message_not_counted", exc_info=True)

    def unavailable_response(self, *, locale: str) -> InferenceResult:
        return fallback_result(locale=locale, reason="ai_disabled")

    @staticmethod
    def _instructions(spec: AgentSpec, *, locale: str, voice: bool = False) -> str:
        parts = [spec.instructions]
        if voice:
            parts.append(f"Reply in {'Arabic' if locale == 'ar' else 'English'}.")
        if spec.needs_business or spec.audience is Audience.CUSTOMER:
            today = datetime.now(UTC).date().isoformat()
            parts.append(f"Today is {today}. Tools take calendar dates as YYYY-MM-DD.")
        return "\n\n".join(parts)

    @staticmethod
    def _charts(chart_ids: tuple[str, ...], artifacts: TurnArtifacts) -> list[ChartReport]:
        """Charts tools rendered, in the order the model named them.

        An id no tool produced is dropped: the model cannot invent a chart. A
        chart a tool drew but the model forgot to name is still shown.
        """
        unknown = [chart_id for chart_id in chart_ids if chart_id not in artifacts.charts]
        if unknown:
            logger.warning("ai_unknown_chart_ids_dropped", extra={"chart_ids": unknown})
        named = [
            artifacts.charts[chart_id]
            for chart_id in dict.fromkeys(chart_ids)
            if chart_id in artifacts.charts
        ]
        unnamed = [report for key, report in artifacts.charts.items() if key not in chart_ids]
        return named + unnamed

    @staticmethod
    def _actions(action_ids: tuple[str, ...], artifacts: TurnArtifacts) -> list[ProposedAction]:
        unknown = [
            action_id for action_id in action_ids if action_id not in artifacts.proposed_actions
        ]
        if unknown:
            logger.warning("ai_unknown_action_ids_dropped", extra={"action_ids": unknown})
        named = [
            artifacts.proposed_actions[action_id]
            for action_id in dict.fromkeys(action_ids)
            if action_id in artifacts.proposed_actions
        ]
        unnamed = [
            action for key, action in artifacts.proposed_actions.items() if key not in action_ids
        ]
        return named + unnamed


#: The app's language decides the reply's, not the customer's message: someone
#: who uses the app in Arabic and types in English still reads Arabic.
_LANGUAGE_RULES = {
    "ar": (
        "Language: the app is set to Arabic. Write your whole reply in Arabic, even when "
        "the customer writes in English or a tool's result is in English. Keep names, "
        "numbers and times as they are."
    ),
    "en": (
        "Language: the app is set to English. Write your whole reply in English, even when "
        "the customer writes in Arabic or a tool's result is in Arabic. Keep names, "
        "numbers and times as they are."
    ),
}


_AFTER_WRITE_REPLIES = {
    ("en", True): "It is booked. Your QR ticket is below: show it at reception to check in.",
    ("ar", True): "تم الحجز. تذكرتك مع رمز QR أدناه: اعرضها في الاستقبال لتسجيل حضورك.",
    ("en", False): "I am holding the time shown below for you. Shall I book it?",
    ("ar", False): "أحجز لك الموعد الظاهر أدناه مؤقتًا. هل أؤكد الحجز؟",
}


_CLOCK_TIME = re.compile(r"\b\d{2}:\d{2}\b")
_TO_ASCII_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _mentions_time(reply: str, offer: HeldSlot) -> bool:
    """Whether the reply already tells the customer the held time (its HH:MM)."""
    if offer.label is None:
        return True
    if "الساعة" in offer.label:
        # A call's Saudi label ("…، بكرة الساعة عشر الصبح"): the hour, in words.
        hour = offer.label.rsplit("الساعة", 1)[-1].split()[0]
        return f"الساعة {hour}" in reply
    times = _CLOCK_TIME.findall(offer.label)
    if not times:
        return True
    # A reply may write the time in Arabic-Indic digits.
    return times[-1] in reply.translate(_TO_ASCII_DIGITS)


_UNAVAILABLE_REPLIES = {
    "en": "The assistant can't answer right now. Please try again in a little while.",
    "ar": "المساعد غير متاح الآن. يُرجى المحاولة بعد قليل.",
}


def _spends_trial(spec: AgentSpec) -> bool:
    """Whether a turn counts against a trial's AI messages: the owner's agents do."""
    return spec.audience is Audience.STAFF


def _unavailable_reply(locale: str) -> str:
    """Said instead of the fallback's "a person will help" when no one was told."""
    return _UNAVAILABLE_REPLIES.get(locale, _UNAVAILABLE_REPLIES["en"])


def _unanswered_reply(locale: str, branches: tuple[str, ...] = (), *, voice: bool = False) -> str:
    """Said for the model when it gave nothing back. With the storefront's branches
    known, it says where they are (the question that failed live), from the records.
    On a call, no list: one spoken sentence."""
    arabic = locale.startswith("ar")
    if voice:
        if arabic:
            return (
                "المعذرة، ما قدرت أجاوبكم على هذا الحين. أقدر أعلمكم عن فروعنا وخدماتنا "
                "وأسعارها، أو أدور لكم موعد مناسب."
            )
        return (
            "Sorry, I couldn't answer that just now. I can tell you about our branches, "
            "services and prices, or find you a time."
        )
    if branches:
        where = "\n".join(f"- {line}" for line in branches)
        if arabic:
            return (
                f"فروعنا:\n{where}\n\nيمكنني أيضًا إخبارك بخدماتنا وأسعارها، أو إيجاد موعد متاح لك."
            )
        return (
            f"Here is where to find us:\n{where}\n\n"
            "I can also tell you what we offer and what it costs, or find you a free time."
        )
    if arabic:
        return (
            "عذرًا، لم أستطع الإجابة عن ذلك الآن. يمكنني إخبارك بمواقع فروعنا وخدماتنا "
            "وأسعارها، أو إيجاد موعد متاح لك."
        )
    return (
        "Sorry, I couldn't answer that just now. I can tell you where our branches are, "
        "what we offer and what it costs, or find you a free time."
    )


def _holding_reply(locale: str, offer: HeldSlot, *, voice: bool = False) -> str:
    """The held time in words, from the hold itself rather than the model."""
    if voice:
        # Spoken: no timezone in brackets, and the call center adds "press 1".
        label = (offer.label or "").rsplit(" (", 1)[0]
        return f"حجزت لكم مؤقت {label}." if locale == "ar" else f"I am holding {label} for you."
    if locale == "ar":
        return f"أحجز لك مؤقتًا: {offer.label}. هل أؤكد الحجز؟"
    return f"I am holding {offer.label} for you. Shall I book it?"


def _press_to_book_reply(locale: str, *, voice: bool = False) -> str:
    """Told when the model tried to book a time the customer has not confirmed."""
    if voice:
        if locale == "ar":
            return "إذا تبون أأكد لكم الحجز اضغطوا واحد."
        return "To book it, press 1 on your phone."
    if locale == "ar":
        return "لتأكيد الحجز، اضغط «نعم، احجزه» تحت الموعد المحجوز لك."
    return 'To book it, press "Yes, book it" under the time held for you.'


def _booking_failed_reply(locale: str, reason: str, *, voice: bool = False) -> str:
    """The truth after a refused booking, whatever the model said.

    On a call, Sara's own words: Saudi dialect in the polite plural, as her
    instructions require, and no reason, which is the server's text, not speech.
    """
    if voice:
        if locale == "ar":
            return "المعذرة، ما قدرت أكمل الحجز. تبون أدور لكم موعد ثاني؟"
        return "Sorry, I couldn't complete that booking. Shall I find you another time?"
    if locale == "ar":
        return "لم أتمكن من إتمام الحجز. هل تريد أن أبحث لك عن موعد آخر؟"
    return f"I could not complete the booking ({reason}). Shall I find you another time?"


_AFTER_WRITE_SPOKEN = {
    ("en", True): "It is booked. The business will confirm it shortly.",
    ("ar", True): "أبشروا، تم الحجز، والمحل بيأكده لكم قريب إن شاء الله.",
    ("en", False): "I am holding that time for you.",
    ("ar", False): "حجزت لكم الموعد مؤقت.",
}


def _after_write_reply(locale: str, *, booked: bool, voice: bool = False) -> str:
    """What the customer is told when a tool wrote but the model gave no answer."""
    replies = _AFTER_WRITE_SPOKEN if voice else _AFTER_WRITE_REPLIES
    return replies.get((locale, booked), replies[("en", booked)])


#: Kept for callers and tests written against the docs/10 roster.
AGENT_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    name: spec.tools for name, spec in AGENTS.items()
}
AVAILABLE_AGENTS: frozenset[str] = frozenset(AGENTS)


class ConversationMemoryService:
    """What the assistants remember of one person, and forgetting all of it.

    Memory is personal data (docs/14, Confidential (PDPL)): redacted, but names
    and free text remain. It expires on its own after `ai_history_ttl_seconds`;
    this is the way to erase it sooner, at every business and the marketplace.
    """

    def __init__(self, history: ConversationStore) -> None:
        self.history = history

    async def forget(self, principal: Principal) -> int:
        """Deletes the caller's conversations and offers; how many keys went.

        Offers hold the hold tokens `book_held_slot` books from, so a slot
        offered before this cannot be booked by pressing "Yes" afterwards.
        """
        if principal.kind is PrincipalKind.SERVICE:
            raise AuthorizationError("A service principal has no conversations to forget.")
        try:
            forgotten = await self.history.forget_principal(principal.subject_id)
        except Exception as error:
            logger.warning("ai_memory_not_forgotten", exc_info=True)
            raise AiMemoryUnavailableError(
                "Conversation memory is unreachable, so nothing was deleted. Try again shortly."
            ) from error
        logger.info("ai_memory_forgotten", extra={"keys": forgotten})
        return forgotten


__all__ = [
    "AGENT_TOOL_ALLOWLIST",
    "AVAILABLE_AGENTS",
    "AgentDeps",
    "AiChatService",
    "ChatTurn",
    "ConversationMemoryService",
    "DiscoveryScope",
    "ServiceScope",
    "TenantServices",
    "TurnArtifacts",
]
