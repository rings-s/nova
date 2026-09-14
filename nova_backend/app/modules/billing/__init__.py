"""Bounded context: BILLING — what a business pays NOVA, and why.

Aggregates      Subscription, Invoice, CommissionLine
Tables          subscriptions, commission_lines, invoices, payouts,
                customer_business_first_bookings
Depends on      identity, catalog, booking, payment
Status          implemented

Domain style: RICH entities. All three own a lifecycle that money depends on —
an invoice edited after issue, or a commission line re-rated after accrual, is
not bad input, it is a salon billed for something it can no longer verify.

The commercial model in one line (docs/11 section 1):

    Monthly bill = subscription + (35% x new-marketplace bookings)
                 + (2.5% x prepaid online) + VAT

The rules this context exists to keep:

  1. **A customer is charged as "new" exactly once, per business, forever.**
     docs/11 section 3 calls any bug that re-charges an existing customer a P1.
     It is enforced by a UNIQUE index on (business_id, customer_id) in
     `customer_business_first_bookings`, not by a SELECT-then-INSERT — two
     concurrent first bookings must produce exactly one billable line, and only
     the database can promise that.
  2. **Commission accrues on COMPLETED, never before.** A cancelled or no-show
     booking earns nothing (section 3 rule 5); a refund writes an offsetting
     line rather than editing the original (rule 6).
  3. **The rate is frozen at accrual.** Section 5: "commission rate is read from
     the plan in force at booking completion, not at invoice time." A salon that
     upgrades mid-month does not get last week re-priced.
  4. **An issued invoice is never edited.** Corrections are new documents.
     `Invoice.assert_mutable` guards every setter.
  5. **Non-payment never breaks the salon's day.** Section 7 step 6 hides the
     marketplace listing at day 21 and nothing else — calendar, queue, tickets
     and existing bookings keep working.

Money is `Decimal` end to end, `NUMERIC(12, 2)` in the database, and rates are
`NUMERIC(5, 2)`. There is no float anywhere in this module by construction.

Public surface — what other modules may import:
    from app.modules.billing.service import BillingService
    from app.modules.billing.domain import PlanTier, CommissionClass, PLANS
    from app.modules.billing.domain import CommissionLine, Invoice, InvoiceStatus, Payout
    from app.modules.billing.events import CommissionAccrued, InvoiceIssued

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

This context is mostly a CONSUMER: it reacts to `BookingCompleted` and
`PaymentRefunded` from the outbox (see `app/worker/handlers.py`). Booking and
payment know nothing about it, and must not.
"""
