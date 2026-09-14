"""Translates exceptions into the API's single error contract.

Three problems this replaces:

  1. Only `DomainError` was handled. Anything else — a bug, a driver error —
     reached Starlette's default handler and returned an unstructured 500,
     with the traceback exposed whenever debug was on.
  2. `IntegrityError` was unhandled, so every database constraint surfaced as a
     500. The `EXCLUDE` constraint that prevents double-booking would have told
     the customer "internal server error" instead of "that slot is taken".
  3. The response shape was `{"code", "message"}`, but the published contract in
     docs/07 and `core.schemas.ErrorResponse` declares `{"error": {...}}`.
     Clients written against the docs would have broken.

Every error response now carries the correlation id, so a user can quote it and
you can find the exact request in the logs.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import CORRELATION_ID_HEADER, get_correlation_id
from app.core.exceptions import DomainError
from app.core.schemas import ErrorResponse
from app.core.throttling import RateLimitExceeded
from app.db.errors import translate_integrity_error

logger = logging.getLogger("nova.errors")

#: Declared on the app so every operation's OpenAPI entry describes the
#: envelope below. Without it FastAPI advertises its own `HTTPValidationError`
#: (`{"detail": [...]}`) for 422, a shape this API never returns, and nothing
#: at all for any other error.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    "4XX": {"model": ErrorResponse, "description": "Client error, in the error envelope."},
    "5XX": {"model": ErrorResponse, "description": "Server error, in the error envelope."},
}


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
    retryable: bool = False,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Builds the one error envelope, per docs/07 section 2."""
    correlation_id = get_correlation_id()
    detail: dict[str, object] = {
        "code": code,
        "message": message,
        "field": field,
        "retryable": retryable,
    }
    if correlation_id:
        detail["correlation_id"] = correlation_id
    body: dict[str, object] = {"error": detail}

    response_headers = dict(headers or {})
    if correlation_id:
        response_headers[CORRELATION_ID_HEADER] = correlation_id
    return JSONResponse(status_code=status_code, content=body, headers=response_headers or None)


async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    # Expected business outcomes, not faults — logged at INFO, not ERROR, so
    # they do not pollute the signal an on-call alert depends on.
    logger.info("domain_error", extra={"error_code": exc.code, "status": exc.status_code})

    # A 429 used to leave here with `retryable: false` and no Retry-After, so
    # the one error that is retryable by definition told clients not to retry,
    # and the wait existed only as prose inside `message`. The limiter already
    # knows the number; RFC 9110 section 10.2.3 says where it goes.
    headers = None
    if isinstance(exc, RateLimitExceeded):
        headers = {"Retry-After": str(exc.retry_after_seconds)}

    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        # A 409 means the same thing whether the service noticed the conflict
        # or the database constraint did, so it must carry the same retry
        # contract either way. Marking only the IntegrityError path retryable
        # made "that slot was just taken" look retryable or not depending on
        # which layer happened to catch the race.
        retryable=exc.status_code in (409, 429),
        headers=headers,
    )


async def _handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    domain_error = translate_integrity_error(exc)
    logger.warning(
        "integrity_error",
        extra={"error_code": domain_error.code, "status": domain_error.status_code},
        exc_info=exc,
    )
    return _error_response(
        status_code=domain_error.status_code,
        code=domain_error.code,
        message=domain_error.message,
        # A losing race on an exclusion constraint may well succeed at a
        # different time, so tell the client it is worth retrying.
        retryable=domain_error.status_code == 409,
    )


async def _handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Reshapes FastAPI's default 422 into our envelope."""
    first = exc.errors()[0] if exc.errors() else {}
    location = [str(p) for p in first.get("loc", []) if p not in ("body", "query", "path")]
    return _error_response(
        status_code=422,
        code="validation_error",
        message=first.get("msg", "Request validation failed."),
        field=".".join(location) or None,
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(
        status_code=exc.status_code,
        code=f"http_{exc.status_code}",
        message=str(exc.detail),
    )


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all. Logs everything, tells the client nothing.

    The traceback goes to the logs with the correlation id attached; the client
    gets a stable code and that id. Internal details — table names, driver
    messages, file paths — never cross the boundary.
    """
    logger.exception(
        "unhandled_exception",
        extra={"http_path": request.url.path, "http_method": request.method},
    )
    return _error_response(
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred. Quote the correlation id when reporting this.",
        retryable=True,
    )


def register_exception_handlers(app: FastAPI) -> None:
    # Starlette types every handler as taking a bare `Exception`, so a handler
    # narrowed to the exception it actually handles never matches. The
    # narrowing is the point — Starlette dispatches by the registered class —
    # so these are suppressed rather than widened back to `Exception`.
    app.add_exception_handler(DomainError, _handle_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, _handle_integrity_error)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        _handle_request_validation_error,  # type: ignore[arg-type]
    )
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    # Registered last and broadest — nothing escapes to the default handler.
    app.add_exception_handler(Exception, _handle_unexpected_error)
