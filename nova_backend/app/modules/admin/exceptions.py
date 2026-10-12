"""admin · DOMAIN layer — module errors.

Each reuses a generic code from docs/15 (`not_found`, `validation_error`,
`conflict`): the console is for NOVA's own staff, and nothing a client does
depends on telling these apart from the generic case.
"""

from app.core.exceptions import ConflictError, NotFoundError, ValidationDomainError


class AdminTableNotFoundError(NotFoundError):
    def __init__(self, table: str) -> None:
        super().__init__(f"There is no table named '{table}'.")


class AdminRowNotFoundError(NotFoundError):
    def __init__(self, table: str, row_id: str) -> None:
        super().__init__(f"No row '{row_id}' in '{table}'.")


class AdminFilterError(ValidationDomainError):
    def __init__(self, column: str, value: str) -> None:
        super().__init__(f"Can't filter or sort '{column}' by '{value}'.")


class AdminActionNotFoundError(NotFoundError):
    def __init__(self, table: str, action: str) -> None:
        super().__init__(f"'{action}' is not an action on '{table}'.")


class AdminActionRefusedError(ConflictError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
