"""ai_agents · CONTRACT layer — API boundary DTOs.

Layer rule: pydantic only.

The `AgentOutput` family doubles as each agent's structured output type (docs/10
section 2, docs/13 section 3.3). That is the point of using PydanticAI: output
that does not validate is not a string to be parsed hopefully, it is a retry
and then a handoff.
"""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.ai_agents.guardrails import ProposalTarget, ProposedActionKind
from app.modules.analytics.schemas import ChartOut
from app.modules.booking.schemas import HoldSlotResult


class AgentOutput(ApiSchema):
    """The envelope every agent must produce (docs/10 section 2)."""

    reply: str = Field(max_length=4000)
    suggested_actions: list[str] = []
    requires_human_handoff: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class InsightOutput(AgentOutput):
    """The accountant and the analyst. Ids only: the charts are the tools'."""

    #: Must name charts `render_chart` produced this turn; anything else is dropped.
    chart_ids: list[str] = []
    metrics_used: list[str] = []


class ManagerOutput(InsightOutput):
    """The business manager: advice, never an instruction (docs/13 section 8)."""

    #: Must name actions `propose_action` recorded this turn.
    proposed_action_ids: list[str] = []


class AiChatRequest(ApiSchema):
    """docs/07 section 10.

    `tenant_id` is absent on purpose. docs/07 lists it, but accepting it would
    let the model's caller name the tenant it wants — the authenticated path
    parameter is the only source (docs/10 section 11, tenant scoping).
    """

    #: Names the conversation. Turns sent under the same id, by the same caller,
    #: about the same business, share memory (`history.py`).
    session_id: str = Field(max_length=128)
    message: str = Field(max_length=4000)
    channel: str = Field(default="pwa", max_length=32)
    locale: str = Field(default="ar", max_length=8)
    #: The held time the customer pressed "Yes, book it" on: its `hold_token`,
    #: from an earlier turn's `held_slots`. `book_held_slot` books only this
    #: offer, so a model's reading of "yes" never books by itself (ADR-0015).
    confirm_hold_token: str | None = Field(default=None, max_length=64)

    #: Staff may ask on behalf of a named customer; a customer principal
    #: supplying this is rejected, exactly as in booking.
    customer_id: UUID | None = None
    #: Required by the staff agents, which each work on one business. The
    #: receptionist takes it as context: the storefront the customer is on.
    business_id: UUID | None = None
    #: The marketplace referral the client got for this storefront, so a
    #: booking the agent makes is attributed exactly as the picker's would be.
    #: Booking's attribution verifies it; a made-up one attributes nothing.
    referral_token: str | None = Field(default=None, max_length=200)


class MarketplaceChatRequest(ApiSchema):
    """A turn with the marketplace assistant: no tenant, no business, and no
    `customer_id`, because it books only in the caller's own name."""

    session_id: str = Field(max_length=128)
    message: str = Field(max_length=4000)
    channel: str = Field(default="pwa", max_length=32)
    locale: str = Field(default="ar", max_length=8)
    #: The held time the customer pressed "Yes, book it" on: its `hold_token`,
    #: from an earlier turn's `held_slots`. `book_held_slot` books only this
    #: offer, so a model's reading of "yes" never books by itself (ADR-0015).
    confirm_hold_token: str | None = Field(default=None, max_length=64)


class ProposedActionOut(ApiSchema):
    id: str
    kind: ProposedActionKind
    title: str
    rationale: str
    metric: str
    target_type: ProposalTarget
    target_id: UUID | None
    #: The endpoint a person would use to apply it, from a fixed table. Never
    #: written by the model.
    apply_via: str | None
    requires_confirmation: bool = True


class QueuePlaceOut(ApiSchema):
    """A place the receptionist took in a walk-in queue for the caller."""

    entry_id: UUID
    queue_id: UUID
    place_in_line: int
    estimated_wait_minutes: int | None


class PendingCancellationOut(ApiSchema):
    """A booking the customer asked the agent to cancel. Nothing is cancelled yet.

    Show it, and if the customer agrees, call
    `POST /tenants/{tenant_id}/bookings/{booking_id}/cancel`.
    """

    booking_id: UUID
    starts_at: datetime
    reason: str | None


class BookingTicketOut(ApiSchema):
    """A booking an agent made, with the QR ticket the customer shows to check in.

    `qr_payload` is the credential: render it as a QR code. Reception scans it
    at `POST /tenants/{tenant_id}/tickets/check-in`.
    """

    booking_id: UUID
    tenant_id: UUID
    business_name: str
    booking_status: str
    starts_at: datetime
    ends_at: datetime
    ticket_id: UUID
    ticket_code: str
    qr_payload: str
    expires_at: datetime
    ticket_page_url: str


class AiChatResponse(ApiSchema):
    """docs/07 section 10, with docs/13 section 3.4's additions."""

    session_id: str
    #: The resolved agent, so a caller using an old alias sees the new name.
    agent: str
    reply: str
    suggested_actions: list[str] = []
    requires_human_handoff: bool = False
    related_booking_id: UUID | None = None
    related_ticket_url: str | None = None
    #: Slots a tool held this turn, each with its token: book one with
    #: `POST /tenants/{tenant_id}/bookings` and `hold_token` before `expires_at`.
    #: Present even when the reply hands off, because the hold is real either way.
    held_slots: list[HoldSlotResult] = []
    #: Places a tool took in a walk-in queue this turn, likewise.
    queue_places: list[QueuePlaceOut] = []
    #: Bookings the customer asked to cancel. The agent cancels nothing: the
    #: client asks the customer to confirm, then calls the booking's cancel route.
    pending_cancellations: list[PendingCancellationOut] = []
    #: Bookings an agent made this turn, each with its QR ticket.
    tickets: list[BookingTicketOut] = []

    #: A client should be able to tell a confident answer from one produced by
    #: the routing model after the reasoning model failed, or by the fallback.
    degraded: bool = False
    confidence: float = 0.0

    metrics_used: list[str] = []
    #: Built by the analytics context, taken from what tools rendered this turn.
    charts: list[ChartOut] = []
    proposed_actions: list[ProposedActionOut] = []


class AgentInfoOut(ApiSchema):
    name: str
    audience: str
    goal: str
    required_feature: str | None
    #: The role permission a staff caller needs in this tenant, if any. A client
    #: hides what the caller can't use; the turn still checks it.
    required_permission: str | None = None
    #: Staff agents work on one business, named as `business_id` in the chat.
    needs_business: bool = False


class AgentCatalogOut(ApiSchema):
    #: Names only, kept from the original contract.
    available: list[str]
    #: Old agent names and the agent each now resolves to (ADR-0011).
    aliases: dict[str, str]
    agents: list[AgentInfoOut]
    #: Whether a turn can reach a model right now: the AI extra is installed,
    #: AI is enabled, and the model server answered. False means every turn
    #: would hand off, so a client should say "offline" instead of a chat box.
    inference_available: bool = False


class MarketplaceAssistantOut(ApiSchema):
    """Whether the marketplace assistant can answer right now."""

    inference_available: bool


class ForgottenConversationsOut(ApiSchema):
    """What a request to forget deleted."""

    #: Conversations and offer lists removed; 0 when there was nothing to forget.
    forgotten: int
