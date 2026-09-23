from uuid import UUID

from app.core.exceptions import ConflictError, DomainError, NotFoundError, ValidationDomainError


class BusinessNotFoundError(NotFoundError):
    code = "business_not_found"

    def __init__(self, business_id: object) -> None:
        super().__init__(f"Business '{business_id}' was not found.")


class LocationNotFoundError(NotFoundError):
    code = "location_not_found"

    def __init__(self, location_id: object) -> None:
        super().__init__(f"Location '{location_id}' was not found.")


class ServiceNotFoundError(NotFoundError):
    code = "service_not_found"

    def __init__(self, service_id: object) -> None:
        super().__init__(f"Service '{service_id}' was not found.")


class ProviderNotFoundError(NotFoundError):
    code = "provider_not_found"

    def __init__(self, provider_id: object) -> None:
        super().__init__(f"Provider '{provider_id}' was not found.")


class DuplicateSlugError(ConflictError):
    code = "duplicate_slug"

    def __init__(self, slug: str) -> None:
        super().__init__(f"Slug '{slug}' is already in use.")


class ProviderNotQualifiedError(ValidationDomainError):
    """Raised when a provider is assigned work they are not qualified for."""

    code = "provider_not_qualified"

    def __init__(self, provider_id: object, service_id: object) -> None:
        super().__init__(
            f"Provider '{provider_id}' is not qualified to perform service '{service_id}'."
        )


class CrossLocationAssignmentError(ValidationDomainError):
    code = "cross_location_assignment"

    def __init__(self) -> None:
        super().__init__("A provider can only be assigned to services at their own location.")


class PhotoNotFoundError(NotFoundError):
    code = "photo_not_found"

    def __init__(self, photo_id: UUID) -> None:
        super().__init__(f"Photo {photo_id} not found.")


class GalleryFullError(ConflictError):
    code = "gallery_full"

    def __init__(self, limit: int) -> None:
        super().__init__(f"A gallery holds at most {limit} photos. Remove one first.")


class PhotoTooLargeError(DomainError):
    status_code = 413
    code = "photo_too_large"

    def __init__(self, limit: int) -> None:
        super().__init__(f"Photos can be at most {limit // (1024 * 1024)} MB.")
