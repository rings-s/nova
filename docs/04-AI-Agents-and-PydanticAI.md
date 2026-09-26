---
title: AI Agents and PydanticAI
created: 2026-08-11
project: NOVA
type: ai
status: design
tags: [ai, pydanticai, local-llm, ollama, lm-studio, rtx-5090]
---

# AI Agents & PydanticAI Architecture

> [!danger] The Golden Rule of NOVA AI
> **AI Agents are NOT allowed to write directly to the database.**
> Agents interact with the system exclusively by calling **Application Service tools** which enforce domain rules and validation.

## 1. Framework & Infrastructure

- **Framework:** `PydanticAI` (Chosen for strict type-safety, structured outputs, and dependency injection).
- **Inference Engine:** `Ollama` or `vLLM` running locally on the **RTX 5090 (32GB VRAM)**.
- **Models:**
  - _Routing/Triage:_ `llama3.1-8b` (Fast, low latency).
  - _Complex Reasoning/Support:_ `llama3.1-70b-instruct` (Quantized to fit 32GB VRAM, utilizing the 128GB ECC RAM for offloading if necessary).

## 2. Agent Definitions

### A. The Triage & Booking Agent

- **Trigger:** Customer sends a WhatsApp message or uses the PWA chat.
- **Tools Provided:**
  - `get_available_slots(service_id, date)`
  - `get_provider_info(provider_id)`
  - `hold_slot_temporarily(slot_id, minutes=5)`
- **Guardrails:** Cannot confirm a booking without a valid payment intent or deposit confirmation.

### B. The Business Intelligence Agent

- **Trigger:** Business owner asks "Why were no-shows high yesterday?"
- **Tools Provided:**
  - `query_analytics(start_date, end_date, metrics)`
  - `get_customer_risk_profiles()`
- **Output:** Structured Pydantic models containing insights and suggested WhatsApp re-engagement campaigns.

## 3. PydanticAI Tool Example

```python
from pydantic_ai import Agent, RunContext
from domain.bookings import BookingService
from pydantic import BaseModel

class SlotHoldResult(BaseModel):
    success: bool
    hold_token: str | None
    message: str

# The Agent depends on the Application Service, NOT the database
booking_agent = Agent(
    'ollama:llama3.1-70b',
    deps_type=BookingService,
    result_type=str
)

@booking_agent.tool
async def hold_slot(
    ctx: RunContext[BookingService],
    service_id: str,
    start_time: datetime
) -> SlotHoldResult:
    """Temporarily holds a slot while the customer completes payment."""
    try:
        token = await ctx.deps.hold_slot(service_id, start_time)
        return SlotHoldResult(success=True, hold_token=token, message="Slot held for 5 mins.")
    except SlotUnavailableError:
        return SlotHoldResult(success=False, hold_token=None, message="Slot is gone.")
```

## 4. As implemented (2026-09-23)

> [!note] Implemented differences
> The design above is the original sketch. The code is in `app/modules/ai_agents/`, with
> the roster and guardrails in docs/10 and docs/13 and ADR-0011.

### Model servers

`AI_PROVIDER` chooses **Ollama** or **LM Studio**. Both speak the OpenAI chat protocol at `/v1`,
so one `OpenAIChatModel` serves either. `runtime.py` is the only file that imports PydanticAI:

| Setting                      | Purpose                                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------ |
| `AI_PROVIDER`                | `ollama` (default) or `lmstudio`                                                                 |
| `AI_BASE_URL`                | the server's `/v1` URL; falls back to `OLLAMA_BASE_URL`                                          |
| `AI_ROUTING_MODEL`           | the fast model: the concierge agent, and the retry when the reasoning model fails                |
| `AI_REASONING_MODEL`         | every other agent                                                                                |
| `AI_THINKING`                | `false` (default) adds Qwen3's `/no_think` switch; thinking made a qwen3-8b turn about 5x slower |
| `AI_REQUEST_TIMEOUT_SECONDS` | past this, the turn hands off to a human                                                         |
| `AI_API_KEY`                 | only if the server was started with authentication                                               |

With LM Studio, a model id such as `qwen/qwen3-8b` gets its family's profile (Qwen) by the part
after the slash. A reasoning model's thinking is read from `reasoning_content`, so it is never
shown as the answer.

### Where agents appear

- **Staff:** `/app/ai` in the dashboard lists the owner agents that this role's permissions allow
  (`required_permission`, from `GET /ai/agents`). Each works on the active business. Plan-gated
  agents (`required_feature`, the Studio plan) carry a badge, and the turn enforces the plan.
- **Customers:** a floating assistant on each storefront runs the receptionist agent, and one on
  `/discover` runs the marketplace agent across every listed business
  (`POST /api/v1/discovery/ai/chat`). Both hold a time and then, in a later turn after the
  customer presses "Yes, book it" on it (the request's `confirm_hold_token`), book it with
  `book_held_slot`, returning the QR ticket in `tickets`
  (ADR-0015). Offers live server-side with their hold tokens; the model never sees a token or
  a QR payload. Businesses check tickets in at `/app/check-in`.
- `GET /ai/agents` reports `inference_available` (cached for 15 s). Clients hide the assistant, or
  show an offline state, instead of offering a chat that could only hand off.

### Hardware reality

The sizing in section 1 assumes an RTX 5090. On a CPU-only laptop (i7-1185G7) qwen3-8b ran at
about 1 token/s and qwen3-4b at about 2, too slow for a full agent turn: a 1,000–3,000 token prompt
and 3–4 model calls. qwen3-1.7b completed a grounded accountant turn, chart included, in 270 s. It
runs both roles there, with `AI_REQUEST_TIMEOUT_SECONDS=600` and the model loaded with one parallel
slot so the prompt cache carries across a turn's calls. Small models sometimes echo a structured
field into the reply (`<chart_ids>…</chart_ids>`); `runtime.clean_reply` strips it. Setup steps
are in `nova_backend/README.md`, "AI agents (local models)".
