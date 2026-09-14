"""Bounded context: PAYMENT — deposits, captures, refunds.

Aggregates      Payment, Refund
Tables          payments, payment_refunds, webhook_events
Depends on      identity, booking
Status          implemented

Domain style: RICH entity. Payment state is a machine with money attached, and
an illegal transition is not a validation slip — it is a customer charged or
refunded twice.

The four rules this context exists to keep (docs/03 section 5, docs/06 section
7, docs/07 section 8):

  1. Payment state is SEPARATE from booking state. A booking may be CONFIRMED
     while payment is still PENDING, if the tenant's deposit policy allows it.
     They are two state machines that observe each other, never one.
  2. Webhook payloads are untrusted until the signature is verified. The
     webhook endpoint is the only unauthenticated write path in the system, so
     it verifies before it parses anything into a service, and records the raw
     payload before it acts.
  3. Capture is idempotent. Moyasar retries, and a double capture charges a
     real customer twice. `PaymentService.capture` returns unchanged for an
     already-captured payment rather than raising.
  4. Refunds are separate rows, never a mutation of the original. Overwriting
     the captured amount destroys the evidence a chargeback dispute needs.

Public surface — what other modules may import:
    from app.modules.payment.service import PaymentService
    from app.modules.payment.domain import PaymentStatus, PaymentFact
    from app.modules.payment.events import PaymentCaptured, PaymentRefunded

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

The outbound adapter is `app/integrations/payments/moyasar.py`. This module
owns the domain; the adapter owns the HTTP and the vendor's JSON shape.
"""
