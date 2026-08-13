# Future AI Integration

Not built yet. No AI code exists in this scaffold — this doc captures the constraints agreed
before any is written, so the first AI module doesn't have to rediscover them.

## Non-negotiable constraints

- Agents are built with **PydanticAI**.
- Agents must **not** touch the database directly. They call controlled application/domain
  tools — the same `commands.py`/`queries.py` handlers a router would call — never raw SQL or
  ORM sessions.
- Agents are **never the source of truth** for bookings, availability, payments, tickets, or
  queue order. Those stay fully deterministic, owned by the relevant module's commands/queries.
- Local models are the primary runtime (Ollama or an OpenAI-compatible server on the RTX 5090).
  Cloud AI is a fallback only, used when local inference is unavailable or explicitly
  configured — never the default.
- Prefer quantized models when memory-constrained (see the 64GB-RAM fallback note in
  [[../architecture/tech-stack]] and `infra/README.md`).

## Where AI code will live

Every module has a reserved `ai/` package (e.g. `backend/app/modules/tenants/ai/`) for
PydanticAI tool bindings scoped to that module — empty today. A module's AI tools should wrap
its own commands/queries, not reach into another module's internals.

## To verify before building

- Which local model(s) fit the target hardware (RTX 5090, 32GB VRAM) at acceptable latency for
  support/sales/retention use cases.
- Structured-output schema conventions (Pydantic models shared between the agent and the
  domain tools it calls).
- Observability approach for agent behavior — "Observable AI behavior" is a stated quality bar
  but no logging/tracing convention exists yet.
