"""Translates PostgreSQL constraint violations into domain errors.

Without this, every constraint the database enforces surfaces as a 500. That is
worst exactly where the constraint matters most: the `EXCLUDE` constraint that
guarantees no double-booking would tell the customer "internal server error"
rather than "that slot was just taken".

The database is the last line of defence for concurrent writes — the service's
check-then-act read cannot close the race. So a constraint firing is an
*expected* outcome under concurrency, not a bug, and deserves a proper 4xx.
"""

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, DomainError, ValidationDomainError

# PostgreSQL SQLSTATE codes.
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_CHECK_VIOLATION = "23514"
_EXCLUSION_VIOLATION = "23P01"

#: Constraint name -> the domain error it represents. Anything not listed gets
#: a generic-but-correct fallback for its SQLSTATE class.
_CONSTRAINT_ERRORS: dict[str, tuple[type[DomainError], str, str]] = {
    "ex_bookings_no_provider_overlap": (
        ConflictError,
        "slot_unavailable",
        "That time is no longer available for this provider.",
    ),
    "uq_locations_tenant_id_slug": (
        ConflictError,
        "duplicate_slug",
        "A location with that name already exists for this tenant.",
    ),
    "ck_bookings_end_after_start": (
        ValidationDomainError,
        "invalid_time_range",
        "Booking end time must be after its start time.",
    ),
}


def _constraint_name(exc: IntegrityError) -> str | None:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None)


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def translate_integrity_error(exc: IntegrityError) -> DomainError:
    """Maps an IntegrityError to the domain error it actually represents."""
    constraint = _constraint_name(exc)

    if constraint and constraint in _CONSTRAINT_ERRORS:
        error_cls, code, message = _CONSTRAINT_ERRORS[constraint]
        error = error_cls(message)
        error.code = code
        return error

    sqlstate = _sqlstate(exc)

    if sqlstate == _EXCLUSION_VIOLATION:
        error = ConflictError("That time slot is no longer available.")
        error.code = "slot_unavailable"
        return error

    if sqlstate == _UNIQUE_VIOLATION:
        error = ConflictError("That value is already in use.")
        error.code = "duplicate_value"
        return error

    if sqlstate == _FOREIGN_KEY_VIOLATION:
        # A referenced row does not exist — e.g. creating a business under a
        # tenant id that was never created. 422, not 500.
        error = ValidationDomainError("A referenced record does not exist.")
        error.code = "invalid_reference"
        return error

    if sqlstate == _CHECK_VIOLATION:
        error = ValidationDomainError("A value violates a database constraint.")
        error.code = "constraint_violation"
        return error

    # Unrecognised: surface as a conflict rather than a 500, but keep the
    # constraint name out of the client-facing message.
    error = ConflictError("The request conflicts with existing data.")
    error.code = "integrity_conflict"
    return error
