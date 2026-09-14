"""analytics · module errors."""

from app.core.exceptions import NotFoundError, ValidationDomainError


class ReportWindowError(ValidationDomainError):
    code = "report_window_invalid"


class ReportTooLargeError(ValidationDomainError):
    """Refused rather than truncated: a report over part of a window is wrong
    in a way nobody reading it could see."""

    code = "report_too_large"

    def __init__(self, what: str, limit: int) -> None:
        super().__init__(
            f"More than {limit} {what} fall inside this window. Choose a shorter period."
        )


class InsufficientDataError(ValidationDomainError):
    code = "insufficient_data"


class UnknownChartError(NotFoundError):
    code = "chart_not_found"

    def __init__(self, chart_id: str) -> None:
        super().__init__(f"There is no chart named '{chart_id}'.")


__all__ = [
    "InsufficientDataError",
    "ReportTooLargeError",
    "ReportWindowError",
    "UnknownChartError",
]
