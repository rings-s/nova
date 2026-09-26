from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.context import CORRELATION_ID_HEADER
from app.core.deps import get_db_session
from app.core.error_handlers import ERROR_RESPONSES, register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.db.session import enforce_rls_role, get_engine
from app.modules.registry import routers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    await enforce_rls_role(get_engine(), env=get_settings().env)
    yield
    await get_engine().dispose()


_DOCS = "https://github.com/rings-s/nova/blob/main/docs"

#: The front page of `/docs`: what every endpoint below has in common.
API_DESCRIPTION = f"""
Booking, walk-in queues, payments and messaging for salons and spas, and the public marketplace
that lists them. Every path below is under `/api/v1`.

## Authentication

1. `POST /api/v1/auth/login` with an email and password returns an `access_token` (valid for
   15 minutes) and a `refresh_token` (30 days). A browser sends `"refresh_cookie": true` to get
   the refresh token as an httpOnly cookie instead, which no page script can read.
2. Send the access token on every request: `Authorization: Bearer <access_token>`. In this page,
   click **Authorize** and paste the token alone.
3. When a request answers `401 unauthenticated`, call `POST /api/v1/auth/refresh` with the refresh
   token (or with none, to use the cookie), then retry once.

Routes without a lock icon need no token: sign-up, sign-in, the marketplace under
`/api/v1/discovery`, and the payment gateway's webhook.

## Tenants

A tenant is one salon business. Its data lives under `/api/v1/tenants/{{tenant_id}}/...`, and the
tenant is only ever read from that path. Staff reach the tenants they work at, and what they may do
there depends on their role (`GET /api/v1/tenants/{{tenant_id}}/memberships/me` lists it). A
customer reaches any tenant, but only their own bookings, payments and queue places in it.

## Errors

Every error has one shape, `{{"error": {{"code", "message", "field", "retryable",
"correlation_id"}}}}`. Branch on `code`.
[Every code, and what to do about it]({_DOCS}/15-API-Error-Codes.md).

## Conventions

- **Lists** return `{{"items": [...], "total": ...}}` and take `limit` (1-100, default 20) and
  `offset`.
- **Retries.** Send an `Idempotency-Key` header on a create request you might retry, such as a
  booking or a payment. A retry with the same key and body replays the first response instead of
  creating a second record. Keys last 24 hours.
- **Rate limits.** A `429 rate_limit_exceeded` carries a `Retry-After` header in seconds.
- **Money** is a decimal string with a currency, SAR by default. **Times** are ISO 8601 in UTC.
- **Bilingual text** comes in pairs: `name_en` and `name_ar`.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    # Off outside local and test unless API_DOCS_ENABLED says otherwise.
    docs = settings.serve_api_docs
    app = FastAPI(
        title="NOVA API",
        version="0.1.0",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        # docs/07 section 2: every error is `{"error": {...}}`, and /docs says so.
        responses=ERROR_RESPONSES,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    # A wildcard origin with credentials enabled lets any site make
    # authenticated requests on a logged-in user's behalf. Browsers reject the
    # combination, so this fails loudly at startup rather than mysteriously at
    # runtime.
    if "*" in settings.cors_origins:
        raise RuntimeError(
            "cors_origins cannot be '*' while allow_credentials is enabled. "
            "List the exact frontend origins instead."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # A browser only lets page script read a short safelist of response
        # headers cross-origin, and neither of these is on it. Without this the
        # PWA cannot honour Retry-After on a 429, or quote the correlation id
        # of a failed request, however correctly the server sends them.
        expose_headers=["Retry-After", CORRELATION_ID_HEADER],
    )
    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)

    for router in routers:
        app.include_router(router, prefix="/api/v1")

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        """Liveness: is the process up? Deliberately touches nothing."""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["ops"])
    async def health_ready(
        session: AsyncSession = Depends(get_db_session),
    ) -> dict[str, str]:
        """Readiness: can we actually serve traffic?

        Separate from liveness on purpose — an orchestrator should restart a
        dead process but only stop routing to one that cannot reach its
        database. Conflating them turns a brief database blip into a restart
        loop.
        """
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
