# Domain: Tenants and Branches

The first vertical slice. A **Tenant** is a business (e.g. a salon brand); a **Branch** is one
of its physical locations. Every future tenant-owned entity (bookings, queues, services, staff)
will reference a branch or tenant the same way.

## Model

```
Tenant
├── id (UUID)
├── name_en, name_ar   — both required, see ADR-0004
├── slug               — unique, derived from name_en
├── phone               — E.164, validated against allowed GCC country codes
├── default_currency    — SAR by default, configurable per tenant
└── branches: [Branch]

Branch
├── id (UUID)
├── tenant_id (FK → Tenant, cascade delete)
├── name_en, name_ar
├── slug               — unique within the tenant, not globally
├── phone
└── timezone            — IANA zone, default Asia/Riyadh
```

Code: `backend/app/modules/tenants/models.py`.

## Business rules

Implemented as pure functions in `backend/app/modules/tenants/domain.py` (no ORM/FastAPI
imports — see [[backend-architecture|../architecture/backend-architecture]]):

- `require_bilingual_text` — name_en and name_ar are both mandatory. Arabic is core identity
  data for a GCC product, not optional localization.
- `validate_gcc_phone` — E.164 format, country code must be in the configured allow-list
  (`Settings.allowed_phone_country_codes`). **To verify**: the full set of GCC codes NOVA
  should accept.
- `validate_timezone` — must be a real IANA zone (validated via `zoneinfo`).
- `generate_slug` — derives a URL-safe slug from `name_en`; collisions raise
  `DuplicateSlugError`.

## Isolation

Branch queries/writes always go through `BranchRepository`, which extends
`TenantScopedRepository` — every query is filtered by `tenant_id`. See
[[0003-tenant-isolation-strategy|../decisions/0003-tenant-isolation-strategy]].

## Not yet built

Update/delete endpoints, staff/service-provider association, branch operating hours. Add them
as new commands/queries in the same module, following [[module-template]].
