# 0016 — Staff Are Staff Only Where They Work, and Customers Everywhere Else

## Status

Accepted — 2026-10-07. Narrows ADR-0003's tenant check for staff principals; ADR-0006's
fail-closed rule and the per-row ownership checks are unchanged.

## Context

A token's `kind` is account-wide. `AuthService._issue_pair` mints STAFF for any account with a
membership and CUSTOMER otherwise. `Principal.can_access_tenant` admits a CUSTOMER at every tenant
(NOVA is a marketplace) but a STAFF principal only at its own. So a stylist who works at one salon
could not book a treatment at another one: every route at that salon answered 403. The same applied
to the marketplace assistant, which refused anyone but a CUSTOMER.

The fix cannot simply let STAFF reach other tenants. `is_staff` is read by `require_staff` and by
service code (`BookingService.get_for_principal`, `resolve_booking_customer`, queue and payment
checks), and a stylist admitted to another salon would have staff authority there.

Two options were weighed:

- **(a) Mint `kind` per tenant in the token.** Cleanest in principle, but every token claim and
  guard changes, and a token would need re-issuing per business visited.
- **(b) Derive the kind per request from the path's tenant.** `tenant_id` already comes only from
  the path, so the request itself says which business the caller is acting on.

## Decision

Option (b), in one place: `app/core/security.py::principal_at_tenant`.

- `get_principal` reads the path's `tenant_id`. A STAFF principal acting on a tenant that is not
  among its token's `tenant_ids` becomes a CUSTOMER for that request, with no `tenant_ids` and no
  `roles`. Every `is_staff` check and `require_staff` at that tenant then sees a customer, and
  `can_access_tenant` admits it as it admits any customer.
- Routes with no tenant in the path keep the token's kind, except the marketplace assistant, which
  acts only as a customer and depends on `get_customer_principal`.
- At a tenant the account is a member of, nothing changes. Role permissions are still read from that
  tenant's `memberships` row (`RequirePermission`).
- The web app's `authStore.isCustomerAt(tenantId)` mirrors the rule to decide whether to show the
  assistant. It only hides UI; the API decides.

## Consequences

- A stylist can book, queue, pay and review at another salon, as a customer, under their own account
  and phone number, through the same ownership checks as anyone else.
- A staff member still cannot act as a customer at their own salon: there, the account is staff.
  Booking for themselves at work goes through the dashboard's on-behalf-of path.
- `tests/modules/identity/test_staff_elsewhere.py` runs the real token path: customer at another
  salon, 403 on a staff route there, and still staff at their own. `tests/test_security.py`
  `TestStaffElsewhere` covers `principal_at_tenant` itself.
