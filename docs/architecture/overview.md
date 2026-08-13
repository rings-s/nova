# Architecture Overview

```
Customer / Business / Service Provider
                │
        SvelteKit PWA (frontend/)
                │  HTTP (JSON)
        FastAPI backend (backend/)
        ┌───────┴────────┐
   PostgreSQL          Redis
 (system of record)  (cache/queues/locks)
                │
          ARQ worker (backend/app/worker/)
                │
   ┌────────────┼─────────────┬─────────────┐
WhatsApp     Moyasar       Nextcloud    Cloudflare Tunnel
(BSP, TBD)  (payments)   (media, TBD)   (public ingress)
```

Everything right of "FastAPI backend" in the integrations row is a **replaceable adapter** —
see `backend/app/integrations/`. None are implemented yet; each has a `Protocol` and a
placeholder that raises until real credentials/implementation exist. Details are marked
"to verify" — see `docs/integrations/`.

## Module boundaries

Backend code is organized as vertical slices under `backend/app/modules/`, not by technical
layer — see [[backend-architecture]]. The only module that exists today is `tenants` (business +
branch registration), which is the reference pattern for every future module (booking, queue,
payments, whatsapp, ai-support, ...).

## Multi-tenancy

Every business (tenant) can have multiple branches; isolation between tenants is enforced at
the repository layer. See [[multi-tenancy]] and
[[0003-tenant-isolation-strategy|../decisions/0003-tenant-isolation-strategy]].

## AI

Not built yet. When it is: PydanticAI agents call controlled domain tools (the same
commands/queries routers use) — never the database directly — and are never the source of
truth for bookings, availability, payments, tickets, or queue order. See
[[future-ai-integration|../ai/future-ai-integration]].
