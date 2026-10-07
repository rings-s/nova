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
from app.core.security import Principal, get_customer_principal, get_principal
from app.core.throttling import write_rate_limit
from app.modules.ai_agents.agents import AGENT_ALIASES, AGENTS
from app.modules.ai_agents.dependencies import (
    get_ai_chat_service,
    get_inference_engine,
    get_marketplace_chat_service,
)
from app.modules.ai_agents.runtime import InferenceEngine
from app.modules.ai_agents.schemas import (
    AgentCatalogOut,
    AgentInfoOut,
    AiChatRequest,
    AiChatResponse,
    BookingTicketOut,
    MarketplaceAssistantOut,
    MarketplaceChatRequest,
    PendingCancellationOut,
    ProposedActionOut,
    QueuePlaceOut,
)
from app.modules.ai_agents.service import AiChatService, ChatTurn
from app.modules.analytics.schemas import ChartOut
from app.modules.booking.dependencies import resolve_booking_customer
from app.modules.booking.schemas import HoldSlotResult


def _response(session_id: str, turn: ChatTurn) -> AiChatResponse:
    """A turn as the API returns it: the reply, and what the tools produced."""
    result = turn.result
    return AiChatResponse(
        session_id=session_id,
        agent=turn.agent.name,
        reply=result.reply,
        suggested_actions=result.suggested_actions,
        requires_human_handoff=result.requires_human_handoff,
        related_booking_id=turn.related_booking_id,
        held_slots=[
            HoldSlotResult(
                hold_token=hold.hold_token,
                location_id=hold.location_id,
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
        tickets=[
            BookingTicketOut(
                booking_id=ticket.booking_id,
                tenant_id=ticket.tenant_id,
                business_name=ticket.business_name,
                booking_status=ticket.booking_status,
                starts_at=ticket.starts_at,
                ends_at=ticket.ends_at,
                ticket_id=ticket.ticket_id,
                ticket_code=ticket.ticket_code,
                qr_payload=ticket.qr_payload,
                expires_at=ticket.expires_at,
                ticket_page_url=ticket.ticket_page_url,
            )
            for ticket in turn.tickets
        ],
    )


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
        referral_token=payload.referral_token,
        confirmed_hold_token=payload.confirm_hold_token,
    )

    return _response(payload.session_id, turn)


@router.get(
    "/agents", response_model=AgentCatalogOut, dependencies=[Depends(get_authorized_tenant)]
)
async def list_agents(
    tenant_id: UUID,
    engine: InferenceEngine = Depends(get_inference_engine),
) -> AgentCatalogOut:
    """The roster this deployment runs (docs/13 section 2), with the old aliases.

    Authenticated and tenant-checked like every other tenant route. It used to
    take no dependency at all — the one hole in ADR-0006's fail-closed rule
    outside the public discovery surface ADR-0010 carves out.

    Useful precisely because the answer can be "none that work": PydanticAI is
    an optional extra and Ollama may be offline, and a client should be able to
    hide the chat entry point rather than discovering it only hands off.
    """
    return AgentCatalogOut(
        inference_available=await engine.reachable(),
        available=sorted(AGENTS),
        aliases=dict(AGENT_ALIASES),
        agents=[
            AgentInfoOut(
                name=spec.name,
                audience=str(spec.audience),
                goal=spec.goal,
                required_feature=spec.required_feature,
                required_permission=(
                    str(spec.required_permission) if spec.required_permission else None
                ),
                needs_business=spec.needs_business,
            )
            for spec in AGENTS.values()
        ],
    )


#: The marketplace assistant. Under `/discovery` because, like the rest of the
#: marketplace, it starts with no tenant: the customer has not chosen a business
#: yet, and choosing one is what it helps with. Unlike the listings it needs a
#: signed-in customer, because it books in their name.
marketplace_router = APIRouter(prefix="/discovery/ai", tags=["ai"])


@marketplace_router.post(
    "/chat", response_model=AiChatResponse, dependencies=[Depends(write_rate_limit)]
)
async def marketplace_chat(
    payload: MarketplaceChatRequest,
    service: AiChatService = Depends(get_marketplace_chat_service),
    principal: Principal = Depends(get_customer_principal),
) -> AiChatResponse:
    """One turn with `marketplace_agent`: search any listed business, hold a time
    there, and book it once the customer confirms it (`confirm_hold_token`),
    returning the QR ticket.

    Each booking goes to the tenant of the listing the customer chose, resolved
    by the server from the listing, and is attributed to the marketplace.
    """
    turn = await service.chat(
        message=payload.message,
        session_id=payload.session_id,
        principal=principal,
        customer_id=principal.subject_id,
        self_service=True,
        locale=payload.locale,
        channel=payload.channel,
        agent_name="marketplace_agent",
        confirmed_hold_token=payload.confirm_hold_token,
    )
    return _response(payload.session_id, turn)


@marketplace_router.get("/status", response_model=MarketplaceAssistantOut)
async def marketplace_status(
    principal: Principal = Depends(get_principal),
    engine: InferenceEngine = Depends(get_inference_engine),
) -> MarketplaceAssistantOut:
    """Whether the assistant can answer, so a client can hide its entry point.

    Authenticated like the chat itself: an anonymous visitor could not use it.
    """
    return MarketplaceAssistantOut(inference_available=await engine.reachable())
