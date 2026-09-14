import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: The role the API and worker connect as: NOSUPERUSER and NOBYPASSRLS, so every
#: policy applies to it. Migration `e1f2a3b4c5d6` creates it and grants it DML on
#: the schema. The owner runs migrations and nothing else.
APP_DB_ROLE = "nova_app"

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

    It also closes a bypass opened earlier in the transaction. The payment
    webhook and the outbox dispatcher both bypass to find the tenant and then
    scope to it; with the bypass still on, every policy would go on matching
    every tenant and the scope would be cosmetic.
    """
    if tenant_id is None:
        return
    await session.execute(
        text(
            "SELECT set_config('app.current_tenant_id', :tenant_id, true),"
            " set_config('app.bypass_rls', 'off', true)"
        ),
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


async def role_exempt_from_rls(connection: AsyncConnection | AsyncSession) -> str | None:
    """The connected role's name if Postgres exempts it from RLS, else None.

    A superuser or a BYPASSRLS role skips every policy, `FORCE` or not. Checked
    against `current_user`, so a `SET ROLE` counts.
    """
    result = await connection.execute(
        text(
            "SELECT rolname FROM pg_roles"
            " WHERE rolname = current_user AND (rolsuper OR rolbypassrls)"
        )
    )
    return result.scalar_one_or_none()


async def enforce_rls_role(engine: AsyncEngine, *, env: str) -> None:
    """Refuses to start a deployed process whose role would switch RLS off.

    The compose stack connected as the `postgres` image's POSTGRES_USER, a
    superuser, until migration `e1f2a3b4c5d6` — and every policy was off with
    nothing to say so. Local and test only warn, so an old volume still yields
    a working stack.

    An unreachable database is logged and let through: readiness reports it,
    and failing startup over it would turn a database blip into a restart loop.
    """
    try:
        async with engine.connect() as connection:
            role = await role_exempt_from_rls(connection)
    except (OSError, SQLAlchemyError):
        logger.warning("rls_role_check_skipped", exc_info=True)
        return

    if role is None:
        return
    if env in ("local", "test"):
        logger.warning("rls_bypassed_by_database_role", extra={"role": role})
        return
    raise RuntimeError(
        f"Connected to Postgres as '{role}', which bypasses row-level security. "
        f"Connect as '{APP_DB_ROLE}' and keep the schema owner for migrations "
        "(MIGRATION_DATABASE_URL)."
    )
