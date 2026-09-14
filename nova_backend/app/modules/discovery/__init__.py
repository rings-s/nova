"""Bounded context: DISCOVERY — the public marketplace surface.

Aggregates      MarketplaceReferral
Tables          marketplace_referrals
Depends on      catalog (listings), booking (availability), identity (tenant_id)
Status          implemented

This is the only context that is public and cross-tenant, and the two facts are
the same fact: a customer searching for a salon has not chosen one yet, so
there is no tenant to scope to and no account to authenticate. Every other
route in NOVA answers "what may this caller see inside one tenant"; discovery
answers "which tenant should this customer be looking at at all".

It exists as its own slice rather than as more endpoints on `catalog` because
the two have opposite security models. Catalog is tenant-scoped by
construction — `TenantScopedRepository` makes a cross-tenant read
unrepresentable — and putting an unauthenticated, cross-tenant read path in the
same module would mean that guarantee no longer holds where it is written down.
Discovery composes catalog through `PublicCatalogService` instead, which is the
one read path catalog publishes for it.

It owns one aggregate of its own, and that aggregate is why the module is worth
having: `MarketplaceReferral` is the server-side record that NOVA introduced a
customer to a business. ADR-0008 froze `BookingSource.MARKETPLACE` with no
writer precisely because that record did not exist, which left every commission
line accruing 0.00 (ADR-0009). Discovery is its writer.

Public surface — what other modules may import:
    from app.modules.discovery.service import DiscoveryService
    from app.modules.discovery.exceptions import ListingNotFoundError

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Booking asks this context exactly one question, at creation time only:
    DiscoveryService.attributes_to_marketplace(token, business_id) -> bool
"""
