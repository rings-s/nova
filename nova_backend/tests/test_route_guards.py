"""Every route carries the guards the API rules require. Pure — no database.

`tests/test_architecture.py` checks what each file imports. This checks what
each endpoint actually depends on, which is where these rules live:

  - Fail closed (ADR-0006). Every route authenticates a principal, except the
    few that cannot have one: signing in, the signature-verified payment
    webhook, and the public marketplace (ADR-0010).
  - Tenant routes authorize the path's tenant (ADR-0003, ADR-0006) through
    `get_authorized_tenant`, and scope the request's connection for RLS through
    `get_tenant_context`. The AI routes are the exception to the second half:
    they hold no request transaction, and every unit of work a chat turn opens
    scopes itself.
  - Authenticated writes declare `write_rate_limit`.
  - Routes that move money or read what a business earns demand a role
    permission (`RequirePermission`), not merely staff.

When this file was written, `GET /tenants/{tenant_id}/ai/agents` broke the first
two rules and twenty authenticated writes broke the third.
"""

from collections.abc import Callable
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.deps import get_authorized_tenant, get_db_session, get_tenant_context
from app.core.security import get_principal
from app.core.throttling import write_rate_limit
from app.modules.identity.dependencies import RequirePermission
from app.modules.identity.domain import StaffPermission
from app.modules.registry import routers

#: Routes with no principal to authenticate, each guarded by something else.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/auth/register"),  # per-IP rate limit
        ("POST", "/auth/login"),  # per-IP rate limit, account lockout
        ("POST", "/auth/refresh"),  # the refresh token itself
        ("POST", "/webhooks/moyasar"),  # the gateway's signature over the raw body
    }
)
#: ADR-0010: read-only but for referrals, published rows only, per-IP limits.
PUBLIC_PREFIX = "/discovery/"

#: Tenant routes that hold no request transaction, so have no connection to
#: scope. A chat turn scopes each unit of work it opens (`TenantServiceScope`);
#: an open transaction here would hold a connection and locks across inference.
TRANSACTIONLESS_TENANT_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/tenants/{tenant_id}/ai/chat"),
        ("GET", "/tenants/{tenant_id}/ai/agents"),
    }
)

_BILLING = "/tenants/{tenant_id}/billing"
_ANALYTICS = "/tenants/{tenant_id}/analytics"
_MANAGE = frozenset({StaffPermission.MANAGE_SUBSCRIPTION})
_FINANCIALS = frozenset({StaffPermission.VIEW_FINANCIALS})
_INSIGHTS = frozenset({StaffPermission.VIEW_ANALYTICS})

#: Every billing route but the price list, the refund, and the analytics routes
#: that need more than the router's `view_analytics`, with what each demands.
#: A new billing route fails `test_money_routes_are_gated_by_role` until it is
#: classified here.
ROLE_GATED_ROUTES: dict[tuple[str, str], frozenset[StaffPermission]] = {
    ("POST", f"{_BILLING}/subscriptions"): _MANAGE,
    ("POST", f"{_BILLING}/subscriptions/{{business_id}}/plan"): _MANAGE,
    ("POST", f"{_BILLING}/subscriptions/{{business_id}}/cancel"): _MANAGE,
    ("GET", f"{_BILLING}/subscriptions/{{business_id}}"): _FINANCIALS,
    ("GET", f"{_BILLING}/invoices"): _FINANCIALS,
    ("GET", f"{_BILLING}/invoices/{{invoice_id}}"): _FINANCIALS,
    ("GET", f"{_BILLING}/invoices/{{invoice_id}}/lines"): _FINANCIALS,
    ("GET", f"{_BILLING}/commission-lines/{{line_id}}/explain"): _FINANCIALS,
    ("GET", f"{_BILLING}/payouts"): _FINANCIALS,
    ("POST", "/tenants/{tenant_id}/payments/{payment_id}/refund"): frozenset(
        {StaffPermission.REFUND_PAYMENTS}
    ),
    ("GET", f"{_ANALYTICS}/financial-summary"): _INSIGHTS | _FINANCIALS,
}
#: The published price list: any authenticated caller on the tenant, by design.
UNGATED_BILLING_ROUTES: frozenset[tuple[str, str]] = frozenset({("GET", f"{_BILLING}/plans")})

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _routes() -> list[tuple[str, str, APIRoute]]:
    return [
        (method, route.path, route)
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in sorted(route.methods)
    ]


def _depends_on(dependant: Dependant, target: Callable[..., Any]) -> bool:
    return any(sub.call is target or _depends_on(sub, target) for sub in dependant.dependencies)


def _permissions(dependant: Dependant) -> frozenset[StaffPermission]:
    found: set[StaffPermission] = set()
    for sub in dependant.dependencies:
        if isinstance(sub.call, RequirePermission):
            found.add(sub.call.permission)
        found |= _permissions(sub)
    return frozenset(found)


def _is_public(method: str, path: str) -> bool:
    return (method, path) in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIX)


def test_every_route_authenticates_unless_it_cannot() -> None:
    unauthenticated = [
        f"{method} {path}"
        for method, path, route in _routes()
        if not _is_public(method, path) and not _depends_on(route.dependant, get_principal)
    ]
    assert unauthenticated == []


def test_every_tenant_route_is_authorized_for_its_tenant() -> None:
    unauthorized = [
        f"{method} {path}"
        for method, path, route in _routes()
        if path.startswith("/tenants/{tenant_id}")
        and not _depends_on(route.dependant, get_authorized_tenant)
    ]
    assert unauthorized == []


def test_every_tenant_route_scopes_its_connection_unless_it_holds_none() -> None:
    unscoped = [
        f"{method} {path}"
        for method, path, route in _routes()
        if path.startswith("/tenants/{tenant_id}")
        and (method, path) not in TRANSACTIONLESS_TENANT_ROUTES
        and not _depends_on(route.dependant, get_tenant_context)
    ]
    assert unscoped == []


def test_the_ai_routes_hold_no_request_transaction() -> None:
    """A dependency on the request session would hold a connection across inference."""
    holding = [
        f"{method} {path}"
        for method, path, route in _routes()
        if (method, path) in TRANSACTIONLESS_TENANT_ROUTES
        and _depends_on(route.dependant, get_db_session)
    ]
    assert holding == []


def test_every_authenticated_write_is_rate_limited() -> None:
    unthrottled = [
        f"{method} {path}"
        for method, path, route in _routes()
        if method in WRITE_METHODS
        and _depends_on(route.dependant, get_principal)
        and not _depends_on(route.dependant, write_rate_limit)
    ]
    assert unthrottled == []


def test_money_routes_are_gated_by_role() -> None:
    """`require_staff` alone would let a stylist refund a customer or read payouts."""
    wrong = []
    for method, path, route in _routes():
        key = (method, path)
        if key in UNGATED_BILLING_ROUTES:
            continue
        if key in ROLE_GATED_ROUTES:
            expected = ROLE_GATED_ROUTES[key]
        elif path.startswith(_ANALYTICS):
            expected = _INSIGHTS
        elif path.startswith(_BILLING):
            wrong.append(f"{method} {path}: not classified in ROLE_GATED_ROUTES")
            continue
        else:
            continue
        actual = _permissions(route.dependant)
        if actual != expected:
            wrong.append(f"{method} {path}: demands {sorted(actual)}, expected {sorted(expected)}")
    assert wrong == []


def test_every_exemption_still_names_a_real_route() -> None:
    """An exemption for a route that no longer exists is waiting to cover the
    next unguarded endpoint someone adds at that path."""
    routes = {(method, path) for method, path, _ in _routes()}
    assert routes >= PUBLIC_ROUTES
    assert routes >= TRANSACTIONLESS_TENANT_ROUTES
    assert routes >= set(ROLE_GATED_ROUTES) | UNGATED_BILLING_ROUTES
    assert any(path.startswith(PUBLIC_PREFIX) for _, path in routes)
