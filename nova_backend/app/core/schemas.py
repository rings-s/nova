"""Base API schema types, per docs/07-Pydantic-Schemas-and-API-Contracts.md section 2.

These are API boundary models. They are not the domain model and not the
database model.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ApiSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class Page(ApiSchema, Generic[T]):
    items: list[T]
    total: int | None = None
    next_cursor: str | None = None


class ErrorDetail(ApiSchema):
    code: str
    message: str
    field: str | None = None
    retryable: bool = False
    #: Echoes the `X-Correlation-ID` response header so a user can quote a
    #: failed request (ADR-0006). Omitted when no correlation id is bound.
    correlation_id: str | None = None


class ErrorResponse(ApiSchema):
    error: ErrorDetail
