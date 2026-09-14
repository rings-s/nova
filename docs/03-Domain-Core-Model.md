---
title: Domain Core Model
created: 2026-08-11
project: NOVA
type: domain
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
- **Integration:** `BusinessProfile` holds the `nextcloud_folder_id` for media assets.
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
- **Rules:** Payment state is separate from Booking state. A booking can be `Confirmed` but `PaymentPending` (if deposit rules allow). Webhooks from Moyasar trigger state transitions.