"""Bounded context: REVIEW — verified ratings of completed visits.

Aggregates      Review
Tables          reviews
Depends on      booking (was the visit completed, and whose was it),
                catalog (the business's rating totals), identity (customer)
Status          implemented

A review is a customer's 1-5 rating of one completed booking, with an optional
comment. "Verified" is the whole design: a rating can only be attached to a
booking that belongs to the caller and actually happened, and only once. That is
what makes the marketplace's "top rated" ranking worth something — nobody can
rate a salon they never visited, and nobody can rate one visit twice.

The rating is public, through the business's running totals in catalog, which
discovery already reads. The comment is not: it is shown to the business's staff
only. Publishing free text on a public page is a moderation and privacy decision
(PDPL, docs/14) that this module deliberately leaves unmade.

Public surface — what other modules may import:
    from app.modules.review.service import ReviewService
    from app.modules.review.exceptions import ReviewNotAllowedError, ...

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py
"""
