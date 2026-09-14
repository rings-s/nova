"""Bounded context: AI_AGENTS — PydanticAI agents and their tools.

Aggregates      none — this context owns no tables
Depends on      every other module's SERVICE layer, analytics included
Status          implemented
Plan            docs/10 (framework), docs/13 and ADR-0011 (roster, analytics, charts)

This context has no domain of its own. It is a consumer that wraps other
modules' application services as agent tools.

The roster (docs/13 section 2, `agents.py`):

    concierge_agent          customers   routes a message
    receptionist_agent       customers   a held slot or a place in the queue
    customer_service_agent   customers   the caller's own booking or payment
    accountant_agent         staff       earned, collected, paid out, charged
    analyst_agent            staff       metrics and charts        (Studio, Chain)
    business_manager_agent   staff       proposed actions, advise only (Studio, Chain)

The docs/10 names (booking, queue, support, billing, insights) resolve to these
as aliases. `retention_agent` stays unavailable.

The golden rule (docs/04, docs/10): an agent may NEVER touch the database. It
has no AsyncSession, no repository, no ORM model — only services:

    ✅  ctx.deps.booking_service.create(...)
    ❌  session.add(BookingRecord(...))

That is enforced structurally rather than by review. `AgentDeps` has no session
field, and there is no `models.py` or `repository.py` in this folder to import.
The module's one session is opened by `dependencies.TenantServiceScope`, which
gives each tool call services built on a short transaction of its own. A turn
holds no transaction across inference, so no connection or lock waits on the
model.

No agent can confirm a booking: `confirm` appears in no allowlist, so no agent
has a tool that could reach it. The business manager has no tool that writes.

Guardrails are CODE, not prompt text (docs/10 section 11, docs/13 section 5):

    tenant scoping      `AiChatService.chat`        — rejected before inference
    staff-only agents   `guardrails.assert_caller_may_use_agent`, aliases included
    one named business  `CatalogService.get_business` — 404 outside the tenant
    plan feature        `BillingService.require_feature`
    tool allowlist      `AgentSpec.tools`           — unlisted tools are never
                                                      registered
    per-row ownership   each customer-facing tool   — the route's own guard
    numeric grounding   output validator            — one retry, then handoff
    artifact ids        `AiChatService`             — charts and actions come
                                                      from what tools produced,
                                                      never from model text
    PII redaction       `guardrails.redact_pii`     — pre-prompt
    prompt injection    `guardrails.sanitize_...`   — framed as data
    rate limit          router dependency           — 429 with ErrorResponse

Fallback (docs/10 section 12) is the reason PydanticAI is an optional runtime
extra: every flow in NOVA must remain fully usable with the inference engine
offline. `runtime.py` degrades to a static reply with
`requires_human_handoff=True` when the library is absent, the model is
unreachable, a turn times out, or a reply stays ungrounded. The analytics
dashboards behind the owner agents keep working either way.

Public surface:
    from app.modules.ai_agents.service import AiChatService, AgentDeps
    from app.modules.ai_agents.agents import AGENTS, AGENT_ALIASES, resolve_agent

Internal — do not import from other modules:
    runtime.py, tools.py, dependencies.py, router.py
"""
