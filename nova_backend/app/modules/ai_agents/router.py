"""ai_agents · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Rate limiting is a guardrail in its own right (docs/10 section 11, last row):
inference is the most expensive thing this server does, and an unthrottled chat
endpoint is a way to occupy the GPU indefinitely.

Neither route opens a request transaction. `get_authorized_tenant` authorizes
the path's tenant without one, and a turn's database work happens in the short
units of work `dependencies.TenantServiceScope` opens for it.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_authorized_tenant
from app.core.security import Principal, get_principal
from app.core.throttling import write_rate_limit
from app.modules.ai_agents.agents import AGENT_ALIASES, AGENTS
from app.modules.ai_agents.dependencies import get_ai_chat_service
from app.modules.ai_agents.schemas import (
    AgentCatalogOut,
    AgentInfoOut,
    AiChatRequest,
    AiChatResponse,
    PendingCancellationOut,
    ProposedActionOut,
    QueuePlaceOut,
)
from app.modules.ai_agents.service import AiChatService
from app.modules.analytics.schemas import ChartOut
from app.modules.booking.dependencies import resolve_booking_customer
from app.modules.booking.schemas import HoldSlotResult

router = APIRouter(prefix="/tenants/{tenant_id}/ai", tags=["ai"])


@router.post("/chat", response_model=AiChatResponse, dependencies=[Depends(write_rate_limit)])
async def chat(
    tenant_id: UUID,
    payload: AiChatRequest,
    agent: str = Query(
        default="concierge_agent",
        description="Which agent to route to. The docs/10 names are accepted as aliases.",
    ),
    service: AiChatService = Depends(get_ai_chat_service),
    principal: Principal = Depends(get_principal),
) -> AiChatResponse:
    """One turn of conversation (docs/13 section 3.4).

    The customer is resolved from the authenticated principal exactly as in
    booking — an agent acting for "whoever the request claims to be" would be a
    way to read someone else's appointments by asking politely.

    Nothing is committed here, because nothing is left to commit: each tool
    committed its own work when it returned. `hold_slot` took a real hold and
    `join_queue` a real place, whether or not the model then answered, which is
    why the holds and queue places come back even with a handoff. No tool
    cancels: `pending_cancellations` are bookings for the customer to confirm.
    """
    customer_reference_id = resolve_booking_customer(payload.customer_id, principal)

    turn = await service.chat(
        message=payload.message,
        session_id=payload.session_id,
        principal=principal,
        customer_id=customer_reference_id,
        self_service=payload.customer_id is None,
        business_id=payload.business_id,
        locale=payload.locale,
        channel=payload.channel,
        agent_name=agent,
    )

    result = turn.result
    return AiChatResponse(
        session_id=payload.session_id,
        agent=turn.agent.name,
        reply=result.reply,
        suggested_actions=result.suggested_actions,
        requires_human_handoff=result.requires_human_handoff,
        related_booking_id=turn.related_booking_id,
        held_slots=[
            HoldSlotResult(
                hold_token=hold.hold_token,
                provider_id=hold.provider_id,
                service_id=hold.service_id,
                starts_at=hold.starts_at,
                ends_at=hold.ends_at,
                expires_at=hold.expires_at,
            )
            for hold in turn.held_slots
        ],
        queue_places=[
            QueuePlaceOut(
                entry_id=place.entry_id,
                queue_id=place.queue_id,
                place_in_line=place.place_in_line,
                estimated_wait_minutes=place.estimated_wait_minutes,
            )
            for place in turn.queue_places
        ],
        pending_cancellations=[
            PendingCancellationOut(
                booking_id=pending.booking_id,
                starts_at=pending.starts_at,
                reason=pending.reason,
            )
            for pending in turn.pending_cancellations
        ],
        degraded=result.degraded,
        confidence=result.confidence,
        metrics_used=turn.metrics_used,
        charts=[
            ChartOut(
                chart_id=report.spec.chart_id,
                kind=report.spec.kind,
                title=report.spec.title,
                description=report.spec.description,
                locale=report.spec.locale,
                business_id=report.business_id,
                date_from=report.window.date_from,
                date_to=report.window.date_to,
                granularity=report.granularity,
                currency=report.currency,
                data_points=report.spec.data_points,
                generated_at=report.generated_at,
                figure=report.spec.figure,
            )
            for report in turn.charts
        ],
        proposed_actions=[
            ProposedActionOut(
                id=action.id,
                kind=action.kind,
                title=action.title,
                rationale=action.rationale,
                metric=action.metric,
                target_type=action.target,
                target_id=action.target_id,
                apply_via=action.apply_via,
            )
            for action in turn.proposed_actions
        ],
    )


@router.get(
    "/agents", response_model=AgentCatalogOut, dependencies=[Depends(get_authorized_tenant)]
)
async def list_agents(tenant_id: UUID) -> AgentCatalogOut:
    """The roster this deployment runs (docs/13 section 2), with the old aliases.

    Authenticated and tenant-checked like every other tenant route. It used to
    take no dependency at all — the one hole in ADR-0006's fail-closed rule
    outside the public discovery surface ADR-0010 carves out.

    Useful precisely because the answer can be "none that work": PydanticAI is
    an optional extra and Ollama may be offline, and a client should be able to
    hide the chat entry point rather than discovering it only hands off.
    """
    return AgentCatalogOut(
        available=sorted(AGENTS),
        aliases=dict(AGENT_ALIASES),
        agents=[
            AgentInfoOut(
                name=spec.name,
                audience=str(spec.audience),
                goal=spec.goal,
                required_feature=spec.required_feature,
            )
            for spec in AGENTS.values()
        ],
    )
