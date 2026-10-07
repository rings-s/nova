---
title: API Error Codes
created: 2026-09-23
project: NOVA
type: reference
status: reference
verified: 2026-09-23
tags: [api, errors, reference]
---

# API error codes

Every error the NOVA API returns, what it means, and what your client should do about it. Use this
page when you write code that calls the API: the web app, an integration, or a test.

`tests/test_error_catalog.py` checks this page against the code, so a new error code fails the
build until it is listed here.

## The error envelope

Every error, from a missing token to an unexpected crash, has the same shape:

```json
{
  "error": {
    "code": "slot_unavailable",
    "message": "That time is no longer available for this provider.",
    "field": null,
    "retryable": true,
    "correlation_id": "caa6d9d6-892b-4df4-a21a-515f61436ed7"
  }
}
```

| Field            | What it tells you                                                                                                           |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `code`           | Stable and machine-readable. Branch on this, never on `message`.                                                            |
| `message`        | English text for a person. It can change between releases.                                                                  |
| `field`          | For a validation error, the input at fault (`phone`, `items.0.quantity`). Otherwise `null`.                                 |
| `retryable`      | Whether the same request may succeed later. See [Retrying](#retrying).                                                      |
| `correlation_id` | Also sent as the `X-Correlation-ID` response header. Quote it when you report a problem: the server logs carry the same id. |

The web app translates errors into Arabic by `code`, from `error.<code>` keys in
`nova-frontend/src/lib/i18n/ar/errors.js`.

## Retrying

`retryable` is `true` for:

- every `409 Conflict`. The state that blocked you may have changed, for example a slot freed up.
  Re-read the state before you retry; don't loop blindly.
- `429 rate_limit_exceeded`. Wait for the number of seconds in the `Retry-After` header.
- `500 internal_error` and `502 payment_gateway_error`. Retry with backoff.

For everything else, sending the same request again gets the same answer. Change the request, or
show the error.

When you retry a `POST` that creates something, send the same `Idempotency-Key` header as the first
attempt, so a retry can't create a second booking or a second charge. The endpoints that support it
say so in their description at `/docs`.

## General

| Code                         | HTTP | Meaning                                                                                                                   | What to do                                                       |
| ---------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `validation_error`           | 422  | The request body, query or path failed validation. `field` names the input.                                               | Fix the input named in `field`.                                  |
| `not_found`                  | 404  | Something was not found; a more specific `*_not_found` code is usual.                                                     | Check the id.                                                    |
| `conflict`                   | 409  | A generic conflict; a more specific code is usual.                                                                        | Re-read, then retry.                                             |
| `http_<status>`              | any  | The framework answered before NOVA's code ran, such as `http_404` for an unknown path or `http_405` for the wrong method. | Check the URL and method.                                        |
| `internal_error`             | 500  | An unexpected server fault. The details are in the server logs, never in the response.                                    | Retry with backoff. If it persists, report the `correlation_id`. |
| `integration_not_configured` | 503  | This deployment has no credentials for the service this needs (Moyasar, WhatsApp).                                        | Nothing a client can fix. The operator sets the credentials.     |

## Signing in and permissions

| Code                          | HTTP | Meaning                                                                                              | What to do                                                                                    |
| ----------------------------- | ---- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `unauthenticated`             | 401  | No token, a malformed or expired one, or a refresh token used to call the API.                       | Refresh the access token (`POST /auth/refresh`) and retry once. If that fails, sign in again. |
| `invalid_credentials`         | 401  | Wrong email or password, or a locked account. All three give the same answer on purpose.             | Show a generic sign-in error. Don't say which part was wrong.                                 |
| `email_already_registered`    | 409  | An account with this email exists.                                                                   | Offer sign-in instead.                                                                        |
| `forbidden`                   | 403  | You are signed in but may not do this: a customer on a staff route, a tenant you don't belong to, or an `/admin` route without a superuser account. | Don't retry. Hide the action for this user.                                                   |
| `insufficient_role`           | 403  | Staff, but your role in this business lacks the permission, such as a receptionist issuing a refund. | Hide the action; `GET /tenants/{id}/memberships/me` lists what the role allows.               |
| `no_phone_to_verify`          | 422  | Phone verification was requested for an account with no phone number.                                | Ask for a phone number first.                                                                 |
| `invalid_verification_token`  | 422  | A phone verification token is wrong, expired, or for another purpose.                                | Request a new one.                                                                            |
| `phone_verification_required` | 422  | Your phone matches an existing customer record, and you must prove it is yours before it is linked.  | Verify the phone (`POST /auth/phone/verify/request`, then `/confirm`), then retry.            |

## Tenants, staff and customers

| Code                              | HTTP | Meaning                                                                                           | What to do                                                  |
| --------------------------------- | ---- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `tenant_not_found`                | 404  | No such tenant.                                                                                   | Check the id in the path.                                   |
| `tenant_mismatch`                 | 409  | A record from one tenant was written under another tenant's scope. A server-side safeguard.       | Report it: a correct client never causes this.              |
| `duplicate_slug`                  | 409  | A tenant, business or location with that name, or its URL slug, exists.                           | Choose another name.                                        |
| `membership_not_found`            | 404  | No such staff membership in this business.                                                        | Refresh the team list.                                      |
| `duplicate_membership`            | 409  | This person already works here.                                                                   | Change their role instead of inviting them again.           |
| `invalid_invite`                  | 401  | The invite token is wrong, expired, or already used.                                              | Ask the business for a new invite.                          |
| `last_owner`                      | 409  | The change would leave the business with no owner.                                                | Appoint another owner first.                                |
| `customer_not_found`              | 404  | No such customer here. For `/customers/me/consent`: you have no customer record at this business. | Check the id; a customer gets a record by booking.          |
| `duplicate_customer_phone`        | 409  | A customer with this phone number exists in this business.                                        | Search for them instead of creating one.                    |
| `customer_phone_required`         | 422  | Your account has no phone number, and a booking needs one.                                        | Add a phone number to the account, then book.               |
| `marketing_consent_customer_only` | 403  | Staff tried to opt a customer in to marketing. Only the customer can.                             | Staff may record WhatsApp consent and withdraw either kind. |

## Catalog and marketplace

| Code                        | HTTP | Meaning                                                                                                                   | What to do                                                       |
| --------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `business_not_found`        | 404  | No such business in this tenant.                                                                                          | Check the id.                                                    |
| `location_not_found`        | 404  | No such branch.                                                                                                           | Check the id.                                                    |
| `service_not_found`         | 404  | No such service.                                                                                                          | Check the id.                                                    |
| `category_not_found`        | 404  | No such service category, or it has been retired. Salons choose from `GET /discovery/categories` and cannot add to it.   | Pick a category from the list; ask a NOVA administrator for a new one. |
| `catalog_item_in_use`       | 409  | The branch, service or provider still has an appointment to come, so it can't be deleted.                                 | Cancel or move those bookings first, or switch it off with `is_active: false`. |
| `provider_not_found`        | 404  | No such provider.                                                                                                         | Check the id.                                                    |
| `provider_not_qualified`    | 422  | The provider does not perform this service.                                                                               | Pick a qualified provider, or qualify them in the catalog first. |
| `cross_location_assignment` | 422  | A provider can only take services at their own branch.                                                                    | Pick a service at the provider's branch.                         |
| `photo_not_found`           | 404  | No such photo, or the signed preview link has expired.                                                                    | Reload the photo list for fresh links.                           |
| `gallery_full`              | 409  | The gallery holds its maximum number of photos.                                                                           | Delete one first.                                                |
| `photo_too_large`           | 413  | The upload is over the size limit (10 MB by default).                                                                     | Upload a smaller file.                                           |
| `invalid_image`             | 422  | The upload is not an image the server can read.                                                                           | Upload a JPEG, PNG or WebP.                                      |
| `listing_not_found`         | 404  | No published marketplace listing at this slug: it doesn't exist, the owner hid it, or it is hidden for an unpaid invoice. | Treat it as gone.                                                |

## Booking

| Code                             | HTTP | Meaning                                                                                                                                                                                   | What to do                                                   |
| -------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `booking_not_found`              | 404  | No such booking, or it is someone else's. A customer never sees another person's booking, so both cases answer 404.                                                                       | Check the id.                                                |
| `slot_unavailable`               | 409  | Someone else took this time first.                                                                                                                                                        | Fetch availability again and let the user pick another time. |
| `slot_not_offered`               | 422  | The `slot_id` was not issued by the server for this slot.                                                                                                                                 | Book only slots returned by the availability endpoint.       |
| `hold_not_found`                 | 404  | No such slot hold.                                                                                                                                                                        | Hold the slot again.                                         |
| `hold_expired`                   | 409  | The hold ran out before the booking was made.                                                                                                                                             | Check availability and hold again.                           |
| `hold_limit_reached`             | 409  | You already hold the maximum number of slots at this business.                                                                                                                            | Book or release a held slot first.                           |
| `provider_location_mismatch`     | 422  | The provider doesn't work at the requested branch.                                                                                                                                        | Pick a provider at that branch.                              |
| `availability_horizon_too_large` | 422  | The availability window asked for is longer than allowed.                                                                                                                                 | Ask for a shorter range.                                     |
| `invalid_schedule`               | 422  | Working hours or a date range that don't make sense: a window that ends before it starts, a weekday outside 0–6, or an availability `date_to` before `date_from`. The message says which. | Fix the value the message names.                             |
| `invalid_time_range`             | 422  | A booking's end is not after its start.                                                                                                                                                   | Fix the times.                                               |
| `invalid_booking_transition`     | 409  | The booking's status doesn't allow this, such as completing a cancelled booking. The message lists the allowed moves.                                                                     | Reload the booking and offer only the allowed actions.       |
| `cancellation_too_late`          | 409  | The free-cancellation window has closed.                                                                                                                                                  | Tell the customer; staff can still cancel for them.          |

## Queue and tickets

| Code                        | HTTP | Meaning                                                                          | What to do                                                                 |
| --------------------------- | ---- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `queue_not_found`           | 404  | No such queue.                                                                   | Check the id.                                                              |
| `queue_entry_not_found`     | 404  | No such place in the queue, or it is someone else's.                             | Check the id.                                                              |
| `queue_closed`              | 409  | The queue is not taking new walk-ins.                                            | Try later, or book an appointment.                                         |
| `already_in_queue`          | 409  | This customer is already waiting in that queue.                                  | Show their existing place.                                                 |
| `no_one_waiting`            | 409  | "Call next" on an empty queue.                                                   | Nothing to do.                                                             |
| `invalid_queue_transition`  | 409  | The entry's status doesn't allow this.                                           | Reload the queue.                                                          |
| `ticket_not_found`          | 404  | No such ticket.                                                                  | Check the id.                                                              |
| `ticket_invalid`            | 422  | The scanned QR code is not a valid ticket for this business. Deliberately vague. | Ask the customer to show the ticket again, or look the booking up by hand. |
| `ticket_expired`            | 409  | The ticket's validity has passed.                                                | Issue a new ticket for the booking.                                        |
| `invalid_ticket_transition` | 409  | The ticket was already used or revoked.                                          | Check the booking's status instead.                                        |

## Payments

| Code                          | HTTP | Meaning                                                                     | What to do                                               |
| ----------------------------- | ---- | --------------------------------------------------------------------------- | -------------------------------------------------------- |
| `payment_not_found`           | 404  | No such payment, or not one you may see.                                    | Check the id.                                            |
| `return_url_not_allowed`      | 422  | `return_url` is not an absolute URL on the app's own origin.                | Use a URL on `PUBLIC_APP_URL`.                           |
| `payment_amount_too_small`    | 422  | Below the smallest amount payable online (1.00 SAR).                        | Take the payment at the counter.                         |
| `payment_gateway_error`       | 502  | Moyasar answered with an error or could not be reached.                     | Retry with backoff.                                      |
| `payment_not_captured`        | 409  | A refund was asked for on a payment that was never captured.                | Nothing to refund.                                       |
| `refund_exceeds_capture`      | 422  | The refund is more than what remains refundable.                            | Refund at most the remaining amount.                     |
| `invalid_payment_transition`  | 409  | The payment's status doesn't allow this.                                    | Reload the payment.                                      |
| `payment_verification_failed` | 409  | What Moyasar reports paid doesn't match this payment. Nothing was captured. | Staff should check the payment in the Moyasar dashboard. |
| `payment_amount_mismatch`     | 409  | The paid amount or currency differs from the payment's. Not captured.       | As above.                                                |
| `payment_checkout_mismatch`   | 409  | The gateway payment paid a different checkout. Not captured.                | As above.                                                |

These answer Moyasar's webhook calls, not app clients:

| Code                        | HTTP | Meaning                                                                                         |
| --------------------------- | ---- | ----------------------------------------------------------------------------------------------- |
| `invalid_webhook_signature` | 422  | The webhook's `secret_token` is missing or wrong. Despite the name, Moyasar sends no signature. |
| `unknown_webhook_payment`   | 404  | The webhook names a payment NOVA has no record of.                                              |
| `payment_not_confirmed`     | 503  | The webhook's claim disagrees with Moyasar's own record. The 503 makes Moyasar retry.           |

## Billing

| Code                               | HTTP | Meaning                                                            | What to do                           |
| ---------------------------------- | ---- | ------------------------------------------------------------------ | ------------------------------------ |
| `subscription_not_found`           | 404  | This business has no subscription.                                 | Subscribe first.                     |
| `subscription_exists`              | 409  | This business already has a subscription.                          | Change its plan instead.             |
| `subscription_not_awaiting_payment` | 409  | The subscription has nothing to pay: it is not a paid plan waiting for its first payment. | Reload the subscription. |
| `checkout_not_found`               | 404  | No such plan checkout in this business.                            | Check the id.                        |
| `downgrade_below_usage`            | 409  | The new plan allows fewer staff seats or branches than are in use. | Remove the extras, then change plan. |
| `plan_feature_required`            | 403  | The business's plan doesn't include this feature.                  | Offer an upgrade.                    |
| `invoice_not_found`                | 404  | No such invoice.                                                   | Check the id.                        |
| `invoice_already_issued`           | 409  | An issued invoice can't be edited.                                 | Issue a credit note instead.         |
| `commission_line_not_found`        | 404  | No such commission line.                                           | Check the id.                        |
| `commission_line_already_reversed` | 409  | This commission was already reversed.                              | Nothing to do.                       |
| `commission_line_already_invoiced` | 409  | This commission is on an issued invoice and can't be re-rated.     | Adjust it on the next invoice.       |

## Reviews and notifications

| Code                              | HTTP | Meaning                                                | What to do                                                     |
| --------------------------------- | ---- | ------------------------------------------------------ | -------------------------------------------------------------- |
| `review_not_allowed`              | 409  | The visit isn't completed yet.                         | Offer the review once the visit is completed.                  |
| `already_reviewed`                | 409  | This visit has already been rated.                     | Show the existing review.                                      |
| `notification_not_found`          | 404  | No such notification.                                  | Check the id.                                                  |
| `consent_withheld`                | 409  | The customer hasn't consented to this kind of message. | Don't send it. Record consent first, if the customer gives it. |
| `invalid_notification_transition` | 409  | The notification's status doesn't allow this.          | Reload it.                                                     |

## Analytics and AI agents

| Code                    | HTTP | Meaning                                                                                                  | What to do                                      |
| ----------------------- | ---- | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `chart_not_found`       | 404  | No chart with that id.                                                                                   | Use an id from `GET /analytics/charts`.         |
| `report_window_invalid` | 422  | The date range ends before it starts, or is longer than a report may cover. The message gives the limit. | Fix the range.                                  |
| `report_too_large`      | 422  | Too many rows in the range to report on correctly. The report is refused, not truncated.                 | Choose a shorter period.                        |
| `insufficient_data`     | 422  | Not enough history for a forecast: it needs several complete weeks. The message says how many.           | Show "not enough data yet".                     |
| `agent_guardrail`       | 403  | The assistant refused: the agent is not available to you, or the request crosses one of its rules.       | Show the message; don't retry the same request. |

## Rate limits and idempotency

| Code                     | HTTP | Meaning                                                         | What to do                                   |
| ------------------------ | ---- | --------------------------------------------------------------- | -------------------------------------------- |
| `rate_limit_exceeded`    | 429  | Too many requests from you in the window.                       | Wait `Retry-After` seconds.                  |
| `ai_busy`                | 429  | The assistant is answering someone else, or you already have a message being answered. | Retry in a few seconds.                      |
| `request_in_flight`      | 409  | A request with this `Idempotency-Key` is still being processed. | Wait a moment, then retry with the same key. |
| `idempotency_key_reused` | 422  | This `Idempotency-Key` was used with a different request body.  | Use a new key for a new request.             |

## Database constraint codes

A few rules are enforced by the database itself. When one is broken, you get one of these rather
than a 500. The specific constraints NOVA names map to codes listed above (`slot_unavailable`,
`duplicate_slug`, `already_reviewed`, `invalid_time_range`). Anything else falls back to:

| Code                   | HTTP | Meaning                                                  | What to do                 |
| ---------------------- | ---- | -------------------------------------------------------- | -------------------------- |
| `duplicate_value`      | 409  | A value that must be unique is already used.             | Change the value.          |
| `invalid_reference`    | 422  | The request refers to a record that doesn't exist.       | Check the ids in the body. |
| `constraint_violation` | 422  | A value breaks a database rule.                          | Check the values.          |
| `integrity_conflict`   | 409  | The request conflicts with existing data in another way. | Re-read, then retry.       |
