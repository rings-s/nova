---
title: AI Agent Catalog
created: 2026-08-14
project: NOVA
type: ai
tags: [ai, agents, pydanticai, tools, guardrails]
related_code:
  - app/modules/ai_agents/agents.py
  - app/modules/ai_agents/tools.py
  - app/modules/ai_agents/schemas.py
  - app/modules/ai_agents/router.py
---

# AI Agent Catalog

> [!important] Goal
> Define every AI agent NOVA runs, the one job it exists to do, the tools it may call, and the line it may not cross.

Framework, model routing, and infrastructure are defined in [[04-AI-Agents-and-PydanticAI]].
This document is the roster.

## Goals

- One agent, one goal — no agent owns two jobs.
- Every agent calls Application Services only; never the ORM, never the database.
- Every agent returns a typed Pydantic result, never free text alone.
- Every agent has an explicit refusal path and a human handoff.
- Every tool call is tenant-scoped and audited.

---

## 1. Agent Placement

```text
app/modules/ai_agents/
  agents.py        # Agent definitions (one per catalog entry below)
  tools.py         # @agent.tool wrappers over Application Services
  deps.py          # AgentDeps container (services, tenant context, locale)
  guardrails.py    # Pre/post validation, refusal policy, PII scrubbing
  schemas.py       # Typed agent inputs and results
  router.py        # /api/v1/ai/* endpoints
```

> [!note] Implemented differences
> The module is laid out differently:
>
> - `agents.py` holds the roster as data: one `AgentSpec` per agent (goal, audience, tool
>   allowlist, output type, instructions, charts, required plan feature), the old names as
>   aliases, and `resolve_agent`.
> - `tools.py` holds `AgentToolkit`, one method per tool. Each one calls an Application Service,
>   is checked against the agent's allowlist, and runs under a timeout.
> - `service.py` holds `AgentDeps`, `TurnArtifacts` and `AiChatService`. There is no `deps.py`.
> - `runtime.py` holds the guarded PydanticAI/Ollama import, the output validator that enforces
>   numeric grounding, and the fallback reply.
> - `guardrails.py`, `schemas.py`, `router.py` and `dependencies.py` match their names above.
>
> The endpoints are nested under the tenant and authenticated like every other route:
> `POST /api/v1/tenants/{tenant_id}/ai/chat?agent=<name>` and
> `GET /api/v1/tenants/{tenant_id}/ai/agents`. The roster is the one in
> [[13-Business-Agents-and-Analytics]] (ADR-0011): `concierge_agent`, `receptionist_agent`,
> `customer_service_agent`, `accountant_agent`, `analyst_agent` and `business_manager_agent`.
> `booking_agent`, `queue_agent`, `support_agent`, `billing_agent` and `insights_agent` still
> work as aliases. `retention_agent` stays unavailable.

Naming conventions:

| Type | Suffix | Example |
|---|---|---|
| Agent instance | `_agent` | `booking_agent` |
| Tool function | verb-first | `get_available_slots` |
| Tool result | `Result` | `HoldSlotResult` |
| Agent output | `Output` | `TriageOutput` |
| Guardrail failure | `Refusal` | `PaymentRefusal` |

---

## 2. Shared Agent Contract

Every agent is constructed with the same dependency container and the same output envelope.

``` python
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext


@dataclass
class AgentDeps:
    tenant_id: UUID
    locale: str                 # "ar" | "en"
    channel: str                # "pwa" | "whatsapp" | "dashboard"
    customer_id: UUID | None
    booking_service: "BookingService"
    queue_service: "QueueService"
    catalog_service: "CatalogService"
    notification_service: "NotificationService"
    analytics_service: "AnalyticsService"
    billing_service: "BillingService"


class AgentOutput(BaseModel):
    reply: str = Field(max_length=4000)
    suggested_actions: list[str] = []
    requires_human_handoff: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
```

Rules:

- `AgentDeps` carries services, never a `AsyncSession`.
- `tenant_id` is injected by the router from the authenticated context, never by the model.
- An agent that cannot satisfy a request sets `requires_human_handoff=True` instead of guessing.
- Every tool result is logged with `session_id`, `tenant_id`, tool name, and outcome.

---

## 3. Agent Roster

| Agent | Goal | Module Surface | Model |
|---|---|---|---|
| `concierge_agent` | Route an incoming message to the right agent. | all | `llama3.1-8b` |
| `booking_agent` | Turn intent into a confirmed booking. | `booking`, `catalog` | `llama3.1-70b` |
| `queue_agent` | Answer and manage walk-in queue state. | `queue` | `llama3.1-8b` |
| `retention_agent` | Bring lapsed customers back. | `notification`, `booking` | `llama3.1-70b` |
| `insights_agent` | Answer owner questions about their numbers. | `analytics` | `llama3.1-70b` |
| `support_agent` | Resolve customer issues or hand off cleanly. | `booking`, `payment` | `llama3.1-70b` |
| `billing_agent` | Explain plan, commission, and invoice charges. | `billing` | `llama3.1-8b` |

> [!note] Superseded roster
> [[13-Business-Agents-and-Analytics]] (ADR-0011) replaces this roster with five agents:
> - `receptionist_agent` absorbs `booking_agent` and `queue_agent`.
> - `customer_service_agent` replaces `support_agent`.
> - `accountant_agent` replaces `billing_agent`.
> - `analyst_agent` replaces `insights_agent`.
> - `business_manager_agent` is new, and only advises.
>
> The old names keep working as aliases. `concierge_agent` still routes, and `retention_agent`
> stays unavailable. This document's shared contract, guardrail layer and fallback rules apply to
> all of them.

---

## 4. Concierge Agent

**Goal:** classify the message and route it. Nothing else.

- **Trigger:** every inbound WhatsApp message and PWA chat turn.
- **Tools:** none. Classification only.
- **Output:**

``` python
from enum import StrEnum


class AgentRoute(StrEnum):
    BOOKING = "booking"
    QUEUE = "queue"
    SUPPORT = "support"
    BILLING = "billing"
    INSIGHTS = "insights"
    HUMAN = "human"


class TriageOutput(BaseModel):
    route: AgentRoute
    locale: str
    intent_summary: str = Field(max_length=280)
    confidence: float = Field(ge=0.0, le=1.0)
```

- **Guardrails:**
  - Never answers the customer directly.
  - `confidence < 0.6` routes to `HUMAN`.
  - Owner-only routes (`INSIGHTS`, `BILLING`) require a staff membership on the tenant.

> [!note] Implemented differences
> A client names the agent directly with `?agent=` instead of going through concierge routing, so
> the owner-only rule is enforced when a turn starts. `assert_caller_may_use_agent` in
> `guardrails.py` refuses `billing_agent` and `insights_agent` to a non-staff principal with a
> 403 `agent_guardrail` error, before any tool or model runs.

---

## 5. Booking Agent

**Goal:** move a customer from intent to a confirmed booking without breaking availability rules.

- **Trigger:** routed from concierge with `route=BOOKING`.
- **Tools:**

| Tool | Service call | Write? |
|---|---|---|
| `search_services(query, location_id)` | `CatalogService.search` | no |
| `get_available_slots(service_id, date_range)` | `BookingService.availability` | no |
| `get_provider_info(provider_id)` | `CatalogService.get_provider` | no |
| `hold_slot(service_id, start_time, minutes=5)` | `BookingService.hold_slot` | yes |
| `create_booking_draft(hold_token, customer_id)` | `BookingService.create_draft` | yes |
| `cancel_booking(booking_id, reason)` | `CancelBookingService.execute` | yes |

- **Guardrails:**
  - Cannot confirm a booking. It may only reach `PENDING_PAYMENT`; confirmation comes from the payment webhook.
  - Cannot hold more than one slot per session.
  - Cannot quote a price it did not read from `CatalogService`.
  - Cannot cancel outside the tenant's `CancellationPolicy`; the domain raises, the agent reports the reason verbatim.
  - Cannot book across tenants.

``` python
class BookingAgentOutput(AgentOutput):
    hold_token: str | None = None
    booking_id: UUID | None = None
    payment_url: str | None = None
```

---

## 6. Queue Agent

**Goal:** tell walk-ins where they stand and keep the queue honest.

- **Trigger:** ticket QR scan follow-up, "how long is the wait", queue status messages.
- **Tools:** `get_queue_position(ticket_id)`, `get_estimated_wait(location_id)`, `join_queue(location_id, service_id)`, `leave_queue(entry_id)`.
- **Guardrails:**
  - Never reveals another customer's name, phone, or ticket.
  - Wait estimates come from `QueueService`, never from the model's own arithmetic.
  - Cannot reorder the queue or call the next customer — that is a reception action.

---

## 7. Retention Agent

**Goal:** win back lapsed customers with an offer the business actually authorised.

- **Trigger:** scheduled ARQ worker (`workers/retention.py`), not a user message.
- **Tools:** `get_lapsed_customers(days_since_last_visit)`, `get_active_promotions(business_id)`, `draft_campaign(segment, promotion_id)`, `queue_whatsapp_message(customer_id, template_id, params)`.
- **Guardrails:**
  - Sends only pre-approved WhatsApp template messages — no free-text outbound.
  - Cannot invent a discount; promotions must exist in `catalog`.
  - Honours marketing opt-out and quiet hours per locale.
  - Campaigns above a configured size require owner approval before send.

---

## 8. Insights Agent

**Goal:** answer an owner's question about their own numbers, with the query it ran.

- **Trigger:** business dashboard chat.
- **Tools:** `query_analytics(start, end, metrics, group_by)`, `get_customer_risk_profiles()`, `get_no_show_breakdown(period)`.
- **Guardrails:**
  - Read-only. No tool in this agent writes.
  - Scoped to the caller's `tenant_id`; cross-tenant benchmarks are aggregated and anonymised.
  - Every claim cites the metric and window it came from.
  - Refuses to answer where the sample is below the reporting threshold.

``` python
class InsightsOutput(AgentOutput):
    metrics_used: list[str]
    period_start: date
    period_end: date
    recommended_campaign: str | None = None
```

---

## 9. Support Agent

**Goal:** resolve the issue with the tools it has, or hand off with full context.

- **Trigger:** routed from concierge with `route=SUPPORT`.
- **Tools:** `get_booking(booking_id)`, `get_payment_status(booking_id)`, `resend_ticket(booking_id)`, `request_refund(payment_id, reason)`, `escalate_to_human(summary)`.
- **Guardrails:**
  - Cannot issue a refund. `request_refund` opens a request; a human approves it.
  - Cannot alter payment or booking state directly.
  - Two failed resolution attempts force `requires_human_handoff=True`.
  - Escalation payload carries the conversation summary, never raw payment credentials.

---

## 10. Billing Agent

**Goal:** explain what a business is being charged and why.

- **Trigger:** owner asks about plan, commission, or an invoice line.
- **Tools:** `get_subscription(business_id)`, `get_invoice(invoice_id)`, `explain_commission_line(line_id)`, `get_plan_comparison()`.
- **Guardrails:**
  - Read-only. Cannot change a plan, apply a credit, or waive a commission.
  - Plan and rate figures are read from `BillingService`, never recalled from the model.
  - Plan-change intent produces a `suggested_action`, not a mutation.

Pricing definitions live in [[11-Pricing-and-Subscriptions]].

---

## 11. Guardrail Layer

Guardrails are code in `guardrails.py`, not prompt text.

| Guardrail | Enforced where | Failure behaviour |
|---|---|---|
| Tenant scoping | `AgentDeps` construction | request rejected before the model runs |
| Tool allowlist | agent definition | tool is not registered, so it cannot be called |
| Write authorisation | Application Service | domain exception surfaced as a refusal |
| PII redaction | pre-prompt | phone, email, and payment refs masked before inference |
| Output validation | Pydantic `result_type` | one retry, then handoff |
| Rate limit | router dependency | 429 with `ErrorResponse` |
| Prompt injection | pre-prompt | tool calls from message content are ignored |

Rules:

- Untrusted text (customer messages, review text, business bio) is never treated as instruction.
- A tool that is not in the agent's allowlist does not exist for that agent.
- Model output that fails validation is retried once, then handed to a human.

---

## 12. Fallback Behaviour

| Condition | Behaviour |
|---|---|
| Ollama unreachable | endpoint returns `requires_human_handoff=True` with a static reply |
| 70b model out of VRAM | fall back to `llama3.1-8b` and flag reduced confidence |
| Tool timeout (>5s) | abort the turn, hand off, log the tool name |
| Repeated validation failure | disable that agent for the session |

The booking, queue, and payment flows must remain fully usable with every agent offline.

---

## 13. Testing Requirements

- Each agent has a guardrail test asserting the forbidden action fails.
- Tool wrappers are tested against real Application Services, not mocks of the domain.
- Tenant isolation is tested per agent: agent A on tenant 1 cannot read tenant 2.
- Prompt-injection fixtures cover message, review, and business-bio inputs.
- Fallback tests run with the inference engine stubbed as unavailable.
