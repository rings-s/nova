"""HTTP middleware: correlation ids and access logging."""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.context import (
    CORRELATION_ID_HEADER,
    new_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger("nova.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Assigns every request a correlation id and echoes it back.

    Honours an inbound `X-Correlation-ID` so a trace started by the frontend or
    an upstream gateway continues through this service instead of restarting.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or new_correlation_id()
        set_correlation_id(correlation_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log before re-raising: the exception handler will build the
            # response, but the timing and route belong in the access log.
            duration_ms = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[CORRELATION_ID_HEADER] = correlation_id

        logger.info(
            "request_completed",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
