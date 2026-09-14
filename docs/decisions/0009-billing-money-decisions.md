# 0009 — The Four Money Decisions in the Billing Module

## Status

Accepted — 2026-08-16

## Context

`docs/11` specifies the commercial model completely enough to build, but four questions it does
not answer had to be answered in code before an invoice could be produced. Each one changes what
a salon is charged, so each one is written down here rather than left to be inferred from the
implementation.

The module is `app/modules/billing/` (migration `a7b8c9d0e1f2`); the index the payout job needs
is `b8c9d0e1f2a3`. `BookingSource`, the attribution signal all of this reads, is ADR-0008.

## Decision

### 1. Commission is charged on the amount net of VAT

`docs/11` §1 gives the bill as `subscription + (35% × new-marketplace bookings) + (2.5% ×
prepaid) + VAT`, and §2 prices services in the gross figure a customer actually pays. Taking 35%
of a gross price charges commission on the government's share of the money.

So `commission_base` divides by `1 + VAT_RATE` first: a 172.50 SAR service is 150.00 net, and
Solo's 35% is 52.50 — not 60.38. VAT is then applied once, to NOVA's own charges, at the invoice.

### 2. The 2.5% processing fee is deducted at payout and not invoiced

§1 puts the processing fee in the monthly bill; §8 deducts it from each day's payout. Both would
charge every prepaid booking twice.

§8 wins. It is the more specific rule, it is the figure the salon sees on the settlement it
actually receives, and netting at payout means NOVA never invoices for money it is already
holding. Invoices therefore carry `processing_amount = 0.00`.

`close_period` keeps a `processing_base` parameter for the case §8 does not reach — online
payment through a gateway NOVA does not settle, where there is no payout to net against — and no
caller passes it today.

### 3. "New exactly once" is enforced by the database, not by a read

§3: *"A customer is charged as 'new' exactly once, per business, forever. Any bug that re-charges
an existing customer is a P1."* §11 requires that two concurrent first bookings produce exactly
one billable line.

A `SELECT` followed by an `INSERT` loses that race, so the accrual path does not ask. It attempts
`INSERT ... ON CONFLICT DO NOTHING ... RETURNING id` against
`uq_first_booking_business_customer` and reads whether a row came back. The database decides who
was first; there is no window between the check and the write because there is no check.

Two consequences worth stating:

- **Only a marketplace booking claims the slot.** Claiming on a direct booking would spend the
  customer's one chargeable slot on a booking that was never billable, and NOVA could then never
  charge for the introduction it later actually makes.
- **A refund releases the claim.** `reverse_for_booking` deletes the first-booking row, so a
  refunded introduction can be billed if it happens again. Without this, one refund makes that
  customer free with that business forever.

### 4. A commission line is a value, never a reference

`rate_pct`, `commission_class`, `base_amount` and `source` are all copied onto the line at
accrual. Nothing reads back through to a `Plan` or a `Booking` to recompute them.

This is what makes §11's *"a plan change mid-period does not retroactively re-rate accrued
lines"* true structurally rather than by care. It also keeps the line readable when the booking
is archived, which is what a disputed charge needs.

Lines are append-only, as §10 requires: a reversal is a new row carrying the original's rate,
flagged `is_reversal`, and `signed_amount` makes the pair net to zero on the invoice. Because
`Money` forbids negative amounts, `Invoice.commission_amount` is a bare `Decimal` — a month whose
only activity was reversing last month's bookings owes less than nothing, and the invoice has to
be able to say so.

## Consequences

- Every invoice at the time of writing totalled to the subscription plus VAT and nothing else:
  `MARKETPLACE` had no writer until the discovery surface shipped (ADR-0008), so every commission
  line accrued 0.00. The arithmetic was tested and correct; it simply had no billable input.
  ADR-0010 supplied that input on 2026-08-21, and the billing module needed no change to consume
  it — `classify_commission` already handled the value.
- A business that never subscribed is treated as Solo — free, 35% — rather than raising. Every
  salon on the platform predates billing, and accrual has to work for them.
- `is_billable` now also excludes a line whose booking was refunded. It reads as "money NOVA is
  still owed", and the payout job deducts exactly that, so a reversed line must not be netted out
  of the salon's takings.
- The payout job resolves a booking's business through `BookingService`, because `PaymentRecord`
  carries only `booking_id`. Cheaper would be a join; the architecture test forbids reaching into
  another module's tables, and a daily job is the wrong place to spend that rule.
- Payments in a second currency for one business on one day are dropped and logged, not summed. A
  payout row carries one currency. NOVA is SAR-only, so this branch should never run.
- Invoice collection (§7 step 4) and the overdue notice (§7 step 5) are not wired. See the
  implementation notes in `docs/11` §7 for why the notice needs an owner-shaped recipient first.

## Alternatives considered

**Charge commission on the gross price** — rejected. It inflates every commission by 15% and
bills NOVA's cut of money that belongs to ZATCA.

**Invoice the processing fee and skip it at payout** — rejected. It delays NOVA's own cost
recovery by up to a month and makes the salon reconcile a settlement against an invoice arriving
weeks later, for a fee already implicit in the money it received.

**Recompute `commission_class` on read** — rejected. It is cheaper to store, and a class derived
from live data changes retroactively when a booking is cancelled or a customer's history grows,
which is exactly what an audited charge must not do.

**A `SELECT ... FOR UPDATE` on the customer before claiming** — rejected. It serialises every
first booking behind a row lock for a guarantee the unique index already gives for free.
