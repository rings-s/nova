"""Bounded context: CATALOG — where the business operates and what it sells.

Aggregates      Business, Location, Service, Provider
Tables          businesses, locations, services, providers, provider_services
Depends on      identity (tenant_id)
Status          implemented

Public surface — what other modules may import:
    from app.modules.catalog.service import CatalogService
    from app.modules.catalog.exceptions import ServiceNotFoundError, ...
    from app.modules.catalog.domain import rating_average   (listing display)

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Booking asks this context two questions and must not answer them itself:
    CatalogService.get_service(id)                  -> duration and price
    CatalogService.is_provider_qualified(p, s)      -> may this provider do it

Review tells it one thing, in the transaction that stores the review:
    CatalogService.record_rating(business_id, rating)
"""
