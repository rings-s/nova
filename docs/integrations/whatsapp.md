# WhatsApp Integration

**Not implemented.** `backend/app/integrations/whatsapp/client.py` defines a `WhatsAppClient`
Protocol (`send_template_message`) and `NotConfiguredWhatsAppClient`, which raises until a real
adapter exists.

## Requirement

Official WhatsApp Business Platform, through an **approved BSP** (Business Solution Provider) —
direct WhatsApp Cloud API access without a BSP is not the stated requirement.

## To verify

- Which BSP (e.g. a specific approved provider) — not chosen yet.
- Template message approval workflow and turnaround time.
- 24-hour customer-service session window rules and how they interact with booking reminders.
- Webhook delivery/retry guarantees for inbound messages and delivery receipts.
- Rate limits and messaging tiers for a new WhatsApp Business Account.
- Number provisioning process (existing number vs. new, verification requirements).

Do not implement against assumed API shapes — confirm against the chosen BSP's actual docs
before writing the real adapter.
