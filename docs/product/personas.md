# Personas

NOVA connects three parties. Every module should be clear about which persona(s) it serves.

## Customer

Books services, receives WhatsApp confirmations/reminders, holds a virtual QR ticket, may join
a walk-in queue. Primary language may be Arabic or English; GCC phone number.

## Business (owner/staff)

Owns one or more branches (see [[tenants-and-branches|../domain/tenants-and-branches]]).
Manages services, availability, staff, media, and views bookings/payments/queue state.
Bilingual identity (name/branding) is mandatory — see
[[0004-bilingual-field-strategy|../decisions/0004-bilingual-field-strategy]].

## Service Provider

Staff member performing services within a branch — not yet modeled (no module exists for this
yet). Future module; will hang off `Branch` similarly to how bookings will.

## Not yet a persona in the system

Platform admin/support roles are not modeled. Add a dedicated persona doc and module when that
work starts rather than retrofitting the tenant/branch model.
