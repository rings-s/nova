---
title: Pricing and Subscriptions
created: 2026-08-14
project: NOVA
type: billing
tags: [pricing, subscriptions, commission, billing, marketplace]
related_code:
  - app/modules/billing/domain.py
  - app/modules/billing/models.py
  - app/modules/billing/schemas.py
  - app/modules/billing/service.py
---

# Pricing and Subscriptions

> [!important] Goal
> Define what a business pays NOVA, when it is charged, and what it is never charged for.

NOVA follows the Treatwell commercial model: the software is cheap, the marketplace is
performance-priced. A business pays for new customers NOVA brings it, and pays nothing on the
customers it already had.

## Goals

- Charge commission only on customers NOVA introduced.
- Charge 0% on every repeat booking, forever.
- Charge 0% on every direct booking — own link, WhatsApp, walk-in, phone.
- Keep the subscription low enough that a solo provider can start at zero.
- Make every invoice line traceable to one booking.

---

## 1. The Model in One Line

```text
Monthly bill = subscription + (35% × new-marketplace-client bookings) + (2.5% × prepaid online) + VAT
```

Everything else is free.

---

## 2. Plans

|                               | **Solo**               | **Studio**                       | **Chain**                        |
| ----------------------------- | ---------------------- | -------------------------------- | -------------------------------- |
| For                           | One provider, no staff | Salon or spa, unlimited staff    | Multi-location groups            |
| Subscription                  | **0 SAR / month**      | **199 SAR / month**              | **449 SAR / month per location** |
| Annual                        | —                      | 1,990 SAR / year (2 months free) | Negotiated                       |
| New marketplace client        | 35%                    | 30%                              | 25%                              |
| Repeat booking                | **0%**                 | **0%**                           | **0%**                           |
| Direct booking                | **0%**                 | **0%**                           | **0%**                           |
| Online prepayment             | 2.5%                   | 2.5%                             | 2.5%                             |
| Staff seats                   | 1                      | Unlimited                        | Unlimited                        |
| Locations                     | 1                      | 1                                | Unlimited                        |
| Marketplace profile           | ✅                     | ✅                               | ✅                               |
| Calendar and availability     | ✅                     | ✅                               | ✅                               |
| Walk-in queue and QR tickets  | ✅                     | ✅                               | ✅                               |
| WhatsApp reminders            | 100 / month            | Unlimited                        | Unlimited                        |
| AI booking and support agents | ✅                     | ✅                               | ✅                               |
| AI insights agent             | —                      | ✅                               | ✅                               |
| AI retention campaigns        | —                      | ✅                               | ✅                               |
| POS and product sales         | —                      | ✅                               | ✅                               |
| Cross-location reporting      | —                      | —                                | ✅                               |
| API access                    | —                      | —                                | ✅                               |
| Payouts                       | Daily                  | Daily                            | Daily                            |
| Contract                      | None, cancel any time  | None, cancel any time            | 12 months                        |

All figures exclude VAT. KSA VAT is 15% and is applied to subscription, commission, and
processing fees on the tenant invoice.

> [!note] Which agents each feature unlocks
>
> - **Every plan:** `ai_booking_agent` is the receptionist and `ai_support_agent` the
>   customer-service agent. The accountant is included too.
> - **Studio and Chain:** `ai_insights_agent` unlocks the analyst and the business manager.
> - **Analytics dashboards:** every plan. Only the branch-by-branch comparison needs
>   `cross_location_reporting`, on Chain.
>
> See [[13-Business-Agents-and-Analytics]] (ADR-0011).

---

## 3. Commission Rules

The rules that decide whether a booking is billable:

1. **First booking through the NOVA marketplace** by a customer the business has no prior booking with → commission applies.
2. **Every later booking by that customer** → 0%, regardless of channel, regardless of how much time passes.
3. **Booking through the business's own NOVA link, WhatsApp, QR, or walk-in queue** → 0%, even on the first visit.
4. **Attribution window:** a marketplace click attributes for 30 days. A booking outside the window with no prior marketplace touch is direct.
5. **Cancelled or no-show booking** → no commission. Commission accrues on `COMPLETED`.
6. **Refunded booking** → commission reversed on the next invoice.
7. **Commission base** is the service price net of VAT and net of discounts, excluding tips and retail products.

> [!warning] The rule that must never break
> A customer is charged as "new" exactly once, per business, forever. Any bug that re-charges an
> existing customer is a P1.

---

## 4. Booking Source Classification

```python
from enum import StrEnum


class BookingSource(StrEnum):
    MARKETPLACE = "marketplace"       # NOVA discovery, search, or listing
    DIRECT_LINK = "direct_link"       # business's own booking page
    WHATSAPP = "whatsapp"             # business WhatsApp number
    WALK_IN = "walk_in"               # queue ticket at the counter
    RECEPTION = "reception"           # staff booked on behalf of the customer
    AI_AGENT = "ai_agent"             # inherits the channel it was reached on


class CommissionClass(StrEnum):
    NEW_MARKETPLACE = "new_marketplace"   # billable
    REPEAT = "repeat"                     # 0%
    DIRECT = "direct"                     # 0%
    EXEMPT = "exempt"                     # cancelled, no-show, refunded
```

`BookingSource` is captured at creation and is immutable. `CommissionClass` is derived once, at
booking completion, and stored on the commission line — never recomputed from live data.

> [!note] Implementation status
> Both enums ship as written above. `BookingSource` lives in `app/modules/booking/domain.py`
> (migration `f6a7b8c9d0e1`, ADR-0008); `CommissionClass` lives in
> `app/modules/billing/domain.py` (migration `a7b8c9d0e1f2`, ADR-0009), is derived once by
> `classify_commission` at booking completion, and is stored on the line rather than recomputed.
>
> **`MARKETPLACE` now has a writer** (ADR-0010). The public discovery surface ships as
> `app/modules/discovery/`, and with it the 30-day attribution record from §3 rule 4:
> `POST /discovery/businesses/{slug}/referrals` records a click as a `marketplace_referrals` row
> and returns a token, which `BookingService.create` verifies against the business being booked
> and the window before it writes `MARKETPLACE`.
>
> `resolve_booking_source` still refuses to let a client _declare_ the value — the marketplace
> presents a credential NOVA issued rather than asserting a source, so the claim stays
> server-side and falsifiable, which is what ADR-0008 required. Every unverifiable case still
> falls back to a free channel, per the P1 rule above.

---

## 5. Billing Domain

Placement follows [[02-Backend-FastAPI-DDD-Structure]]: `app/modules/billing/`.

**Aggregates**

| Aggregate        | Protects                                                            |
| ---------------- | ------------------------------------------------------------------- |
| `Subscription`   | Plan, seats, locations, billing cycle, trial and cancellation state |
| `Invoice`        | A closed month of charges for one tenant; immutable once issued     |
| `CommissionLine` | One booking's commission decision and amount                        |

**Value objects:** `Plan`, `CommissionRate`, `Money`, `BillingPeriod`.

**Domain events:** `SubscriptionActivated`, `PlanChanged`, `SubscriptionCancelled`,
`CommissionAccrued`, `CommissionReversed`, `InvoiceIssued`, `InvoicePaid`, `InvoiceOverdue`.

**Domain rules**

- A subscription belongs to exactly one tenant.
- Commission rate is read from the plan in force at booking completion, not at invoice time.
- An issued invoice is never edited; corrections are credit notes.
- Downgrading below current usage (seats, locations) is refused by the domain.
- A cancelled subscription keeps read access until the end of the paid period.

```python
class PlanTier(StrEnum):
    SOLO = "solo"
    STUDIO = "studio"
    CHAIN = "chain"


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"
```

---

## 6. Billing Schemas

Naming follows [[07-Pydantic-Schemas-and-API-Contracts]].

```python
class PlanOut(ApiSchema):
    tier: PlanTier
    monthly_price: Decimal
    annual_price: Decimal | None
    currency: str = "SAR"
    new_client_commission_pct: Decimal
    repeat_commission_pct: Decimal = Decimal("0")
    processing_fee_pct: Decimal = Decimal("2.5")
    included_features: list[str]


class SubscriptionOut(ApiSchema):
    id: UUID
    business_id: UUID
    tier: PlanTier
    status: SubscriptionStatus
    current_period_start: date
    current_period_end: date
    seats: int
    locations: int
    cancel_at_period_end: bool


class ChangePlanRequest(ApiSchema):
    tier: PlanTier
    annual: bool = False


class CommissionLineOut(ApiSchema):
    id: UUID
    booking_id: UUID
    source: BookingSource
    commission_class: CommissionClass
    base_amount: Decimal
    rate_pct: Decimal
    amount: Decimal
    reversed: bool = False


class InvoiceOut(ApiSchema):
    id: UUID
    business_id: UUID
    period_start: date
    period_end: date
    status: InvoiceStatus
    subscription_amount: Decimal
    commission_amount: Decimal
    processing_amount: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    currency: str = "SAR"
    issued_at: datetime | None
    due_at: datetime | None
    lines_url: str
```

---

## 7. Billing Cycle

1. Booking reaches `COMPLETED` → `CommissionAccrued` writes a `CommissionLine` in `DRAFT`.
2. Refund → `CommissionReversed` writes an offsetting line.
3. On the 1st of each month an ARQ worker closes the previous period and issues one `Invoice` per tenant.
4. Payment is collected through Moyasar against the tenant's stored payment method.
5. Failure → `PAST_DUE`, retry on days 3, 7, 14, with a WhatsApp and email notice each time.
6. Still unpaid at day 21 → marketplace listing hidden. The calendar, queue, and existing bookings keep working.

> [!danger] Never break the salon's day
> Non-payment removes NOVA's marketing, never the business's operations. Existing bookings,
> tickets, and check-ins always run.

> [!note] Implementation status
> Steps 1, 2, 3, 5 and 6 ship. Steps 1 and 2 are outbox handlers on `BookingCompleted` and
> `PaymentRefunded` (`app/worker/handlers.py`); steps 3, 5 and 6 are ARQ crons —
> `close_monthly_invoices` at 02:00 on the 1st, `advance_dunning` daily at 09:00, which owns both
> the day 3/7/14 retries and the day 21 listing hide. Every one of them is idempotent, so a retry
> or a manual re-run costs nothing.
>
> Two gaps, both narrow:
>
> **Step 4 has no collection call.** `mark_invoice_paid` records a collection and restores the
> listing, but nothing charges the stored payment method — the payment module has no
> merchant-initiated Moyasar flow, only the customer-present one. Until it does, an invoice is
> marked paid by whatever settles it out of band.
>
> **Step 5 publishes but does not deliver.** `advance_dunning` emits `InvoiceOverdue` on every
> retry; no handler turns it into the WhatsApp and email notice. `NotificationRecord.customer_id`
> is a foreign key to `customers`, and an overdue notice goes to the business owner, who is not
> one — so this needs the notification module to grow an owner-shaped recipient, not a handler
> bolted onto a customer-shaped table.

---

## 8. Payouts

- Customer prepayments are collected by NOVA and paid out **daily**.
- Payout = collected amount − 2.5% processing − commission due.
- Commission is netted at payout where a prepayment exists; otherwise it is invoiced monthly.
- Every payout references its bookings and is exportable as CSV for the business's accountant.

> [!note] Implementation status
> `settle_daily_payouts` (ARQ, 04:00 daily) settles the day that just ended, one row per
> `(business_id, payout_date)`. It reads the day's captures net of same-day refunds, resolves each
> booking's business through `BookingService`, and nets only commission that is still owed — a
> line whose booking was refunded is no longer billable, so its commission is not deducted.
>
> **The 2.5% is charged here and only here.** §1 puts the processing fee in the monthly bill and
> this section deducts it from each payout; doing both would bill every prepaid booking twice.
> This section wins, being the more specific rule and the one the salon sees on the settlement it
> actually receives, so invoices carry 0.00 processing. `close_period` keeps a `processing_base`
> parameter for the case this section does not cover — online payment through a gateway NOVA does
> not settle, where there is no payout to net against — and nothing passes it today.
>
> The CSV export is not built; `GET /billing/payouts` returns the same data as JSON, booking
> references included.

---

## 9. Free Forever

These are never billed, on any plan:

- Repeat bookings from any customer the business already has.
- Bookings from the business's own link, WhatsApp, QR ticket, or walk-in queue.
- Cancelled bookings, no-shows, and refunded bookings.
- Retail product sales and tips.
- Customer accounts, media storage, and ticket QR generation.

---

## 10. Persistence Notes

Follows [[08-Database-Models-and-Persistence]].

- `subscriptions`, `invoices`, `commission_lines` tables, all tenant-scoped.
- Unique index on `(business_id, customer_id)` in a `customer_business_first_booking` table — this is what makes "new exactly once" enforceable at the database level, not just in code.
- Unique index on `(business_id, period_start)` for invoices.
- Money is `NUMERIC(12, 2)`; rates are `NUMERIC(5, 2)`. Never floats.
- Commission lines are append-only; reversals are new rows.
- Invoice issuance is idempotent per `(business_id, period)`.

---

## 11. Testing Requirements

- A customer's second marketplace booking is charged 0%.
- A first-ever direct booking is charged 0%.
- A no-show accrues nothing; a refund reverses in full.
- A plan change mid-period does not retroactively re-rate accrued lines.
- Two concurrent first bookings for the same customer produce exactly one billable line.
- Invoice totals reconcile to the sum of their lines plus VAT, to the fils.
