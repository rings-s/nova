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
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.core.exceptions import ValidationDomainError
from app.core.security import Principal
from app.modules.ai_agents.agents import AGENTS, AgentSpec, Audience, resolve_agent
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
from app.modules.ai_agents.tools import AgentToolkit, HeldSlot, PendingCancellation, QueuePlace
from app.modules.analytics.service import AnalyticsService, ChartReport
from app.modules.billing.service import BillingService
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
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
    #: Write tools that completed, in order. Each one's unit of work committed.
    committed_writes: list[str] = field(default_factory=list)
    handoff_reason: str | None = None

    def begin_attempt(self) -> None:
        """Clears what one model attempt presented, before the next begins.

        Charts, proposals and cited metrics belong to the answer that named
        them, and a retry answers afresh. Writes, grounded figures and a
        requested handoff stay: they happened, whichever attempt caused them.
        """
        self.charts.clear()
        self.proposed_actions.clear()
        self.metrics_used.clear()

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

    tenant_id: UUID
    session_id: str
    locale: str
    channel: str
    principal: Principal
    customer_id: UUID | None
    self_service: bool
    business_id: UUID | None
    services: ServiceScope
    artifacts: TurnArtifacts = field(default_factory=TurnArtifacts)


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


class AiChatService:
    def __init__(
        self,
        *,
        engine: InferenceEngine,
        services: ServiceScope,
        tenant_id: UUID,
        history: ConversationStore | None = None,
    ) -> None:
        self.engine = engine
        self.services = services
        self.tenant_id = tenant_id
        #: None turns memory off: every turn starts from its own message.
        self.history = history

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
    ) -> ChatTurn:
        """Runs a turn. Refuses before inference; never raises for an inference problem."""
        spec = resolve_agent(agent_name)
        # Both names: the alias the caller used and the agent it resolved to.
        assert_caller_may_use_agent(agent_name, caller_is_staff=principal.is_staff)
        assert_caller_may_use_agent(spec.name, caller_is_staff=principal.is_staff)
        if spec.audience is Audience.STAFF and not principal.is_staff:  # pragma: no cover
            raise GuardrailError(GuardrailViolation.OWNER_ONLY, "Staff only.")
        assert_tenant_matches(requested_tenant_id, self.tenant_id)

        if spec.needs_business and business_id is None:
            raise ValidationDomainError(f"'{spec.name}' works on one business: send business_id.")
        if spec.required_permission is not None or spec.needs_business:
            # One short unit of work for every check before the model runs.
            async with self.services() as services:
                if spec.required_permission is not None:
                    # This tenant's membership row decides, before any figure is read.
                    await services.memberships.require_permission(
                        principal, spec.required_permission
                    )
                if spec.needs_business and business_id is not None:
                    # 404 for a business outside this tenant, before any plan is read.
                    await services.catalog.get_business(business_id)
                    if spec.required_feature is not None:
                        await services.billing.require_feature(business_id, spec.required_feature)

        sanitized = sanitize_untrusted_text(message)
        if sanitized.injection_detected:
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
            business_id=business_id if spec.needs_business else None,
            services=self.services,
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
        if self.history and result.new_turn is not None:
            await self.history.append(conversation, result.new_turn)

        if artifacts.handoff_reason is not None and not result.requires_human_handoff:
            result = replace(result, requires_human_handoff=True)

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
        )
        logger.info(
            "ai_turn_completed",
            extra={
                "session_id": session_id,
                "tenant_id": str(self.tenant_id),
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

    def unavailable_response(self, *, locale: str) -> InferenceResult:
        return fallback_result(locale=locale, reason="ai_disabled")

    @staticmethod
    def _instructions(spec: AgentSpec, *, locale: str) -> str:
        language = "Arabic" if locale == "ar" else "English"
        parts = [spec.instructions, f"Reply in {language}."]
        if spec.needs_business:
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
    "ServiceScope",
    "TenantServices",
    "TurnArtifacts",
]
