from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, or_, select

from app.db.repository import BaseRepository, TenantScopedRepository
from app.modules.catalog.models import (
    Business,
    Location,
    Provider,
    ProviderService,
    Service,
)


class _SoftDeleteAwareRepository[ModelT](TenantScopedRepository[ModelT]):
    """Adds an explicit `include_deleted` switch on top of tenant scoping.

    `SoftDeleteMixin` deliberately does not filter automatically — a booking
    made last month must still be able to resolve the service it used, even
    after the salon retires it. Listing for customers passes the default;
    resolving history passes `include_deleted=True`.
    """

    def _active(self, stmt: Select) -> Select:
        # Declarative attribute; see the note in `TenantScopedRepository._scope`.
        return stmt.where(self.model.is_deleted.is_(False))  # type: ignore[attr-defined]

    async def get(self, id: UUID, *, include_deleted: bool = False) -> ModelT | None:
        stmt = self._scope(self._base_select().where(self.model.id == id))  # type: ignore[attr-defined]
        if not include_deleted:
            stmt = self._active(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self, *, limit: int = 20, offset: int = 0, include_deleted: bool = False
    ) -> list[ModelT]:
        stmt = self._scope(self._base_select())
        if not include_deleted:
            stmt = self._active(stmt)
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())


class BusinessRepository(_SoftDeleteAwareRepository[Business]):
    model = Business

    async def get_by_slug(self, slug: str) -> Business | None:
        stmt = self._active(self._scope(self._base_select().where(Business.slug == slug)))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class LocationRepository(_SoftDeleteAwareRepository[Location]):
    model = Location

    async def list_for_business(self, business_id: UUID) -> list[Location]:
        stmt = self._active(
            self._scope(self._base_select().where(Location.business_id == business_id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ServiceRepository(_SoftDeleteAwareRepository[Service]):
    model = Service

    async def list_for_location(self, location_id: UUID) -> list[Service]:
        stmt = self._active(
            self._scope(self._base_select().where(Service.location_id == location_id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ProviderRepository(_SoftDeleteAwareRepository[Provider]):
    model = Provider

    async def list_for_location(self, location_id: UUID) -> list[Provider]:
        stmt = self._active(
            self._scope(self._base_select().where(Provider.location_id == location_id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def is_qualified(self, provider_id: UUID, service_id: UUID) -> bool:
        """Booking calls this before accepting a provider for a service."""
        stmt = select(ProviderService).where(
            ProviderService.tenant_id == self.tenant_id,
            ProviderService.provider_id == provider_id,
            ProviderService.service_id == service_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    def assign_service(self, provider_id: UUID, service_id: UUID) -> ProviderService:
        assignment = ProviderService(
            tenant_id=self.tenant_id, provider_id=provider_id, service_id=service_id
        )
        self.session.add(assignment)
        return assignment


# --- public marketplace reads --------------------------------------------
#
# Everything above this line is tenant-scoped: a repository instance is fixed
# to one tenant and structurally cannot read another's rows. The marketplace is
# the one place that rule cannot apply — a customer searching for "haircut in
# Riyadh" has no tenant yet, and finding one is the entire point (ADR-0010).
#
# So `PublicCatalogRepository` extends `BaseRepository`, not
# `TenantScopedRepository`, and pays for that with a different restriction:
# every query below is confined to rows a business has published, by the
# `_PUBLIC_*` predicates. It is read-only — there is deliberately no `add`.


def _public_business() -> list:
    """What makes a business publicly visible.

    Three separate flags, because they mean three different things and a
    listing must satisfy all of them:

      - `is_deleted`  — retired; the row survives only for historical bookings.
      - `is_active`   — switched off entirely; nothing it owns is bookable.
      - `is_listed`   — trading normally but not advertised on NOVA, which is
                        what an unpaid invoice does at day 21 (docs/11 §8).

    Returned as a list of clauses so callers can splat it into `.where()`.
    """
    return [
        Business.is_deleted.is_(False),
        Business.is_active.is_(True),
        Business.is_listed.is_(True),
    ]


def _public_location() -> list:
    return [Location.is_deleted.is_(False), Location.is_active.is_(True)]


def _public_service() -> list:
    return [Service.is_deleted.is_(False), Service.is_active.is_(True)]


def _public_provider() -> list:
    return [Provider.is_deleted.is_(False), Provider.is_active.is_(True)]


class PublicCatalogRepository(BaseRepository[Business]):
    """Cross-tenant reads of published catalog rows, for the marketplace.

    Two independent controls stand between this class and a leak, and they are
    deliberately not the same control twice:

      1. Every method here filters on the `_PUBLIC_*` predicates above, so an
         unlisted or retired business is invisible even to a correct query.
      2. Postgres RLS (migration `d0e1f2a3b4c5`) grants a matching SELECT-only
         policy that is gated on `app.discovery_mode`. Even if a predicate
         above were dropped by mistake, the database still refuses to return an
         unlisted row, and still refuses every write.

    The RLS policy is the reason `set_discovery_scope` must be called before
    anything here runs — without it these queries return nothing at all, which
    is the correct failure direction.
    """

    model = Business

    async def search(
        self,
        *,
        term: str | None = None,
        city: str | None = None,
        category: str | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[tuple[Business, Location, Decimal | None, str | None]]:
        """Published branches matching the filters, as marketplace cards.

        The unit of the result is a *branch*, not a business: a customer books
        at one address, and a chain's Riyadh and Jeddah branches are different
        answers to "near me". A business with three branches is three cards.

        Returns `(business, location, starting_price, currency)`. The price is
        the cheapest bookable service at that branch — the "from 150 SAR" on a
        listing card — computed as a correlated subquery so it costs one query
        rather than one per row.
        """
        cheapest = (
            select(func.min(Service.price))
            .where(Service.location_id == Location.id, *_public_service())
            .correlate(Location)
            .scalar_subquery()
        )
        currency = (
            select(Service.currency)
            .where(Service.location_id == Location.id, *_public_service())
            .correlate(Location)
            .order_by(Service.price.asc())
            .limit(1)
            .scalar_subquery()
        )

        stmt = (
            select(Business, Location, cheapest, currency)
            .join(Location, Location.business_id == Business.id)
            .where(*_public_business(), *_public_location())
        )

        if term:
            # Matches the business itself or anything it sells, so "haircut"
            # finds a salon that never mentions the word in its own name.
            # Bilingual on both sides (ADR-0004): a customer typing Arabic must
            # match `name_ar`, and neither language is the canonical one.
            pattern = f"%{term}%"
            sells_it = (
                select(Service.id)
                .where(
                    Service.location_id == Location.id,
                    *_public_service(),
                    or_(
                        Service.name_en.ilike(pattern),
                        Service.name_ar.ilike(pattern),
                        Service.category.ilike(pattern),
                    ),
                )
                .correlate(Location)
                .exists()
            )
            stmt = stmt.where(
                or_(
                    Business.name_en.ilike(pattern),
                    Business.name_ar.ilike(pattern),
                    Business.description_en.ilike(pattern),
                    Business.description_ar.ilike(pattern),
                    sells_it,
                )
            )

        if city:
            stmt = stmt.where(Location.city.ilike(city))

        if category:
            offers_category = (
                select(Service.id)
                .where(
                    Service.location_id == Location.id,
                    *_public_service(),
                    Service.category.ilike(category),
                )
                .correlate(Location)
                .exists()
            )
            stmt = stmt.where(offers_category)

        if bounding_box is not None:
            # A cheap, index-friendly prefilter. The exact great-circle
            # distance is computed in `domain.distance_km` afterwards, because
            # a bounding box is a square and the customer asked for a circle.
            min_lat, max_lat, min_lng, max_lng = bounding_box
            stmt = stmt.where(
                Location.latitude.is_not(None),
                Location.longitude.is_not(None),
                Location.latitude.between(min_lat, max_lat),
                Location.longitude.between(min_lng, max_lng),
            )

        # A stable total order. Without the id tiebreak, two branches with the
        # same name can swap places between pages and a customer sees one twice
        # while never seeing the other.
        stmt = stmt.order_by(Business.name_en.asc(), Location.id.asc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    async def get_business_by_slug(self, slug: str) -> Business | None:
        """The storefront lookup. `slug` is globally unique (docs/08 §147)."""
        stmt = select(Business).where(Business.slug == slug, *_public_business())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_locations(self, business_id: UUID) -> list[Location]:
        stmt = (
            select(Location)
            .where(Location.business_id == business_id, *_public_location())
            .order_by(Location.name_en.asc(), Location.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_services(self, location_ids: list[UUID]) -> list[Service]:
        if not location_ids:
            return []
        stmt = (
            select(Service)
            .where(Service.location_id.in_(location_ids), *_public_service())
            .order_by(Service.price.asc(), Service.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_providers(self, location_ids: list[UUID]) -> list[Provider]:
        if not location_ids:
            return []
        stmt = (
            select(Provider)
            .where(Provider.location_id.in_(location_ids), *_public_provider())
            .order_by(Provider.name_en.asc(), Provider.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_qualified_provider_ids(self, service_id: UUID) -> list[UUID]:
        """Providers who may actually perform this service.

        Discovery needs this to answer "who is free on Tuesday" without
        offering a stylist the salon never qualified — the same question
        `is_qualified` answers for booking, asked in the other direction.
        """
        stmt = (
            select(ProviderService.provider_id)
            .join(Provider, Provider.id == ProviderService.provider_id)
            .where(ProviderService.service_id == service_id, *_public_provider())
            .order_by(Provider.name_en.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_public_service(self, service_id: UUID) -> Service | None:
        stmt = select(Service).where(Service.id == service_id, *_public_service())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
