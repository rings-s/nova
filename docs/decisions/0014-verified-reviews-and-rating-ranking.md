# 0014 — Verified Reviews, Denormalised Rating Totals, and a Bayesian Ranking

## Status

Accepted — 2026-09-22 (migration `b4c5d6e7f8a9`).

## Context

Discovery (ADR-0010) could sort by name or by distance, but not by quality. A marketplace "top
rated" ranking is only worth something if a rating cannot be bought or inflated. That rules out an
owner rating their own salon, a customer rating a salon they never visited, and anyone rating one
visit twice.

## Decision

### A new `review` bounded context

`app/modules/review/` holds the `Review` aggregate (table `reviews`). It is a pure-validator module
(the ORM model is the entity), with the usual slice files and a `ReviewSubmitted` domain event.

- **Verified visits only.** `ReviewService.submit` accepts only a CUSTOMER principal. Staff could
  otherwise rate their own business. It reads the booking through
  `BookingService.get_for_principal`, which answers 404 for someone else's booking rather than
  confirming it exists, and requires the status to be `completed`.
- **Once per booking.** The service checks first, and the unique index `uq_reviews_booking_id`
  enforces it under concurrency. The review is flushed before the totals move, so a racing
  duplicate fails there and is never counted.
- **Ratings** are whole numbers from 1 to 5 (`ck_reviews_rating_range`, and `validate_rating`
  refuses `True`). A comment is optional, trimmed, and at most 1000 characters.
- **Routes** (`/tenants/{id}/reviews`): `POST ""` submits a review, `GET /mine` lists the caller's
  reviews at that business, and `GET ""` is a staff-only paged list for one business.

### The rating is public; the comment is not

The comment is shown to the business's staff only. Publishing free text on a public page is a
moderation and privacy decision (PDPL, docs/14) that this decision deliberately leaves open.

### Totals live on `businesses`, maintained in the same transaction

`businesses.rating_count` and `rating_sum` are running totals. `ReviewService` calls
`CatalogService.record_rating(business_id, rating)` in the transaction that stores the review, so
the totals can never disagree with `reviews`. Check constraints bound them
(`rating_count >= 0`, `rating_sum BETWEEN rating_count AND rating_count * 5`). The totals sit on
`businesses` because discovery's SELECT-only window can already read that table (ADR-0010). A join
from there to `reviews` would need a second public policy.

### Ranking is a Bayesian average

`catalog.domain.rating_score` ranks a business as if it had also received 5 ratings of 3.5
(`RATING_PRIOR_WEIGHT`, `RATING_PRIOR_MEAN`). One 5-star visit therefore does not outrank two hundred
visits averaging 4.8, and a new salon has to earn its place. `PublicCatalogRepository` computes the
same expression in SQL so the database can order and page by it, and a catalog test pins the two
together. Cards display the plain `rating_average` (None until someone rates) and `rating_count`.

Discovery search takes `sort=default|distance|rating`. `default` means nearest first when the
customer is located, and by name otherwise.

## Consequences

- There is no edit or delete of a review, and no un-counting of a rating. Adding either means
  adjusting the totals in the same transaction.
- Staff cannot reply to a review, and no customer can read another customer's comment.
- Reviewing is per tenant: `GET /mine` answers for one tenant's business at a time.
