"""Catalog persistence: what a business is, where it operates, what it sells.

Naming note: docs/08 shows a single `name` column, but ADR-0004 fixed
`name_en`/`name_ar` as the bilingual strategy and `identity.Tenant` already
follows it. The ADR wins — a GCC storefront cannot render a single-language
service name. docs/08 needs updating to match.
"""

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantOwnedMixin, TimestampMixin, UUIDPKMixin


class Business(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """The public-facing storefront for a tenant."""

    __tablename__ = "businesses"
    __table_args__ = (
        CheckConstraint("rating_count >= 0", name="rating_count_non_negative"),
        # Every rating is 1..5, so the sum is bounded by the count on both sides.
        CheckConstraint(
            "rating_sum BETWEEN rating_count AND rating_count * 5",
            name="rating_sum_in_range",
        ),
    )

    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description_en: Mapped[str | None] = mapped_column(Text)
    description_ar: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Whether this business appears on the public marketplace (ADR-0010).
    #:
    #: Distinct from `is_active`, and the two fail in opposite directions.
    #: `is_active` false means the business is switched off entirely — nothing
    #: it owns is bookable. `is_listed` false means it is simply not advertised
    #: on NOVA: its own booking link, WhatsApp flow and reception keep working.
    #:
    #: That distinction is what docs/11 section 8 needs when an unpaid invoice
    #: reaches day 21 — the listing is hidden while "the calendar, queue, and
    #: existing bookings keep working". Hiding it with `is_active` instead would
    #: cancel the salon's operations over an overdue bill.
    #:
    #: Defaults to listed because docs/11 section 2 gives every plan tier a
    #: marketplace profile; it is an opt-out, not an opt-in.
    is_listed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: Running totals of the verified ratings this business has received
    #: (`review` module). Kept here rather than aggregated from `reviews` on
    #: every search because the marketplace reads businesses through the
    #: SELECT-only discovery window, and ratings are an attribute of the
    #: listing a customer is choosing between — not a reason to open a second
    #: cross-tenant window onto another table. `ReviewService` bumps both in
    #: the same transaction that inserts the review, with an atomic UPDATE.
    rating_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    rating_sum: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    locations: Mapped[list["Location"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class Location(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """A physical branch. Was `identity.Branch` before the catalog split."""

    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_locations_tenant_id_slug"),
        Index("ix_locations_tenant_business", "tenant_id", "business_id"),
        # Marketplace search filters on city case-insensitively, which a plain
        # index on `city` cannot serve. Declared here as well as in the
        # migration so autogenerate does not propose dropping it on every run —
        # the same reason `uq_users_email_lower` is declared on `User`.
        Index("ix_locations_city_lower", text("lower(city)")),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)

    #: Free-text city, matched case-insensitively by marketplace search.
    #: Nullable because every existing branch predates the column and because a
    #: home-service provider genuinely has no address; such a row is reachable
    #: by name and by map radius, just not by a city filter.
    city: Mapped[str | None] = mapped_column(String(120))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    # Required, not defaulted at the app layer: availability and queue maths are
    # wrong in a way that is hard to see if this is ever implicit.
    timezone: Mapped[str] = mapped_column(String(100), default="Asia/Riyadh", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship(back_populates="locations")


class Service(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """A bookable treatment offered at one location."""

    __tablename__ = "services"
    __table_args__ = (
        Index("ix_services_tenant_location", "tenant_id", "location_id"),
        Index("ix_services_tenant_category", "tenant_id", "category"),
    )

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    description_en: Mapped[str | None] = mapped_column(Text)
    description_ar: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(120))

    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Numeric, never Float — see Money in app/core/values.py.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SAR", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Provider(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """A staff member who performs services at a location."""

    __tablename__ = "providers"
    __table_args__ = (Index("ix_providers_tenant_location", "tenant_id", "location_id"),)

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(255))
    title_ar: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProviderService(Base, TenantOwnedMixin):
    """Which providers are qualified for which services.

    Booking reads this to reject a provider who cannot perform the requested
    service, and the AI booking agent reads it to only ever offer valid pairs.
    """

    __tablename__ = "provider_services"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), primary_key=True
    )


class BusinessPhoto(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A photo of a business: its cover (at most one) or one of its gallery.

    The row is the index; the pixels live in `integrations.storage`, one file
    per variant under `storage_prefix`. Stored images are always ones NOVA
    re-encoded itself (`integrations.images`), never the bytes uploaded.
    """

    __tablename__ = "business_photos"
    __table_args__ = (
        Index("ix_business_photos_business", "tenant_id", "business_id", "position"),
        # One cover per business, enforced where two concurrent uploads can't
        # both slip past a check.
        Index(
            "uq_business_photos_one_cover",
            "business_id",
            unique=True,
            postgresql_where=text("kind = 'cover'"),
        ),
        CheckConstraint("kind IN ('cover', 'gallery')", name="kind_valid"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Gallery order; lower first. Covers ignore it.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: `tenant_id/photo_id` — each variant is `<prefix>/<variant>.webp`.
    storage_prefix: Mapped[str] = mapped_column(String(80), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
