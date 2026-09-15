"""booking · DOMAIN layer — module errors.

The transition errors live in `domain.py` beside the state machine they guard
(`InvalidBookingTransition`, `CancellationTooLate`); this file holds the rest.
"""

from app.core.exceptions import ConflictError, NotFoundError, ValidationDomainError


class BookingNotFoundError(NotFoundError):
    code = "booking_not_found"

    def __init__(self, booking_id: object) -> None:
        super().__init__(f"Booking '{booking_id}' was not found.")


class SlotUnavailableError(ConflictError):
    """The requested time collides with an existing booking for that provider."""

    code = "slot_unavailable"

    def __init__(self) -> None:
        super().__init__("That time is no longer available for this provider.")


class ProviderNotQualifiedError(ValidationDomainError):
    code = "provider_not_qualified"

    def __init__(self, provider_id: object, service_id: object) -> None:
        super().__init__(
            f"Provider '{provider_id}' is not qualified to perform service '{service_id}'."
        )


class ProviderLocationMismatchError(ValidationDomainError):
    code = "provider_location_mismatch"

    def __init__(self) -> None:
        super().__init__("The provider does not work at the requested location.")


class SlotNotOfferedError(ValidationDomainError):
    """The signed `slot_id` does not match the slot being booked.

    docs/07 section 5: agents may query availability but must not invent slots.
    A mismatch means the caller either tampered with the id or assembled a slot
    the server never generated — both are refusals, not retries.
    """

    code = "slot_not_offered"

    def __init__(self) -> None:
        super().__init__("That slot was not offered by the server. Re-check availability.")


class HoldNotFoundError(NotFoundError):
    code = "hold_not_found"

    def __init__(self) -> None:
        super().__init__("That slot hold does not exist.")


class HoldExpiredError(ConflictError):
    code = "hold_expired"

    def __init__(self) -> None:
        super().__init__("That slot hold has expired. Re-check availability and try again.")


class HoldLimitReachedError(ConflictError):
    """A customer already holds as many slots at this tenant as one may.

    A hold blocks a provider's time for everyone else, so without a cap one
    account could keep a salon unbookable by re-holding each slot as it expired.
    """

    code = "hold_limit_reached"

    def __init__(self, limit: int) -> None:
        super().__init__(f"You already hold {limit} slots here. Book or release one first.")


class HorizonTooLargeError(ValidationDomainError):
    """Guards against a request that would generate millions of slots."""

    code = "availability_horizon_too_large"

    def __init__(self, max_days: int) -> None:
        super().__init__(f"Availability can be requested at most {max_days} days at a time.")
