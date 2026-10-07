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
"""

import logging
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
from app.core.security import Principal
from app.modules.ai_agents.agents import (
    AGENTS,
    AgentSpec,
    AgentUnavailableError,
    Audience,
    resolve_agent,
)
from app.modules.ai_agents.concurrency import InferenceGate
from app.modules.ai_agents.exceptions import AiBusyError
from app.modules.ai_agents.guardrails import (
    GuardrailError,
    GuardrailViolation,
    ProposedAction,
    assert_caller_may_use_agent,
    assert_tenant_matches,
    grounded_values_in,
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
from app.modules.analytics.service import AnalyticsService, ChartReport
from app.modules.billing.service import BillingService
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
from app.modules.discovery.service import DiscoveryService
from app.modules.identity.service import MembershipService
from app.modules.payment.service import PaymentService
from app.modules.queue.service import QueueService

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
    ) -> ChatTurn:
        """Runs a turn. Refuses before inference; never raises for an inference problem."""
        spec = resolve_agent(agent_name)
        # A marketplace agent works across tenants and a tenant's agent inside
        # one: each is reachable only through its own route.
        if spec.marketplace != (self.tenant_id is None):
            raise AgentUnavailableError(agent_name)
        # Both names: the alias the caller used and the agent it resolved to.
        assert_caller_may_use_agent(agent_name, caller_is_staff=principal.is_staff)
        assert_caller_may_use_agent(spec.name, caller_is_staff=principal.is_staff)
        if spec.audience is Audience.STAFF and not principal.is_staff:  # pragma: no cover
            raise GuardrailError(GuardrailViolation.OWNER_ONLY, "Staff only.")
        assert_tenant_matches(requested_tenant_id, self.tenant_id)

        if spec.needs_business and business_id is None:
            raise ValidationDomainError(f"'{spec.name}' works on one business: send business_id.")
        context_business = spec.needs_business or (spec.accepts_business and business_id)
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
            discovery=self.discovery if spec.marketplace else None,
            services_for=self.services_for if spec.marketplace else None,
        )
        artifacts = deps.artifacts
        instructions = self._instructions(spec, locale=locale)
        # NOVA's own instructions are facts too: a reply may repeat a number they state.
        artifacts.grounded_values |= grounded_values_in(instructions)
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
        if deps.offers:
            # Stated as a fact of the conversation, not left to memory: a turn
            # whose answer failed is not remembered, but its hold still stands.
            instructions = (
                f"{instructions}\n\n{self._offers_note(deps.offers, confirmed_hold_token)}"
            )

        gate = self.gate_factory() if self.gate_factory is not None else None
        started = time.perf_counter()
        try:
            async with gate.slot(str(principal.subject_id)) if gate else nullcontext():
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
                )
        except AiBusyError:
            metrics.record_ai_turn(
                agent=spec.name, outcome="busy", seconds=time.perf_counter() - started
            )
            raise
        if self.history and result.new_turn is not None:
            await self.history.append(conversation, result.new_turn)
        if self.history is not None and (artifacts.held_slots or artifacts.used_offers):
            await self.history.save_offers(
                conversation, encode_offers(self._offers_after(deps)), OFFER_TTL_SECONDS
            )

        if artifacts.handoff_reason is not None and not result.requires_human_handoff:
            result = replace(result, requires_human_handoff=True)
        elif artifacts.booking_failures and not artifacts.tickets:
            # A booking was attempted and refused, and nothing was booked. The
            # model's own text is not trusted here: live, qwen3-1.7b told a
            # customer "it has been booked" after exactly this refusal.
            code, reason = artifacts.booking_failures[-1]
            if code == "not_confirmed_yet" and artifacts.held_slots:
                # It tried to book what it had only just held: the honest
                # state is "held, waiting for your yes".
                reply = _after_write_reply(locale, booked=False)
            elif code == "not_confirmed":
                # Held in an earlier turn, but the customer never pressed its
                # button: whatever text persuaded the model, nothing is booked.
                reply = _press_to_book_reply(locale)
            else:
                reply = _booking_failed_reply(locale, reason)
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
                reply=_holding_reply(locale, artifacts.held_slots[-1]),
                requires_human_handoff=False,
            )
        elif result.new_turn is None and (artifacts.held_slots or artifacts.tickets):
            # No model answered, but a tool already held or booked: say what is
            # true rather than "someone will help", which reads as a failure
            # when the customer's time is in fact held or booked.
            result = replace(
                result,
                reply=_after_write_reply(locale, booked=bool(artifacts.tickets)),
                requires_human_handoff=False,
            )

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
    def _offers_note(offers: list[HeldSlot], confirmed_hold_token: str | None) -> str:
        """The open offers, for the model: times and places, never a hold token."""
        lines = [
            f"- starts_at {offer.starts_at.isoformat()}"
            + (f" at business_slug {offer.business_slug}" if offer.business_slug else "")
            for offer in offers
        ]
        note = "Times already held for this customer and waiting for their answer:\n" + "\n".join(
            lines
        )
        confirmed = next((o for o in offers if o.hold_token == confirmed_hold_token), None)
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

    def unavailable_response(self, *, locale: str) -> InferenceResult:
        return fallback_result(locale=locale, reason="ai_disabled")

    @staticmethod
    def _instructions(spec: AgentSpec, *, locale: str) -> str:
        language = "Arabic" if locale == "ar" else "English"
        parts = [spec.instructions, f"Reply in {language}."]
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


_AFTER_WRITE_REPLIES = {
    ("en", True): "It is booked. Your QR ticket is below: show it at reception to check in.",
    ("ar", True): "تم الحجز. تذكرتك مع رمز QR أدناه: اعرضها في الاستقبال لتسجيل حضورك.",
    ("en", False): "I am holding the time shown below for you. Shall I book it?",
    ("ar", False): "أحجز لك الموعد الظاهر أدناه مؤقتًا. هل أؤكد الحجز؟",
}


def _mentions_time(reply: str, offer: HeldSlot) -> bool:
    """Whether the reply already tells the customer the held time (its HH:MM)."""
    if offer.label is None:
        return True
    hhmm = offer.label.rsplit(", ", 1)[-1][:5]
    return hhmm in reply


def _holding_reply(locale: str, offer: HeldSlot) -> str:
    """The held time in words, from the hold itself rather than the model."""
    if locale == "ar":
        return f"أحجز لك مؤقتًا: {offer.label}. هل أؤكد الحجز؟"
    return f"I am holding {offer.label} for you. Shall I book it?"


def _press_to_book_reply(locale: str) -> str:
    """Told when the model tried to book a time the customer has not confirmed."""
    if locale == "ar":
        return "لتأكيد الحجز، اضغط «نعم، احجزه» تحت الموعد المحجوز لك."
    return 'To book it, press "Yes, book it" under the time held for you.'


def _booking_failed_reply(locale: str, reason: str) -> str:
    """The truth after a refused booking, whatever the model said."""
    if locale == "ar":
        return "لم أتمكن من إتمام الحجز. هل تريد أن أبحث لك عن موعد آخر؟"
    return f"I could not complete the booking ({reason}). Shall I find you another time?"


def _after_write_reply(locale: str, *, booked: bool) -> str:
    """What the customer is told when a tool wrote but the model gave no answer."""
    return _AFTER_WRITE_REPLIES.get((locale, booked), _AFTER_WRITE_REPLIES[("en", booked)])


#: Kept for callers and tests written against the docs/10 roster.
AGENT_TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    name: spec.tools for name, spec in AGENTS.items()
}
AVAILABLE_AGENTS: frozenset[str] = frozenset(AGENTS)


__all__ = [
    "AGENT_TOOL_ALLOWLIST",
    "AVAILABLE_AGENTS",
    "AgentDeps",
    "AiChatService",
    "ChatTurn",
    "DiscoveryScope",
    "ServiceScope",
    "TenantServices",
    "TurnArtifacts",
]
