"""Bounded context: BOOKING — deterministic availability and the appointment lifecycle.

The core context. Everything else exists to support it.

Aggregates      Booking
Tables          bookings
Depends on      identity (tenant_id), catalog (service duration, provider skill)
Status          implemented

Public surface — what other modules may import:
    from app.modules.booking.service import BookingService
    from app.modules.booking.domain import BookingStatus, BookingSource
    from app.modules.booking.domain import BookingFact, CustomerVisitFact, ProviderCapacityFact
    from app.modules.booking.events import BookingConfirmed, BookingCancelled

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Two rules this context must never break:

  1. No double-booking. A provider cannot hold two overlapping bookings in a
     blocking status. Enforced in `domain.conflicts_with` and again by a
     database constraint.
  2. Confirmation is not the agent's to give. The AI booking agent may take a
     booking as far as PENDING_PAYMENT; only a verified payment confirms it
     (docs/10 section 5).

This module has a rich domain entity (`domain.Booking`) that is NOT the ORM
model (`models.BookingRecord`). The repository maps between them. See
nova_backend/README.md, "Two styles of domain.py", for why booking earns this
and catalog does not.
"""
