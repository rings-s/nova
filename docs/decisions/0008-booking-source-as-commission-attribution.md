# 0008 — `BookingSource` Is Commission Attribution, Not a Channel Label

## Status

Accepted — 2026-08-16

> The `MARKETPLACE` writer this ADR deferred — "a marketplace attribution record… which needs
> the public discovery surface, which does not exist" — shipped in
> [[0010-public-discovery-and-marketplace-attribution]] on 2026-08-21. The rule below that a
> client may not _declare_ `MARKETPLACE` is unchanged, and still enforced by
> `resolve_booking_source`.

## Context

Two documents defined `BookingSource` differently, and the code implemented the wrong one.

`docs/06` §4 (2026-08-11) defined it as the interface a booking arrived through:

```text
pwa · staff · whatsapp · ai_agent
```

`docs/11` §4 (2026-08-14) defined it as the channel that _introduced the customer_:

```text
marketplace · direct_link · whatsapp · walk_in · reception · ai_agent
```

`app/modules/booking/domain.py` implemented `docs/06`'s set. That is the older definition, and
it cannot express the only question the commercial model asks. NOVA's entire pricing model
(`docs/11` §1) is:

```text
Monthly bill = subscription + (35% × new-marketplace-client bookings) + (2.5% × prepaid) + VAT
```

Everything turns on whether NOVA introduced the customer or the salon already had them. `pwa`
cannot answer it: the same PWA serves the marketplace listing _and_ the salon's own booking
page, which are the two sides of the question. A `pwa` row is not an imprecise answer, it is no
answer, and no amount of later analysis recovers it — nothing anywhere in the row records which
surface the customer came through.

This is why the fix could not wait for the billing module. The billing module is a large build
(`Subscription`, `Invoice`, `CommissionLine`, monthly close, payouts, reversals) and can arrive
whenever. The _signal_ it reads is different: every booking taken before this change is
permanently unbillable and unauditable, and the cost of the delay compounds with volume.

## Decision

### `BookingSource` becomes the `docs/11` §4 vocabulary

`docs/11` wins the conflict on two grounds: it is the newer document, and it is the one with a
consequence attached. `docs/06` and `docs/08` §10 have been amended to match rather than left to
contradict it.

`RECEPTION` replaces `STAFF` and `DIRECT_LINK` replaces `PWA`. `WALK_IN` and `MARKETPLACE` are
new. `WHATSAPP` and `AI_AGENT` carry over unchanged.

### Only `MARKETPLACE` is ever chargeable

`NEVER_BILLABLE_SOURCES` in `booking/domain.py` names the other five. `docs/11` §3 rules 2–3 and
§9 already say this in prose; stating it as a frozenset next to the enum means the invariant can
be asserted by a test today instead of living in the head of whoever writes the billing module
later. `tests/modules/booking/test_attribution.py` asserts it.

`AI_AGENT` is in that set. `docs/11` §4 says an agent "inherits the channel it was reached on",
so a booking stored as bare `ai_agent` is one that never recorded its real channel — it cannot
be shown to be a marketplace booking, so it is not billed as one.

### The client may not declare `MARKETPLACE`

`resolve_booking_source` sits beside `resolve_booking_customer` and follows the same rule ADR-0006
established: take from the request only what the request is entitled to assert.

- Staff booking on behalf of someone is `RECEPTION`, whatever the body says.
- A customer may declare `DIRECT_LINK`, `WHATSAPP`, `WALK_IN`, or `AI_AGENT`.
- Nobody may declare `MARKETPLACE`, because it is the only source that costs the salon money. A
  client that could assert it could invent revenue; a client that could withhold it could dodge
  a charge it owed.
- Anything unstated is `DIRECT_LINK`.

`MARKETPLACE` therefore has no writer yet, which is correct and temporary. It has to be derived
server-side from a marketplace attribution record — the 30-day click window in `docs/11` §3 rule
4 — and that needs the public discovery surface, which does not exist. Until it does, the field
records honestly that NOVA cannot demonstrate it introduced the customer.

### Uncertainty resolves in the salon's favour, always

Every default here leans the same way. `docs/11` §3 states the rule that must never break:

> A customer is charged as "new" exactly once, per business, forever. Any bug that re-charges an
> existing customer is a P1.

Defaulting to `DIRECT_LINK` means NOVA under-charges when it cannot tell. The opposite default
would charge a salon for a customer it already had. The first is lost revenue; the second is the
P1.

Migration `f6a7b8c9d0e1` applies the same reasoning to history: `pwa` becomes `direct_link`
rather than being split by guesswork.

## Consequences

- **Breaking**: `POST /bookings` no longer accepts `source: "pwa"` or `"staff"`; `BookingOut.source`
  returns the new vocabulary. `source` is now optional on the request and is overridden entirely
  for staff booking on behalf.
- Historical bookings are all `direct_link`, `reception`, `whatsapp`, or `ai_agent`. **No
  historical booking will ever be billable**, by construction. That is the honest outcome — the
  data to bill them was never captured — and it is a one-time cost that stops accruing now.
- Downgrading migration `f6a7b8c9d0e1` does not round-trip: `marketplace` and `walk_in` collapse
  into `pwa` because the old vocabulary cannot express them.
- `BookingSource` is immutable after creation. Nothing on the `Booking` entity reassigns it, and
  nothing should — a booking that could change channel after completion could change what the
  salon was charged for it. This is currently a convention enforced by there being no setter,
  not by the database.
- The column is deliberately unindexed. Its only reader will be a monthly billing rollup that
  does not exist; `docs/08` §18 warns against indexing ahead of a real query plan.
- Still outstanding for billing, and unblocked by this: the `customer_business_first_booking`
  table (`docs/11` §10) that makes "new exactly once" enforceable at the database level, and
  `CommissionClass`, which `docs/11` §4 derives at booking _completion_ and stores on the
  commission line — so it belongs to the billing module, not here.

## Alternatives considered

**Keep `BookingSource` as the channel and add a separate `attribution` column** — rejected.
`docs/11` §4 names `BookingSource` explicitly and lists its members; introducing a second,
undocumented field to hold the meaning the documented field was supposed to carry leaves two
overlapping columns and a reader who has to know which one billing trusts.

**Wait and build it with the billing module** — rejected, and this is the whole point of the ADR.
The enum is an afternoon; the billing module is not. Every day between them is bookings recorded
with no recoverable attribution.

**Let the client declare `MARKETPLACE` and reconcile later** — rejected: there is nothing to
reconcile against. Without a server-side click record the claim is unfalsifiable, and an
unfalsifiable claim that generates an invoice line is a dispute the salon wins.

**Add a CHECK constraint pinning the column to the six values** — deferred. `status` on the same
table has none either (SQLAlchemy renders `native_enum=False` as a bare `VARCHAR`), and adding one
here alone would break `alembic check` unless the model declares it too. Worth doing for both
columns together, as its own change.
