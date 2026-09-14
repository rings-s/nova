from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.error_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware
from app.db.session import get_engine
from app.modules.registry import routers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    yield
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NOVA API", version="0.1.0", lifespan=lifespan)

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
