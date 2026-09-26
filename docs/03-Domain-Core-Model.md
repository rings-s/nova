---
title: Domain Core Model
created: 2026-08-11
project: NOVA
type: domain
status: design
tags: [domain, ddd, aggregates, events]
---

# Domain Core Model

> [!note] Bounded Contexts
> NOVA is divided into distinct Bounded Contexts to prevent a "Big Ball of Mud".

## 1. Identity & Access Context

- **Aggregates:** `User`, `Tenant` (Business), `Membership`.
- **Rules:** A User can belong to multiple Tenants (e.g., a receptionist working at two salon branches).

## 2. Catalog & Resource Context

- **Aggregates:** `BusinessProfile`, `Location`, `Service`, `Provider`.
- **Photos:** a business has one cover and up to 12 gallery photos (`BusinessPhoto`), stored as re-encoded WebP files outside the database (ADR-0013). Branches carry an owner-set map pin (ADR-0012).
- **Ratings:** `Business` keeps running `rating_count`/`rating_sum` totals, written only by the review context.
- **Rules:** Services require specific Provider skills. Providers have strict weekly schedules.

## 3. Booking & Availability Context (The Core)

- **Aggregates:** `Booking`, `Schedule`, `AvailabilitySlot`.
- **Value Objects:** `TimeBlock`, `Money`, `CancellationPolicy`.
- **Domain Events:**
  - `BookingConfirmed`
  - `BookingCancelled`
  - `SlotReleased`

## 4. Queue & Ticketing Context

- **Aggregates:** `Queue`, `QueueEntry`, `VirtualTicket`.
- **Rules:**
  - Walk-ins and Appointments share the same provider timeline but have different priority weights.
  - A `VirtualTicket` contains a cryptographic hash. The QR code payload is just the Ticket ID, never PII (Personally Identifiable Information).

## 5. Payment Context

- **Aggregates:** `PaymentIntent`, `Transaction`.
- **Rules:** Payment state is separate from Booking state. A booking can be `Confirmed` but `PaymentPending` (if deposit rules allow). Moyasar's webhook, or the payer's return (`POST …/payments/{id}/sync`), triggers capture, and only after NOVA fetches Moyasar's own record of the payment.

## 6. Review Context

- **Aggregates:** `Review`.
- **Rules:** Only the customer of a `completed` booking may rate it, once, 1-5 with an optional private comment. The rating updates the business's totals in the same transaction; the marketplace ranks by a Bayesian average of them (ADR-0014).
