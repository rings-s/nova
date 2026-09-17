# 0010 — The Public Discovery Surface, and the Writer for `MARKETPLACE`

## Status

Accepted — 2026-08-21

## Context

`docs/09` #3 requires that "a customer can discover a business and book a service". Only the
second half existed. Every route in NOVA was nested under `/tenants/{tenant_id}`, and
`tests/test_customer_journey.py` began each journey already holding a tenant id — which is
precisely what a customer discovering a salon does not have. There was no way to answer "which
salons near me do balayage", and therefore no way to reach a booking without being told where to
book first.

The gap was not only a missing feature. Three documents named it as the thing blocking the
commercial model:

- ADR-0008: "`MARKETPLACE` therefore has no writer yet… It has to be derived server-side from a
  marketplace attribution record — the 30-day click window in `docs/11` §3 rule 4 — and that
  needs the public discovery surface, which does not exist."
- ADR-0009: "`MARKETPLACE` has no writer until the discovery surface ships (ADR-0008), so every
  commission line accrues 0.00."
- `docs/11` §4: "**`MARKETPLACE` has no writer yet.**… the commission machinery below — which is
  complete and tested — accrues 0.00 on all of them until discovery ships."

So the billing module was finished and earning nothing, waiting on a signal no code produced.

Two structural problems stood between the codebase and a marketplace:

1. **Tenant scoping is total.** `TenantScopedRepository` fixes a repository to one tenant at
   construction, and ADR-0003 makes that the load-bearing isolation control. A cross-tenant read
   is not merely absent from it; it is unrepresentable, which is the point.
2. **RLS fails closed.** Migration `d4e5f6a7b8c9` matches rows against
   `app.current_tenant_id`. A request that never sets it sees nothing — correct for every
   existing route, and fatal for one that has no tenant to set.

## Decision

### Discovery is a bounded context of its own

`app/modules/discovery/` is public and cross-tenant, and those are the same fact: a customer
searching for a salon has neither an account nor a tenant. Every other context answers "what may
this caller see inside one tenant"; discovery answers "which tenant should they be looking at".

It is not more endpoints on `catalog` because the two have opposite security models, and folding
an unauthenticated cross-tenant read into the module whose defining guarantee is tenant scoping
would mean that guarantee no longer holds where it is written down.

### Catalog keeps its own queries; discovery composes them

`PublicCatalogRepository` and `PublicCatalogService` live in `catalog`, because those are
catalog's tables and `tests/test_architecture.py` enforces that no module reaches into another's
repository. Discovery receives the assembled service from
`catalog.dependencies.build_public_catalog_service` and never sees the repository — the same
route `booking` already takes to `CatalogService`.

The public repository extends `BaseRepository` rather than `TenantScopedRepository`, and pays
for the missing tenant filter with a different restriction: it is read-only — there is no
`add` — and every query is confined to published rows.

### A second RLS window, `app.discovery_mode`, that is SELECT-only

Migration `d0e1f2a3b4c5` adds a `public_discovery` policy to `businesses`, `locations`,
`services`, `providers` and `provider_services`. Postgres ORs permissive policies, so
`tenant_isolation` is untouched and an ordinary tenant-scoped request behaves exactly as before.

It is deliberately not `app.bypass_rls`, which `app/db/session.py` documents as never belonging
on a request path. The difference is two restrictions the bypass does not have:

- **`FOR SELECT` only.** Nothing on the public path can write across tenants even by accident.
  Verified: under the window an `INSERT` is refused outright and `UPDATE`/`DELETE` match zero
  rows.
- **Published rows only.** The policy repeats the visibility predicate, so an unlisted or
  retired salon is invisible to the database, not merely to the query.

The predicate is therefore enforced twice — once in the query, once in the policy — and neither
is trusted to be the only one.

### `is_listed`, separate from `is_active`

`docs/11` §8 ends the dunning ladder with "marketplace listing hidden. The calendar, queue, and
existing bookings keep working." That is not expressible with an on/off flag: hiding a listing
with `is_active` would cancel the salon's operations over an overdue invoice. `is_listed`
defaults to true, because `docs/11` §2 gives every plan tier a marketplace profile — it is an
opt-out, not an opt-in.

### A referral is a row, not a signed token

`POST /discovery/businesses/{slug}/referrals` records a click and returns an opaque token,
storing only its SHA-256 hash. `BookingService.create` resolves `MARKETPLACE` from it.

A signed token would also have been unforgeable, so unfalsifiability is not what decides this. A
commission line takes money from a salon, and the row's second job is settling the argument when
one disputes it: a timestamped click against the storefront it landed on is a better answer than
"our server signed something". The row also records which booking claimed it, so the audit trail
runs end to end.

Only the hash is stored, following `queue`'s ticket tokens, and for a sharper reason: the rows
that decide a salon's invoice should not double as a supply of the credentials that produce
those invoices.

### Attribution is resolved in the service, not the router

`resolve_booking_source` stays exactly as ADR-0008 left it — a client still may not declare
`MARKETPLACE`. The marketplace does not declare it either; it presents a credential NOVA issued.

Verification needs the business id, which is not known until `create()` reads the location, so
it happens there rather than in the router. That keeps `source` written exactly once, at
construction, which is what ADR-0008 means by immutable.

Only the unattributed `DIRECT_LINK` default is ever upgraded. A booking declared `whatsapp`,
`walk_in` or `reception` came through a channel the salon owns, and a stray token must not
re-label it as one NOVA is owed 35% on. Staff booking on behalf is `RECEPTION` before
attribution is consulted at all.

### Every ambiguous case still resolves in the salon's favour

A token that is absent, unknown, expired, or issued for a different business is simply not a
marketplace booking. `docs/11` §3 names the opposite mistake a P1 — "a customer is charged as
'new' exactly once, per business, forever" — so under-charging NOVA is the cheap failure and
the direction every branch leans.

The `business_id` check matters most: without it, a customer could click a listing that costs
nothing and spend the token at a different salon. It is the only attribution fraud a client can
attempt by hand.

### Authentication: the one carve-out, and what pays for it

ADR-0006 established that NOVA fails closed and every endpoint requires a bearer token. A
marketplace a customer must log in to browse is not a marketplace, so discovery is the exception.
It is bounded by: read-only but for the referral row, which describes NOVA's own behaviour and
touches nothing a business owns; published rows only, enforced twice; per-IP rate limits, since
there is no principal to limit by, tightest on availability; and a curated projection — branch
phone numbers appear on a storefront, which is the salon's shop window, and never in search
results, which is the scrape ADR-0007 found on the old unauthenticated `GET /tenants`.

## Consequences

- **`MARKETPLACE` can now be written.** The first path in NOVA that can produce a chargeable
  booking. Billing needed no changes: `classify_commission` already handled the value.
- Public availability is an occupancy oracle for anyone willing to poll it — free slots are the
  inverse of a provider's calendar. The rate limit bounds this rather than closing it, which is
  the same trade `GET /tenants/{id}/bookings/availability` already makes, taken with no principal
  to attribute the polling to.
- That route also answers for _every_ provider qualified for the service, where the authenticated
  one answers for a named provider — so the same date range costs a multiple of it, chosen by an
  anonymous caller. Two bounds cap the work: `discovery_max_availability_days` (14, against
  `availability_max_horizon_days`'s 90) caps the date dimension, and `discovery_max_public_slots`
  caps the other one, a salon with a great many stylists. The slot cap truncates chronologically
  after sorting, so it reads as "the next N available times" rather than dropping one stylist's
  day.
- Geo search is a two-step: a bounding box the database can index, then an exact haversine in
  `discovery.domain` that trims the square to the circle. When a geo filter is present, paging is
  applied after that trim, so the query over-fetches a bounded window.
- Search is `ILIKE` over names, descriptions, service names and categories. Adequate at current
  scale, and the point at which it stops being adequate is a `pg_trgm` or `tsvector` index rather
  than a redesign. `%` and `_` are escaped, so a customer searching "50% off" does not match the
  platform.
- `businesses.is_listed` does not survive a downgrade: the old schema has nowhere to record it, so
  a salon hidden for non-payment reappears in search if `d0e1f2a3b4c5` is reversed.
- Referrals are not single-use. A customer booking two services off one visit came through the
  marketplace both times, and `docs/11` §3 rule 2 already makes only the first billable.
- ~~**Outstanding, and it now matters more than it did.**~~ RLS is bypassed entirely by a Postgres
  superuser, even with `FORCE`. The default `infra/docker-compose.yml` connects as `nova`, which
  the `postgres` image creates as a superuser, so in that deployment every policy — the
  pre-existing `tenant_isolation` as much as `public_discovery` — is decorative, and the
  application-layer predicates are the only control actually running. Discovery leans on RLS as
  its second control, so the app should connect as a `NOSUPERUSER` role. The policies were
  verified against one, and behave as specified; the deployment does not use one yet.
  **Resolved 2026-09-14** by migration `e1f2a3b4c5d6`: the API, the worker and the test suite
  now connect as `nova_app` (NOSUPERUSER NOBYPASSRLS), and the discovery tests run as it.

## Alternatives considered

**Put the discovery endpoints on `catalog`** — rejected. It is where the queries live, and they
stayed there. The HTTP surface did not, because `catalog`'s router is nested under a tenant and
guards every write with `require_staff`; an unauthenticated cross-tenant read in the same file
makes the module's security model unreadable.

**Maintain a denormalized `marketplace_listings` read model** — rejected as premature. It buys
query performance at the cost of a second copy of the catalog that can silently drift, and a
de-listed salon lingering in a stale projection is a correctness bug, not a slow page. The RLS
window reads the real tables.

**A signed HMAC referral token with no row** — rejected. Equally unforgeable and cheaper, but it
leaves nothing to show a salon disputing a commission line, and nothing to point at the booking
that claimed it. Storage was never the constraint.

**Bind the referral to the customer who clicked** — rejected as a second source of truth.
Whether a customer is new to a business is settled by a unique index at completion time
(`customer_business_first_bookings`, ADR-0009). Answering it here as well would give
"charged as new exactly once, forever" a second place to be wrong, and `docs/11` §3 calls that a
P1.

**Require authentication to browse** — rejected. It inverts the funnel the commercial model
depends on: a customer would have to sign up before they could see whether NOVA has anything
they want.
