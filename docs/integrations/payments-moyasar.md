# Payments — Moyasar Integration

**Not implemented.** `backend/app/integrations/payments/moyasar.py` defines a `PaymentGateway`
Protocol (`create_payment`, `verify_webhook`) and `NotConfiguredPaymentGateway`, which raises
until a real adapter exists.

## To verify

- Which payment methods are enabled on the NOVA Moyasar account (mada, cards, Apple Pay, STC
  Pay, etc.) — affects what the frontend needs to render.
- Webhook signature verification scheme and payload shape.
- Refund/void semantics and how they map to booking cancellation flows.
- Currency support beyond SAR (the platform's default currency is configurable — see
  [[../architecture/tech-stack]] — but Moyasar's supported currencies must be confirmed).
- Settlement/payout timing, relevant for business-facing reporting later.

Do not implement against assumed API shapes — confirm against Moyasar's actual docs and the
account's enabled methods before writing the real adapter.
