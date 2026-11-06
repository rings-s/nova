# NOVA Backend — Code Structure

How this codebase is organised and where to put new code.
Architecture rationale lives in `docs/02-Backend-FastAPI-DDD-Structure.md`.

## The one rule

Dependencies point **inward**. The domain is the centre and knows nothing about the outside.

```
router.py  ──▶  service.py  ──▶  domain.py  ◀──  repository.py
   HTTP          use cases        the rules        persistence
```

| Layer           | May import                          | Must never import        |
| :-------------- | :---------------------------------- | :----------------------- |
| `router.py`     | schemas, service, dependencies      | models, repository       |
| `service.py`    | domain, repository, models, events  | fastapi                  |
| `domain.py`     | stdlib, pydantic, `app.core.values` | fastapi, sqlalchemy      |
| `repository.py` | models, `app.db`                    | fastapi, service         |
| `models.py`     | sqlalchemy, `app.db`                | fastapi, service, domain |

If you are unsure which layer a file is, open it — every file starts with a
header naming its layer and its import rule.

## Where everything lives

```
nova_backend/
├── app/
│   ├── main.py              app factory, middleware, router registration
│   │
│   ├── core/                shared kernel — no business rules
│   │   ├── config.py        Settings from env
│   │   ├── deps.py          get_db_session, get_tenant_context
│   │   ├── exceptions.py    DomainError → NotFound/Conflict/Validation
│   │   ├── error_handlers.py  turns DomainError into an HTTP response
│   │   ├── schemas.py       ApiSchema, Page, ErrorResponse
│   │   ├── values.py        Money, TimeRange       (pure domain)
│   │   ├── validators.py    phone, slug, bilingual (pure domain)
│   │   ├── events.py        publish_event + DomainEvent base
│   │   ├── pagination.py    PageParams
│   │   └── logging.py
│   │
│   ├── db/                  persistence kernel
│   │   ├── base.py          DeclarativeBase + constraint naming convention
│   │   ├── mixins.py        UUIDPK, Timestamp, TenantOwned, SoftDelete
│   │   ├── session.py       async engine and sessionmaker
│   │   └── repository.py    BaseRepository, TenantScopedRepository
│   │
│   ├── modules/             one folder per bounded context
│   │   ├── registry.py      the single place every module is wired in
│   │   ├── identity/        ✅ Tenant, User, Membership, Customer
│   │   ├── catalog/         ✅ Business, Location, Service, Provider, BusinessPhoto
│   │   ├── discovery/       ✅ MarketplaceReferral  ← the only public, cross-tenant slice
│   │   ├── booking/         ✅ Booking, Schedule, SlotHold  ← reference implementation
│   │   ├── queue/           ✅ Queue, QueueEntry, Ticket
│   │   ├── review/          ✅ Review  ← verified 1-5 ratings of completed visits
│   │   ├── payment/         ✅ Payment, Refund
│   │   ├── billing/         ✅ Subscription, CommissionLine, Invoice, Payout
│   │   ├── analytics/       ✅ owner reports and Plotly charts (pandas, numpy)  ← owns no tables
│   │   ├── notification/    ✅ Notification
│   │   ├── ai_agents/       ✅ PydanticAI agents (calls services, never the DB)
│   │   ├── call_center/     ✅ PhoneLine, Call  ← Sara answers the phone (ADR-0017, Unifonic)
│   │   ├── support/         ✅ FollowUp  ← the inbox behind "someone will get back to you"
│   │   └── admin/           ✅ AdminAuditEntry  ← superuser console: reads every table, audited
│   │
│   ├── integrations/        outbound adapters (Moyasar, WhatsApp, Unifonic Voice) + images.py, storage/ (photos)
│   └── worker/              outbox dispatcher + scheduled jobs (ARQ)
│
├── alembic/                 migrations
└── tests/                   mirrors app/modules/
```

✅ implemented · ⬜ scaffolded, not yet implemented

All twelve contexts are implemented. The agent roster (receptionist, customer service,
accountant, analyst, business manager) and the charts are specified in docs/13 and ADR-0011.
`ai_agents` needs the optional `ai` extra and a reachable
vLLM server (the compose `llm` service) to do inference; it degrades to a human handoff without them, and every other flow is
unaffected (docs/10 section 12).

## Anatomy of a module

Every module under `app/modules/` has the same files, in the same roles.
Open any module and you already know your way around it.

The exception is `analytics`, which owns no tables. It has no `models.py`, `repository.py` or
`events.py`. It reads other modules' fact projections through their services, and adds
`metrics.py` (pandas and numpy, the only place they are imported) and `charts.py` (Plotly).

`admin` (the platform console at `/admin`, superusers only) also differs. Its repository reads
every table generically through `Base.metadata`, never another module's ORM classes, and it owns
no events. It writes through the curated actions in `admin/domain.py`, each run through the owning
module's service, and through direct edits that add, change or delete any row but the audit log's
as plain SQL (no module rule or event runs). Both are scoped to the row's tenant and audited.

| File              | Layer       | Holds                                             |
| :---------------- | :---------- | :------------------------------------------------ |
| `__init__.py`     | —           | context summary: aggregates, deps, public surface |
| `router.py`       | delivery    | FastAPI endpoints. No business rules.             |
| `schemas.py`      | contract    | Pydantic request/response DTOs                    |
| `service.py`      | application | use-case orchestration; flushes, never commits    |
| `domain.py`       | **domain**  | the rules. No framework imports.                  |
| `models.py`       | persistence | SQLAlchemy ORM tables                             |
| `repository.py`   | persistence | queries, tenant-scoped                            |
| `events.py`       | domain      | domain event dataclasses                          |
| `exceptions.py`   | domain      | module errors, subclassing `DomainError`          |
| `dependencies.py` | delivery    | FastAPI DI providers                              |

Three of these are not the same thing, and mixing them is the most common mistake:

- `schemas.py` is the **API boundary** — what the outside world sends and sees.
- `models.py` is **infrastructure** — table shape.
- `domain.py` is the **model** — the rules that must hold regardless of either.

## Two styles of `domain.py`

Not every module earns a rich domain entity. We pay for the mapping layer only
where there is a real lifecycle to protect.

**Pure functions** — `identity`, `catalog`, `discovery`, `review`, `notification`.
Rules are field-level validation; the ORM model _is_ the domain object.

```python
def validate_service_duration(duration_minutes: int) -> int: ...
```

**Rich entities** — `booking`, `queue`, `payment`, `billing`.
These own a state machine, so the entity is defined in `domain.py` independent
of the ORM, and the repository maps between them.

```python
class Booking:
    def confirm(self) -> None:
        if self.status not in (BookingStatus.DRAFT, BookingStatus.PENDING_PAYMENT):
            raise InvalidBookingTransition(self.status, BookingStatus.CONFIRMED)
        self.status = BookingStatus.CONFIRMED
```

The test: _can this thing be in a wrong state?_ A service with a bad price is
rejected at the edge. A booking that is `COMPLETED` without ever being
`CHECKED_IN` is a corrupted aggregate — that needs an entity.

## Tracing one request

`POST /api/v1/tenants/{tenant_id}/catalog/services`

1. `main.py` matched the route from `modules/registry.py`.
2. `catalog/router.py` validates the body into `CreateServiceRequest`.
3. `core/deps.py::get_tenant_context` reads `tenant_id` **from the path only**.
4. `catalog/dependencies.py` builds `CatalogService` with repositories already
   scoped to that tenant.
5. `catalog/service.py::create_service` calls `get_location` (proving the
   location belongs to this tenant), then the `domain.py` validators.
6. On a broken rule, `domain.py` raises `ValidationDomainError` — not an
   `HTTPException`. `core/error_handlers.py` turns it into a 422.
7. The repository adds the row; the service flushes.
8. The **router** commits. Services never commit, so one endpoint can compose
   several service calls atomically.

## Multi-tenancy

Every table except `tenants` carries `tenant_id` via `TenantOwnedMixin`, and
every repository for those tables extends `TenantScopedRepository`, which has
no unscoped query method to reach for by mistake.

`tenant_id` is fixed at repository construction from the URL path. It is never
read from a request body or query parameter.

Postgres Row-Level Security backs this up (migration `d4e5f6a7b8c9`): each
request sets `app.current_tenant_id` on its connection and every policy compares
against it, so a connection that never sets it sees nothing. It fails closed.
See `docs/decisions/0003-tenant-isolation-strategy.md`.

**The one exception is `discovery`** (ADR-0010). A customer searching for a
salon has no tenant yet, so the marketplace reads _across_ tenants through
`catalog`'s `PublicCatalogService` and a second RLS window,
`app.discovery_mode`. That window is narrower than it sounds: `FOR SELECT` only,
and matching only rows a business has published — active, listed, not deleted.
Nothing on that path can write across tenants, and an unlisted salon is
invisible to the database rather than merely filtered by the query.

A Postgres **superuser bypasses RLS entirely**, even with `FORCE`, and so does a
`BYPASSRLS` role. The API and worker therefore connect as `nova_app`, which is
neither (migration `e1f2a3b4c5d6`), and only migrations run as the schema owner
(`MIGRATION_DATABASE_URL`). A staging or production process connected as an
exempt role refuses to start (`app.db.session.enforce_rls_role`). The test suite
runs as `nova_app` too, so every run exercises the policies.

## Adding a module

1. Copy the file set above into `app/modules/<name>/`.
2. Write `__init__.py` first — naming the aggregates and the public surface
   forces the boundary decision before any code exists.
3. Use `TenantOwnedMixin` + `TenantScopedRepository` unless it is the tenant root.
4. Register it in `app/modules/registry.py` (models import + router).
5. `uv run alembic revision --autogenerate -m "..."`, then **read the migration**.
6. Add `tests/modules/<name>/` with `test_domain.py` (no DB), `test_repository.py`
   (tenant isolation), `test_router.py` (end-to-end).

## Cross-module calls

Modules talk through **services**, never through each other's repositories or
models. Booking needs a service's duration, so it calls
`CatalogService.get_service()` — it does not import `catalog.models.Service`
and query it.

For anything that is a reaction rather than a question, publish a domain event
instead: booking publishes `BookingConfirmed`; notification reacts. Booking must
not import notification.

## Payments (Moyasar)

Payments go through [Moyasar](https://docs.moyasar.com/), following its API
reference. The adapter is `app/integrations/payments/moyasar.py`; the rules
are in `modules/payment`.

**The flow**

1. `POST /tenants/{id}/payments/intents` opens a Moyasar **invoice**
   (`POST /v1/invoices`) for the booking's price, in halalas, so the server
   decides the amount.
2. With `MOYASAR_PUBLISHABLE_KEY` set, the response's `checkout` holds the
   options for Moyasar's
   [Payment Form](https://docs.moyasar.com/guides/card-payments/basic-integration)
   (`moyasar-payment-form`, `Moyasar.init`), bound to that invoice by
   `invoice_id`. The booking page renders it (`MoyasarForm.svelte`), offering
   mada, Visa, Mastercard and STC Pay. Card details go from the browser straight
   to Moyasar, and Moyasar refuses a form payment whose amount differs from the
   invoice's. Without the key, `redirect_url`, the invoice's hosted page, is
   the fallback. Apple Pay is not enabled in the form: it needs the domain
   verified with Moyasar and Apple's script allowed by the CSP.
3. After 3-D Secure, Moyasar sends the payer to the `return_url` the client
   gave, with `payment=<id>` added (and, from the form, Moyasar's own `id`,
   `status` and `message`, none of them trusted). The page calls
   `POST …/payments/{id}/sync`, which
   fetches the invoice and its payment from Moyasar and captures only if the
   status is `paid` and the amount, currency and invoice all match. The redirect
   itself proves nothing.
4. Moyasar also sends a `payment_paid` webhook to `POST /api/v1/webhooks/moyasar`.
   It is authenticated by the `secret_token` in its body, deduplicated by event
   id, and checked against Moyasar's record of the payment just like a sync.
   Either path confirms the booking; whichever arrives second changes nothing.

A declined card does not fail the payment while the checkout is still open,
because the payer can try another card. The payment fails once the invoice
expires (`MOYASAR_CHECKOUT_TTL_MINUTES`, default 30) or is cancelled.

**Setting it up**

1. In the [Moyasar dashboard](https://dashboard.moyasar.com), under Settings >
   API Keys, copy the **secret** key and the **publishable** key. Use the test
   pair (`sk_test_…`, `pk_test_…`) until go-live. The app refuses to start with
   a `pk_…` key as `MOYASAR_API_KEY` or an `sk_…` key as
   `MOYASAR_PUBLISHABLE_KEY`, with a test and a live key mixed, and with any
   test key when `ENV=production`.
2. Under Settings > Webhooks, add
   `https://<your public host>/api/v1/webhooks/moyasar` with a shared secret of
   your choosing (`openssl rand -hex 32`). Subscribe to at least
   `payment_paid` and `payment_failed`.
3. Set them in `infra/.env` and restart the stack (`make dev`):

   ```dotenv
   MOYASAR_API_KEY=sk_test_...
   MOYASAR_PUBLISHABLE_KEY=pk_test_...
   MOYASAR_WEBHOOK_SECRET=<the webhook's shared secret>
   ```

4. `PUBLIC_APP_URL` must be the customer app's origin. A `return_url`
   anywhere else is refused.

Without a key, payment routes answer 503 `integration_not_configured`, and the
rest of the app runs as normal. Locally, Moyasar cannot reach your webhook
unless you expose it (`make tunnel`). Payments still confirm through the sync
step when the payer returns. To test, pay with Moyasar's
[test cards](https://docs.moyasar.com/guides/card-payments/test-cards/).

A `live: false` (test-mode) webhook is ignored when `ENV=production`. Refunds
go through `POST …/payments/{id}/refund` (owners and managers). A refund made
in Moyasar's dashboard is not synced back to NOVA.

## Sara on the phone (Unifonic Voice)

Sara (`call_center_agent`, ADR-0017) answers a business's phone. Unifonic carries the call as
webhook turns; NOVA's own agent decides what she says. To connect a number:

1. Buy a Saudi number in the Unifonic console and give it an **inbound application**.
2. Set `VOICE_PUBLIC_BASE_URL` to the API's public origin (the tunnel's, locally) and
   `VOICE_AI_BASE_URL` / `VOICE_AI_MODEL` / `VOICE_AI_API_KEY` to a fast vLLM server (on a
   GPU; unset, Sara uses the `llm` service). A caller cannot wait for the local
   CPU model; each turn times out after
   `VOICE_AI_REQUEST_TIMEOUT_SECONDS` (6). Speech Unifonic recognised with a `confidence` under
   `VOICE_MIN_SPEECH_CONFIDENCE` (0.3; 0 switches it off) is asked for again and never reaches the
   model; `nova_voice_unclear_speech_total` counts how often. Check Unifonic's scale on a live
   account: on 0–100, 0.3 lets everything through. The model and Sara's voice share
   `VOICE_TURN_BUDGET_SECONDS` (8): keep it under Unifonic's own wait for a reply.
3. As a superuser, `POST /api/v1/tenants/{tenant_id}/call-center/lines` with `business_id` and
   `number_e164`. Paste the returned `answer_url` into the inbound application. It is the line's
   credential: `POST …/lines/{id}/rotate` replaces it.
4. The business needs a plan with `ai_call_center` (Studio or Chain).
5. Get the WhatsApp template `call_verification_code` (one parameter, `code`) approved, or Sara
   cannot verify callers before reading their bookings. Also `booking_received` (`customer_name`,
   `business_name`, `service_name`, `starts_at`, `ticket_url`): what a caller is sent after Sara
   books, saying the business will confirm it.
6. For Sara's own Saudi voice, serve Qwen3-TTS (see below) and set `VOICE_TTS_BASE_URL`.
   Without it, Unifonic's text-to-speech reads her replies.
7. For reminder calls, set `UNIFONIC_VOICE_API_KEY`. The worker rings customers with
   `voice_consent` about confirmed bookings 2–24 hours ahead, 10:00–21:00 local time.

### Sara's voice: Qwen3-TTS

Qwen3-TTS has no Arabic of its own, so the model is the Saudi fine-tune
[`vadimbelsky/qwen3-TTS-KSA`](https://huggingface.co/vadimbelsky/qwen3-TTS-KSA) (Apache-2.0, one
voice, `ksa_speaker`). NOVA calls any OpenAI-compatible `POST /v1/audio/speech` server; its own is
the compose `tts` service (`infra/tts`, ADR-0018), a small FastAPI app around the model's `qwen-tts`
package. Neither vLLM, which serves the text model, nor llama.cpp before it can serve this
checkpoint.

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.gpu.yml \
    --env-file infra/.env --profile tts up -d --build tts
```

Then set `VOICE_TTS_BASE_URL=http://tts:8091/v1` and recreate `backend` and `worker`. The first
start downloads the weights (about 4.5 GB) into the `tts_models` volume. The model speaks at
24 kHz; the service resamples every clip to the `sample_rate` NOVA asks for (8000 Hz, the phone
line's, `VOICE_TTS_SAMPLE_RATE`) and returns mono 16-bit PCM WAV. It generates one clip at a time.
Setting `VOICE_TTS_API_KEY` makes the service require it too. Without the GPU override, build it
for CPU with `TTS_TORCH_INDEX=https://download.pytorch.org/whl/cpu`: that works for listening to it,
but a CPU is far slower than `VOICE_TTS_TIMEOUT_SECONDS` allows, so on a call Unifonic's voice would
read nearly every reply.

Listen to the [demo](https://huggingface.co/spaces/vadimbelsky/saudi-tts-demo) before going live:
the authors call the model not production-ready, and whether `ksa_speaker` is a woman's voice, as
Sara's should be, is unconfirmed.

Unifonic's documentation is behind a login, so check these on a live account before go-live: the
inbound request's field names and the recognised-speech field (`_SPEECH_FIELDS` in
`app/integrations/voice/unifonic.py`), the outbound `POST /calls` endpoint and its auth, and how
long Unifonic waits for a webhook reply, and whether `play` accepts an audio URL (Sara's own voice
depends on it).

## AI agents (local models)

The agents in `modules/ai_agents` run on a model server on your own machine,
through PydanticAI. The roster, tools and guardrails are in docs/10 and docs/13.
The server connection is in `runtime.py`, and nothing else in the app knows
which server is running.

**Where agents appear**

- `/app/ai` in the dashboard: the accountant, analyst and business manager
  agents, for the business being managed. The list shows only the agents this
  role's permissions allow. Charts and proposed actions come from the tools.
- The storefront (`/discover/<slug>`): an "Ask the assistant" button that opens
  the receptionist agent for signed-in customers.
- `/discover`: the marketplace assistant (`POST /discovery/ai/chat`, customers
  only). It searches every listed business, holds a time, and books at the one
  the customer picks, attributed to the marketplace.
- Both assistants **book for the customer in two turns** (ADR-0015). A hold tool
  offers a time; `book_held_slot` books it only in a later turn, after the
  customer presses its "Yes, book it" (`confirm_hold_token`), and returns the booking's **QR ticket** in `tickets`. The
  booking is a `draft` until the business confirms it. Customers see the QR in
  the chat and under My bookings ("Show ticket"). The business scans it at
  `/app/check-in`, by camera or by pasting the code.
- Both call `GET /tenants/{id}/ai/agents` first. Its `inference_available` is
  false when the model server does not answer. The storefront then hides the
  button, and `/app/ai` shows an "offline" panel.

**The model server: vLLM** (ADR-0019)

Every environment serves the model with vLLM, the compose `llm` service, which
`make dev` starts with the rest of the stack. The base compose file runs vLLM's
CPU build (`public.ecr.aws/q9t5s3a7/vllm-cpu-release-repo:v0.10.2`, which needs
AVX-512); `infra/docker-compose.gpu.yml` switches it to the CUDA build
(`vllm/vllm-openai:v0.10.2`):

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.gpu.yml \
    --env-file infra/.env up -d llm
```

On first start it downloads `LLM_MODEL` from Hugging Face into the `llm_models`
volume and answers as `LLM_ALIAS`. The default is Qwen3-4B (`Qwen/Qwen3-4B`, as
`qwen3-4b`), for a GPU. vLLM loads full-precision weights, about 8 GB for the
4B, so a CPU-only machine serves Qwen3-1.7B (about 3.4 GB) instead:

```dotenv
LLM_MODEL=Qwen/Qwen3-1.7B
LLM_ALIAS=qwen3-1.7b
AI_ROUTING_MODEL=qwen3-1.7b
AI_REASONING_MODEL=qwen3-1.7b
```

These are the backend's defaults, and what `infra/.env.example` sets:

```dotenv
AI_PROVIDER=vllm
AI_BASE_URL=http://llm:8000/v1
AI_ROUTING_MODEL=qwen3-4b            # the service's --served-model-name (LLM_ALIAS)
AI_REASONING_MODEL=qwen3-4b
AI_THINKING=false
```

The service parses Qwen3's tool calls (`--enable-auto-tool-choice
--tool-call-parser hermes`) and its thinking (`--reasoning-parser qwen3`, into
`reasoning_content`, never shown). Thinking is off two ways: every request sends
the chat template's `enable_thinking: false` (`runtime.py`, `_model_settings`),
and the instructions end in `/no_think`. Keep `qwen3` in the alias, or neither
is sent. It runs one sequence at a time (`LLM_PARALLEL`, vLLM's
`--max-num-seqs`) with an 8,192-token context (`LLM_CTX`); on a GPU raise the
first together with `AI_MAX_CONCURRENT_TURNS`. On the CPU build,
`LLM_CPU_KVCACHE_GIB` (2) is the RAM set aside for the KV cache. Nothing
publishes its port.

**Speed**

A turn sends the agent's instructions and tool schemas, typically 1,000 to 3,000
tokens, and may call the model several times. `AI_THINKING=false`, the default,
adds Qwen3's `/no_think` switch to the instructions. That cut a small
tool-calling turn from 319 s to 59 s with qwen3-8b. PydanticAI's
generic `thinking=False` (sent as `reasoning_effort`) did not finish that turn
within 10 minutes in testing, so it is not used.

vLLM on a CPU has not been measured here yet. For reference, on a CPU-only
laptop (i7-1185G7, 16 GB) with quantised GGUF weights (LM Studio and llama.cpp,
before 2026-10-28), in tokens per second:

| Model      | Reading the prompt | Generating |
| ---------- | ------------------ | ---------- |
| qwen3-8b   | ~2                 | ~1         |
| qwen3-4b   | ~4.5               | ~1.9       |
| qwen3-1.7b | ~10–27             | ~3–14      |

With qwen3-1.7b there, the accountant's "How much did we earn this month?" took
270 s over 3–4 model calls, with a real chart. vLLM's CPU build reads
full-precision weights for every token, so expect it no faster; that laptop runs
it with `AI_REQUEST_TIMEOUT_SECONDS=1800`. One sequence at a time keeps a turn's
follow-up calls on the prompt prefix vLLM already cached.

When the model is unreachable or times out, the turn hands off to a human. It
never fails the request, and the rest of the app is unaffected.

**Capacity, measurement and what is kept**

- **Turn limit.** `AI_MAX_CONCURRENT_TURNS` (default 1) turns run at once per API
  process and each caller gets one at a time; a further turn waits
  `AI_QUEUE_WAIT_SECONDS` (default 15), then gets `429 ai_busy`. Set the first to
  the server's: the `llm` service with `LLM_PARALLEL=N` runs N sequences at a time. With several API replicas, divide the slots among them.
- **Metrics.** `/metrics` (with `METRICS_TOKEN` set) carries
  `nova_ai_turns_total{agent,outcome}` (ok, handoff, degraded, busy),
  `nova_ai_turn_duration_seconds`, `nova_ai_tool_calls_total{tool,outcome}` and
  `nova_ai_injection_total`, and `nova_ai_output_retries_total{agent,reason}`: replies sent back to
  the model as JSON, in the wrong language or with a figure no tool returned. A rising degraded or handoff rate means the model
  is down or struggling; a rising busy rate means more slots are needed.
- **Evaluation.** `make ai-eval` sends 14 fixed Arabic and English messages
  (injection, "refund me", "book me", a phone number, the price, a question in
  the other language than the app's) to the configured model and prints a
  pass/fail table; `AI_EVAL_MIN_PASS` (default 0.8) is the gate. A case the
  model did not answer fails, and the table counts them. It needs the model
  server and is skipped only when no case was answered. Run it
  before and after changing a model, a prompt or a guardrail. It checks what
  happened, not the wording.
- **Retention.** A conversation's recent turns are kept in Redis for
  `AI_HISTORY_TTL_SECONDS` (default 24 hours), at most `AI_HISTORY_MAX_TURNS`
  (10), keyed by tenant, caller, business and a hash of `session_id`. Phone
  numbers, emails and card numbers are masked before the model sees a message,
  but names and free text are kept as written. A signed-in person erases all of
  theirs at once, at every business and the marketplace, with
  `DELETE /api/v1/ai/conversations` (the chat window's "Forget chat"); the
  offered times kept beside the turns go too. It answers
  `503 ai_memory_unavailable` rather than "done" when Redis is unreachable.
  Deleted keys leave the dataset at once, but an append-only file keeps the old
  writes until Redis next rewrites it. State the 24 hours and the erase route
  in the privacy notice.

## Commands

```bash
make dev        # docker compose up
make migrate    # alembic upgrade head
make test       # pytest
make lint       # ruff check
make fmt        # ruff format
```
