"""The error envelope's retry contract. Pure — no database.

A client decides whether to try again from two places: `error.retryable` in
the body and, for a rate limit, the `Retry-After` header. Both were wrong for
429 — `retryable` came back false and the header was never sent, so the one
error that is retryable by definition told clients not to bother, and the
wait was only readable by parsing English out of `message`.
"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.error_handlers import register_exception_handlers
from app.core.exceptions import ConflictError, NotFoundError
from app.core.rate_limit import LOGIN_POLICY
from app.core.schemas import ErrorResponse
from app.core.throttling import RateLimitExceeded
from app.main import create_app


async def _response_to(exc: Exception) -> Response:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/boom")


async def test_a_rate_limit_says_when_to_retry() -> None:
    response = await _response_to(RateLimitExceeded(27, LOGIN_POLICY))

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "27"
    error = response.json()["error"]
    assert error["code"] == "rate_limit_exceeded"
    assert error["retryable"] is True


async def test_a_conflict_is_retryable_but_names_no_wait() -> None:
    """A lost race may succeed at another time, but there is no known delay."""
    response = await _response_to(ConflictError("That slot was just taken."))

    assert response.status_code == 409
    assert response.json()["error"]["retryable"] is True
    assert "Retry-After" not in response.headers


async def test_a_missing_resource_is_not_retryable() -> None:
    response = await _response_to(NotFoundError("Nothing here."))

    assert response.status_code == 404
    assert response.json()["error"]["retryable"] is False
    assert "Retry-After" not in response.headers


async def test_every_error_body_matches_the_published_schema() -> None:
    for exc in (RateLimitExceeded(5, LOGIN_POLICY), ConflictError("x"), NotFoundError("y")):
        response = await _response_to(exc)
        ErrorResponse.model_validate(response.json())


def test_the_openapi_document_describes_the_envelope_actually_sent() -> None:
    """/docs is where a client author reads the contract (docs/00).

    Unless told otherwise, FastAPI documents every 422 as its own
    `HTTPValidationError`, a `{"detail": [...]}` shape this API never returns,
    and documents no other error at all.
    """
    spec = create_app().openapi()

    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert "correlation_id" in spec["components"]["schemas"]["ErrorDetail"]["properties"]

    envelope = {"$ref": "#/components/schemas/ErrorResponse"}
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            for status in ("4XX", "5XX"):
                content = operation["responses"].get(status, {}).get("content", {})
                assert content.get("application/json", {}).get("schema") == envelope, (
                    f"{method.upper()} {path} does not document {status} as ErrorResponse"
                )
