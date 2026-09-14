# 0011 — Business Agents, an Analytics Context, and Server-Built Charts

## Status

Accepted — 2026-09-14. The plan is `docs/13-Business-Agents-and-Analytics.md`; the implementation
follows it.

## Context

docs/10 §3 named a roster of seven agents. ADR-0007 left the insights and retention agents
unavailable because no analytics surface existed; the billing agent shipped later with the billing
module. Salons need five roles from NOVA's AI: a receptionist, a customer-service agent, an
accountant, an analyst and a business manager. Three were put to the product owner:

- the accountant, analyst and manager serve **each salon's own staff**, not NOVA's operators;
- the new agents **replace** the old roster, and the old names become aliases;
- the business manager **advises only**.

Three findings in the code shaped the rest.

1. **Inference has never run on the locked dependency.** `runtime.py` imports `OpenAIModel` from
   `pydantic_ai.models.openai`, and PydanticAI 2.x (locked at 2.31.0) no longer has it: only
   `OpenAIChatModel` and `OpenAIResponsesModel`. The `ImportError` happens inside the turn, is
   caught as an ordinary inference failure, and every chat hands off to a human. Nothing noticed,
   because PydanticAI is an optional extra and no test environment installs it.
2. **The support agent could cancel a stranger's booking.** Its `get_booking_status` and
   `cancel_booking` tools call `BookingService.get` and `cancel` by id without the per-row check
   `POST /bookings/{id}/cancel` performs. A customer principal reaches every tenant (it is a
   marketplace), so a customer who knows or guesses a booking id could cancel it through chat.
3. **No service answers a question about a period.** Booking lists by provider or by customer;
   payment by booking; billing pages without dates. An analyst needs a business's whole window,
   and the architecture test forbids reading another module's tables.

## Decision

### Five agents replace the docs/10 roster, with aliases

`receptionist_agent` absorbs `booking_agent` and `queue_agent`, `customer_service_agent` replaces
`support_agent`, `accountant_agent` replaces `billing_agent`, `analyst_agent` replaces
`insights_agent`, and `business_manager_agent` is new. `concierge_agent` still routes, and
`retention_agent` stays unavailable. An alias resolves before any check, so the old names cannot be
used to skip the staff-only rule.

Each agent is one `AgentSpec` record: goal, audience, tool and chart allowlists, output type,
required plan feature, and instructions. The rules that differ per agent are then data that a test
can read, not branches spread through a service.

### The business manager advises; it never acts

Its only non-read tool, `propose_action`, records a `ProposedAction` of a fixed kind. Each kind maps
to the endpoint a person would use to apply it, and nothing in NOVA executes it. A schedule change
or a hidden listing still goes through the route that enforces staff access, rate limits and
domain rules. That is where those rules live, and an agent that changed a salon's hours by itself
would be the first write path to bypass them.

### Analytics is a context that owns no tables and reads fact projections

`app/modules/analytics/` composes narrow, read-only projections that each owning service exposes:
`BookingService.list_booking_facts`, `PaymentService.list_payment_facts`,
`QueueService.list_queue_facts`, and dated billing ledger queries. Each is a frozen dataclass in the
owner's `domain.py` with only the columns analytics needs — the pattern
`BookingRepository.map_business_ids` set for the payout job. No names, phones or emails leave the
owner. `customer_id` does, as an opaque id for counting distinct and returning customers, and it
never reaches a chart or a reply.

### pandas and numpy compute, plotly draws, and all three are core dependencies

They are imported only by `analytics/metrics.py` and `analytics/charts.py`, both pure and tested
without a database, and an architecture test enforces that confinement. They are core dependencies
rather than an extra like `ai`, because the dashboards are product: they serve every plan and have
to work with the inference engine offline. The cost is about 138 MB installed (numpy 2.5 at 58 MB,
pandas 3.0 at 47 MB, plotly 7.0 at 33 MB).

PydanticAI stays optional at runtime but joins the `dev` dependency group. Tests then run the real
library through `FunctionModel`, so the next renamed class fails a build instead of every chat.

### Money stays exact

Amounts enter pandas as int64 minor units (fils), are summed exactly, and leave as `Decimal`. Floats
appear only inside chart figures, which are presentation. docs/06 §8's "never float" holds for every
KPI a salon owner might act on.

### Charts are Plotly JSON built on the server and drawn by the client

`GET /analytics/charts/{chart_id}` and the chat response both carry Plotly's own figure JSON, which
the SvelteKit dashboard draws with plotly.js. There are two reasons for server-built charts. The
agents need exactly the figures the dashboard shows. And computing in the browser would ship raw
facts to it.

### The model references what tools produced; it never produces numbers, charts or actions

Every tool records what it returns in a per-turn `TurnArtifacts`: charts, proposed actions, metric
names, and every number in its result. The model's structured output lists `chart_ids`,
`proposed_action_ids` and `metrics_used`. The service attaches the recorded objects and drops any id
no tool produced.

For the accountant, analyst and business manager, a PydanticAI output validator also rejects a
reply that states a number no tool returned. It allows one retry, then hands off. Integers from 0
to 10 are exempt ("the top 3 services").

### Plan features gate the AI, not the numbers

`ai_insights_agent` (Studio, Chain) unlocks the analyst and the business manager.
`cross_location_reporting` (Chain) unlocks the branch-by-branch breakdown and its chart. Everything
else in `/analytics/*` and the accountant are on every plan, and the booking and support features
are too. That matches docs/11 §2, which puts the insights agent and cross-location reporting on
paid tiers and says nothing about denying a salon its own numbers.

### The runtime targets PydanticAI 2.x

`OpenAIChatModel` with `OllamaProvider`, a per-agent `output_type`, the grounding output validator,
and `UsageLimits(request_limit=8, tool_calls_limit=12)` so a looping model cannot hold the GPU.
Tests inject a `FunctionModel` through the engine rather than patching the library.

### Customer-facing tools check ownership row by row

`AgentDeps` carries the principal. Every tool that names a booking, payment or queue entry calls the
same `get_for_principal` / `assert_visible_to` / `assert_entry_visible_to` guard its HTTP route
calls, so a customer's chat can do no more than that customer's requests could.

## Consequences

- **The production image grows by about 140 MB**, from roughly 305 MB to 445 MB uncompressed.
- **`/api/v1/tenants/{tenant_id}/analytics/*` is a new read surface.** It is staff-only and
  rate-limited, but a long window is real database work. It is capped at 400 days and 50,000 rows
  per fact query, and computed per request with no cache. When that stops being adequate the fix
  is a nightly rollup table or materialized views, not a redesign.
- **AI clients see changes.** The old agent names still work as aliases, but responses name the
  new agent, and staff agents now require `business_id`.
- **The grounding check is a floor.** Small integers are exempt, and a real number can still be
  attached to the wrong metric; `metrics_used` and the chart are the reader's check.
- **The forecast is a linear trend and says so.** Ramadan, Eid and summer seasonality are not
  modelled.
- **Proposed actions are not stored.** A history of advice would need a table, and a decision about
  who may read it.
- **Chat is still stateless across turns.** "At most one hold per session" (docs/10 §5) remains
  unenforced.
- **Analytics across tenants for NOVA's operators is not built.** It needs a platform principal,
  and `bypass_tenant_scope` stays banned on request paths.

## Alternatives considered

**Add the new agents alongside the old roster.** Rejected when the product owner was asked: five
agents overlapping the existing ones, holding the same tools for the same jobs.

**Aggregate in SQL inside each owning module.** Not chosen for now. Every metric would become a
bespoke query in the module that owns the table, spread over five modules. Pure pandas functions
over facts are testable without a database. Revisit when a window regularly approaches the row cap.

**A denormalised analytics read model.** Rejected as premature, for the reason ADR-0010 gave for
`marketplace_listings`: a second copy that drifts. A stale revenue figure is a wrong revenue figure.

**Server-rendered PNG charts** (matplotlib, or plotly with kaleido). Rejected. kaleido needs a
headless Chromium in the image. A PNG cannot switch language, show values on hover or follow the
dashboard's theme. And WhatsApp, the one channel that would want an image, is the customer channel,
where these charts do not belong.

**Let the model compute from raw rows.** Rejected. A language model summing three thousand prices
is how an owner is told the wrong revenue, and it would put row-level data into the prompt.

**Make analytics an optional extra, like `ai`.** Rejected. The dashboards are sold on every plan
and must work with AI switched off; an extra would make them a deployment choice.

**polars instead of pandas.** Not chosen. pandas was the stated preference, and at one salon's scale
(thousands of rows) either takes milliseconds.
