---
title: AI Agents and PydanticAI
created: 2026-08-11
project: NOVA
type: ai
tags: [ai, pydanticai, local-llm, ollama, rtx-5090]
---

# AI Agents & PydanticAI Architecture

> [!danger] The Golden Rule of NOVA AI
> **AI Agents are NOT allowed to write directly to the database.** 
> Agents interact with the system exclusively by calling **Application Service tools** which enforce domain rules and validation.

## 1. Framework & Infrastructure
- **Framework:** `PydanticAI` (Chosen for strict type-safety, structured outputs, and dependency injection).
- **Inference Engine:** `Ollama` or `vLLM` running locally on the **RTX 5090 (32GB VRAM)**.
- **Models:** 
  - *Routing/Triage:* `llama3.1-8b` (Fast, low latency).
  - *Complex Reasoning/Support:* `llama3.1-70b-instruct` (Quantized to fit 32GB VRAM, utilizing the 128GB ECC RAM for offloading if necessary).

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