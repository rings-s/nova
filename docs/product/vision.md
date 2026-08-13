# Vision

NOVA is a GCC-focused AI booking and customer-operations platform connecting **Customer ↔
Business ↔ Service Provider**.

Initial vertical: **beauty** — salons, spas, massage centers, wellness businesses. Future
verticals (healthcare clinics, auto services, home services, professional services) are
possible but out of scope for current implementation; domain code should avoid hard-coding
"beauty" where a generic concept (e.g. "business", "branch", "service") already works, but no
multi-vertical abstraction should be built ahead of actually needing it.

## Core capabilities (target state, not all built yet)

- Service discovery
- Booking
- Payments (Moyasar)
- Virtual QR tickets
- Walk-in queues
- WhatsApp communication (official Business Platform via an approved BSP)
- AI support, sales, and retention (PydanticAI agents calling controlled domain tools — see
  [[future-ai-integration|../ai/future-ai-integration]])
- Business operations (multi-branch, multi-tenant)
- Media management (Nextcloud-backed)

## What's actually built so far

See [[overview|../architecture/overview]] and [[tenants-and-branches|../domain/tenants-and-branches]]
— the `tenants` module (business + branch registration) is the first working vertical slice,
built as the reference pattern for every module that follows.
