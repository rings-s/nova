from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Literal
from uuid import UUID

from pydantic import Field, computed_field

from app.core.schemas import ApiSchema
from app.modules.catalog.domain import rating_average


class CreateBusinessRequest(ApiSchema):
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    description_en: str | None = None
    description_ar: str | None = None


class BusinessOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    name_en: str
    name_ar: str
    slug: str
    description_en: str | None
    description_ar: str | None
    is_active: bool
    #: Whether this business is advertised on the public marketplace.
    is_listed: bool
    #: Verified ratings received (`review` module). The sum is carried only to
    #: derive the average; clients get the average and the count.
    rating_count: int = 0
    rating_sum: int = Field(default=0, exclude=True)
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rating_average(self) -> float | None:
        return rating_average(self.rating_sum, self.rating_count)


class BusinessPhotoOut(ApiSchema):
    """A photo as the dashboard sees it. `urls` are short-lived signed links
    (an <img> cannot send a login token), valid whether or not the business is
    listed on the marketplace yet."""

    id: UUID
    business_id: UUID
    kind: str
    position: int
    width: int
    height: int
    created_at: datetime
    urls: dict[str, str]


class UpdatePhotoRequest(ApiSchema):
    """`kind: "cover"` makes this the cover (the old one joins the gallery);
    `position` is its place in the gallery, lowest first."""

    kind: Literal["cover", "gallery"] | None = None
    position: int | None = Field(default=None, ge=0)


class SetListingVisibilityRequest(ApiSchema):
    is_listed: bool


class SetLocationPositionRequest(ApiSchema):
    """Where a branch is on the map: both numbers, or both null to take it off.

    Not optional fields with a default. A body of `{}` is a mistake to be told
    about, not a request to clear the pin, so both keys must be present.
    """

    latitude: float | None
    longitude: float | None


class PlaceOut(ApiSchema):
    """What the map calls a point, in both languages, to fill the branch form.

    `name_en`/`name_ar` are a suggested branch name (the district, else the
    city); any field is null where the map has nothing (open desert, the sea).
    """

    latitude: float
    longitude: float
    city_en: str | None = None
    city_ar: str | None = None
    district_en: str | None = None
    district_ar: str | None = None
    name_en: str | None = None
    name_ar: str | None = None


class CreateLocationRequest(ApiSchema):
    business_id: UUID
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    timezone: str = "Asia/Riyadh"
    #: Used by marketplace search. Optional, but a branch without one cannot be
    #: found by a city filter — only by name or map radius.
    city: str | None = Field(default=None, max_length=120)
    latitude: float | None = None
    longitude: float | None = None


class _PartialUpdate(ApiSchema):
    """A PATCH body: only the fields sent change.

    `null` clears a field that may be empty (`clearable`); for any other it
    means "leave it", since a name or a price cannot be nothing.
    """

    clearable: ClassVar[frozenset[str]] = frozenset()

    def changes(self) -> dict[str, object]:
        return {
            field: value
            for field, value in self.model_dump(exclude_unset=True).items()
            if value is not None or field in self.clearable
        }


class UpdateLocationRequest(_PartialUpdate):
    """The map pin is `PATCH .../position`; `city: null` clears the city."""

    clearable = frozenset({"city"})

    name_en: str | None = Field(default=None, min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, min_length=1, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    timezone: str | None = None
    is_active: bool | None = None


class LocationOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    business_id: UUID
    name_en: str
    name_ar: str
    slug: str
    timezone: str
    city: str | None
    latitude: float | None
    longitude: float | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryOut(ApiSchema):
    """A service category as a service carries it: enough to label it."""

    id: UUID
    slug: str
    name_en: str
    name_ar: str


class CategoryAdminOut(CategoryOut):
    """A category as the superuser manages it, retired ones included."""

    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateCategoryRequest(ApiSchema):
    name_en: str = Field(min_length=1, max_length=120)
    name_ar: str = Field(min_length=1, max_length=120)


class UpdateCategoryRequest(ApiSchema):
    """Renames a category, or retires or restores it. Omitted fields keep
    their value. The slug never changes, because shared links filter by it."""

    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None


class CreateServiceRequest(ApiSchema):
    location_id: UUID
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    description_en: str | None = None
    description_ar: str | None = None
    #: One of `GET /discovery/categories`. Tenants pick from that list; they
    #: cannot add to it.
    category_id: UUID | None = None
    duration_minutes: int = Field(gt=0)
    price: Decimal = Field(ge=0)
    currency: str = Field(default="SAR", min_length=3, max_length=3)


class UpdateServiceRequest(_PartialUpdate):
    """`null` clears the category or a description."""

    clearable = frozenset({"category_id", "description_en", "description_ar"})

    name_en: str | None = Field(default=None, min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, min_length=1, max_length=255)
    description_en: str | None = None
    description_ar: str | None = None
    category_id: UUID | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    description_en: str | None
    description_ar: str | None
    category_id: UUID | None
    category: CategoryOut | None
    duration_minutes: int
    price: Decimal
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateProviderRequest(ApiSchema):
    location_id: UUID
    name_en: str = Field(min_length=1, max_length=255)
    name_ar: str = Field(min_length=1, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    title_ar: str | None = Field(default=None, max_length=255)


class UpdateProviderRequest(_PartialUpdate):
    """`null` clears a title."""

    clearable = frozenset({"title_en", "title_ar"})

    name_en: str | None = Field(default=None, min_length=1, max_length=255)
    name_ar: str | None = Field(default=None, min_length=1, max_length=255)
    title_en: str | None = Field(default=None, max_length=255)
    title_ar: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class ProviderOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    location_id: UUID
    name_en: str
    name_ar: str
    title_en: str | None
    title_ar: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AssignServiceRequest(ApiSchema):
    service_id: UUID
