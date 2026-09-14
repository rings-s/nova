from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            str(settings.database_url),
            # Detects connections dropped by the database or a proxy, instead
            # of failing the first query on a stale one.
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            # Recycle below typical idle-connection timeouts so we close them
            # before the network does.
            pool_recycle=1800,
            connect_args={
                # Server-side cap: a runaway query is killed rather than
                # holding a pooled connection indefinitely.
                "server_settings": {
                    "statement_timeout": str(settings.db_statement_timeout_ms),
                    "application_name": "nova-api",
                },
            },
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def set_tenant_scope(session: AsyncSession, tenant_id: "UUID | None") -> None:
    """Binds the connection's RLS variable for this transaction.

    `SET LOCAL` is scoped to the transaction, so the value cannot leak to the
    next request that borrows this pooled connection — a plain `SET` would be a
    cross-tenant leak waiting to happen.

    Called by `get_tenant_context` once the tenant is authorized. Without it,
    RLS policies match nothing and queries return empty, which is the correct
    failure direction.
    """
    if tenant_id is None:
        return
    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


async def bypass_tenant_scope(session: AsyncSession) -> None:
    """Lets a transaction read across tenants.

    For the outbox dispatcher and admin/maintenance jobs only. Never call this
    on a request path — it disables the database-level isolation guarantee.
    """
    await session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))


async def set_discovery_scope(session: AsyncSession) -> None:
    """Opens the connection's read-only window onto published listings.

    The marketplace is the one request path with no tenant: a customer
    searching for a salon has not chosen one yet. `set_tenant_scope` therefore
    has nothing to set, and RLS — which fails closed — would return zero rows
    for every discovery query.

    This is deliberately NOT `bypass_tenant_scope`. That switch disables tenant
    isolation outright and is documented as never belonging on a request path.
    The `public_discovery` policies this enables (migration `d0e1f2a3b4c5`) are
    narrower in two ways that matter:

      - they are `FOR SELECT` only, so nothing on this path can write across
        tenants even by accident, and
      - they match only rows a business has published — active, listed, not
        deleted — so an unlisted salon stays invisible.

    `SET LOCAL` again, so the window closes with the transaction rather than
    leaking to the next request that borrows this pooled connection.
    """
    await session.execute(text("SELECT set_config('app.discovery_mode', 'on', true)"))
