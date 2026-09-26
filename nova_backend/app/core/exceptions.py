class DomainError(Exception):
    """Base class for all module-level domain errors.

    Subclasses set `status_code` and a machine-readable `code` so routers never
    have to translate business exceptions into HTTP responses themselves. This
    module has no FastAPI import so domain/service code can raise these without
    depending on the web framework — see app/core/error_handlers.py for the
    FastAPI-side translation into responses.
    """

    status_code: int = 400
    code: str = "domain_error"
    #: Whether asking again may succeed. A 409 and a 429 always are; any other
    #: error opts in here (an unreachable payment provider, say).
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class ValidationDomainError(DomainError):
    status_code = 422
    code = "validation_error"
