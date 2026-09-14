"""Per-request context propagated without threading it through every call.

A correlation id lets you take one id from a client error report and pull every
log line for that request — across the router, service, repository, and worker.
Without it, a 500 in production is a needle in a haystack.

`ContextVar` is the async-safe equivalent of thread-local: each request task
gets its own value, and concurrent requests cannot see each other's.
"""

from contextvars import ContextVar
from uuid import UUID, uuid4

CORRELATION_ID_HEADER = "X-Correlation-ID"

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_principal_id: ContextVar[str | None] = ContextVar("principal_id", default=None)


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def new_correlation_id() -> str:
    return str(uuid4())


def set_tenant_id(value: UUID | str | None) -> None:
    _tenant_id.set(str(value) if value is not None else None)


def get_tenant_id() -> str | None:
    return _tenant_id.get()


def set_principal_id(value: UUID | str | None) -> None:
    _principal_id.set(str(value) if value is not None else None)


def get_principal_id() -> str | None:
    return _principal_id.get()


def current_context() -> dict[str, str]:
    """The fields every log line and error response should carry."""
    context = {
        "correlation_id": get_correlation_id(),
        "tenant_id": get_tenant_id(),
        "principal_id": get_principal_id(),
    }
    return {k: v for k, v in context.items() if v is not None}
