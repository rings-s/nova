# Saudi PDPL — Items Flagged for Legal Review

**No compliance claim is made here.** This lists data-handling decisions in the current
scaffold that should be checked against Saudi Arabia's Personal Data Protection Law (PDPL) and
any other applicable GCC data-protection regulation by qualified legal counsel before
production use. Nothing below should be read as "NOVA is PDPL-compliant."

## Data currently collected (tenants module)

- Business phone number (`Tenant.phone`, `Branch.phone`) — business contact data, likely lower
  sensitivity, but still subject to applicable rules on storage/retention.
- No customer personal data is collected yet (no booking/customer module exists).

## Items to verify with counsel before handling customer data

- **Cross-border data transfer**: where is the production Postgres/Nextcloud actually hosted?
  PDPL has requirements on transferring personal data outside Saudi Arabia.
- **Consent model**: no consent-capture mechanism exists yet for customer data (bookings,
  WhatsApp opt-in, marketing/retention AI use). "Respect user consent" is a stated project
  requirement but no implementation exists.
- **Data minimization**: confirm what customer data booking/queue/payment modules actually
  need to store vs. what's convenient to store — "avoid storing unnecessary sensitive data" is
  a stated requirement, not yet tested against a real data model.
- **Retention/deletion**: no retention policy or deletion mechanism exists yet (no soft-delete,
  no data export/erasure endpoint).
- **WhatsApp message content**: messages sent/received via the future WhatsApp integration may
  contain personal data — confirm BSP's data handling and whether message content needs to be
  stored at all vs. just delivery status.
- **AI processing of customer data**: once AI support/sales/retention agents exist, confirm
  whether processing customer data through a local model (or cloud fallback) has PDPL
  implications distinct from normal application processing.
- **Payment data**: Moyasar integration will touch payment data — confirm NOVA's own storage
  scope (should be minimal; Moyasar as PCI-scope holder) against actual implementation once
  built.

## Action

Do not treat any of the above as resolved. Route to legal review before the corresponding
feature (customer accounts, WhatsApp, payments, AI) ships to real users.
