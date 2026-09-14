"""Bounded context: NOTIFICATION — WhatsApp and customer messaging.

Aggregates      Notification
Tables          notifications
Depends on      identity (reacts to events from booking, queue, and payment)
Status          implemented

Domain style: PURE FUNCTIONS over a small status enum. The interesting rules
here are not about lifecycle — they are about permission to speak to someone.

This context is a CONSUMER. It reacts to domain events — `BookingConfirmed`,
`BookingCancelled`, `CustomerCalled`, `PaymentCaptured` — and must never be
called directly by booking or queue. If you find yourself importing
NotificationService from booking, publish an event instead. The subscriptions
live in `app/worker/outbox.py`.

Three gates every message passes before it leaves:

  1. CONSENT is per channel, and separately for marketing (PDPL). Agreeing to
     receive a booking confirmation on WhatsApp is not agreeing to receive
     offers there. No consent produces a SUPPRESSED record — deliberately not
     FAILED, because nothing went wrong and the record is the evidence that the
     opt-out was honoured.
  2. QUIET HOURS apply to marketing only, evaluated in the CUSTOMER's timezone.
     A transactional message ignores them: a reminder the night before a 6am
     appointment is the entire point.
  3. DEDUPE, because the outbox delivers at-least-once. The same
     BookingConfirmed can arrive twice, and a customer told twice that their
     booking is confirmed reads it as a system that double-booked them.

Outbound messages are pre-approved WhatsApp templates, never free text —
`MessageTemplate` is an allowlist, and only the parameters a template declares
are sent to the BSP.

Public surface — what other modules may import:
    from app.modules.notification.service import NotificationService
    from app.modules.notification.domain import MessageTemplate

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Adapter: `app/integrations/whatsapp/client.py`.
"""
