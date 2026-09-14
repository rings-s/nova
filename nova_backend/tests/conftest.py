"""Pytest fixtures for the backend test suite.

Test DB strategy: a real Postgres database (schema uses UUID PKs, TIMESTAMPTZ,
and will grow enums/JSONB — SQLite would fake too much of that). Migrations
are applied once per session via Alembic (the same migrations that run in
production), and each test gets an isolated outer transaction that is rolled
back afterward, so tests never see each other's data without paying for a
drop/recreate per test. See docs/decisions/0005-test-database-strategy.md.

Every test runs as `nova_app`, the role the deployed API connects as, so
row-level security applies exactly as it does in production. See `db_session`.
"""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.command import upgrade
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# Point Settings.database_url at the test database before anything imports
# app.core.config — get_settings() is process-wide cached, so this must run
# before the first call anywhere in the import graph below.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nova:nova@localhost:5432/nova_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# The same for migrations. Inside the compose stack MIGRATION_DATABASE_URL names
# the development database and alembic/env.py prefers it, so left alone,
# `_apply_migrations` would migrate `nova` instead of `nova_test`.
os.environ["MIGRATION_DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("ENV", "test")
# Settings requires these, and a test run should not need real ones. Defaulted
# here rather than in CI so `pytest` works from a clean checkout with nothing
# but a database — the suite is self-contained or it is not reproducible.
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-not-used-outside-tests")

from app.core.deps import get_db_session  # noqa: E402
from app.core.security import Principal, PrincipalKind, get_principal  # noqa: E402
from app.db.session import APP_DB_ROLE  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.ai_agents.dependencies import (  # noqa: E402
    get_agent_transaction,
    get_conversation_store,
)
from app.modules.ai_agents.history import InMemoryConversationStore  # noqa: E402
from app.modules.catalog.models import (  # noqa: E402
    Business,
    Location,
    Provider,
    ProviderService,
    Service,
)
from app.modules.identity.models import Customer, Tenant  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def _apply_migrations() -> None:
    """Applies migrations once per session.

    Deliberately NOT autouse. Domain tests (`test_domain.py` in every module)
    are pure Python and must run with no database at all — making this autouse
    would force Postgres on the whole suite and quietly undermine the rule that
    domain.py has no infrastructure dependency.

    Only `db_session` depends on this, so only tests that actually touch the
    database pay for it.
    """
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    upgrade(config, "head")


@pytest_asyncio.fixture
async def db_session(_apply_migrations: None) -> AsyncIterator[AsyncSession]:
    # Function-scoped (not session-scoped) so the engine/connection are always
    # used from the same event loop pytest-asyncio creates for this test —
    # avoids "attached to a different loop" errors from a shared engine.
    engine: AsyncEngine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection, connection.begin() as outer_transaction:
        # The whole test runs as the role the deployed app connects as, so every
        # RLS policy applies as it does in production. The connection itself
        # logs in as the schema owner: that is what lets `SET ROLE` go without a
        # password, and what `as_owner` steps back out to.
        await connection.execute(text(f"SET LOCAL ROLE {APP_DB_ROLE}"))
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        yield session
        await session.close()
        await outer_transaction.rollback()
    await engine.dispose()


@asynccontextmanager
async def _owner_role(session: AsyncSession) -> AsyncIterator[None]:
    """Runs a block as the schema owner, which RLS does not restrict.

    For building fixtures only. A test seeds several tenants at once, which no
    request ever does, so it writes the way a seed script would. Nothing under
    test runs inside this.
    """
    await session.execute(text("SET LOCAL ROLE NONE"))
    try:
        yield
    finally:
        await session.execute(text(f"SET LOCAL ROLE {APP_DB_ROLE}"))


@pytest.fixture
def as_owner(db_session: AsyncSession) -> Callable[[], AbstractAsyncContextManager[None]]:
    """`async with as_owner():` seeds rows outside RLS. See `_owner_role`."""
    return lambda: _owner_role(db_session)


@pytest.fixture
def principal() -> Principal:
    """The caller for API tests.

    A SERVICE principal, so it is not scoped to a single tenant and test
    fixtures can create tenants freely. Tests that care about authorization
    override this with a narrower principal — see
    `tests/test_security.py` and `tests/modules/booking/test_authorization.py`.
    """
    return Principal(
        subject_id=uuid4(),
        kind=PrincipalKind.SERVICE,
        roles=frozenset({"test"}),
    )


@pytest_asyncio.fixture
async def app(db_session: AsyncSession, principal: Principal) -> AsyncIterator[FastAPI]:
    application = create_app()

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _override_get_principal() -> Principal:
        return principal

    @asynccontextmanager
    async def _savepoint() -> AsyncIterator[AsyncSession]:
        async with db_session.begin_nested():
            yield db_session

    application.dependency_overrides[get_db_session] = _override_get_db_session
    # Authentication itself is exercised in tests/test_security.py against the
    # real token path; API tests override it so they can focus on behaviour.
    application.dependency_overrides[get_principal] = _override_get_principal
    # An agent's tool calls each open a transaction of their own, which on the
    # pool would see none of this test's uncommitted rows. A savepoint keeps
    # the same commit-or-roll-back boundary inside the test's transaction.
    application.dependency_overrides[get_agent_transaction] = lambda: _savepoint
    # Conversation memory in this process, one store for the test, so turns in
    # the same test share it and no test reads another's.
    memory = InMemoryConversationStore()
    application.dependency_overrides[get_conversation_store] = lambda: memory
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def tenant_factory(db_session: AsyncSession):
    async def _create(**overrides: object) -> Tenant:
        defaults = {
            "name_en": "Test Salon",
            "name_ar": "صالون تجريبي",
            "slug": f"test-salon-{uuid4().hex[:8]}",
            "phone": "+966500000000",
            "default_currency": "SAR",
        }
        defaults.update(overrides)
        tenant = Tenant(**defaults)
        db_session.add(tenant)
        await db_session.flush()
        return tenant

    return _create


@pytest_asyncio.fixture
async def business_factory(db_session: AsyncSession):
    async def _create(tenant: Tenant, **overrides: object) -> Business:
        defaults = {
            "tenant_id": tenant.id,
            "name_en": "Test Salon",
            "name_ar": "صالون تجريبي",
            "slug": f"salon-{uuid4().hex[:8]}",
        }
        defaults.update(overrides)
        business = Business(**defaults)
        async with _owner_role(db_session):
            db_session.add(business)
            await db_session.flush()
        return business

    return _create


@pytest_asyncio.fixture
async def location_factory(db_session: AsyncSession):
    async def _create(business: Business, **overrides: object) -> Location:
        defaults = {
            "tenant_id": business.tenant_id,
            "business_id": business.id,
            "name_en": "Main Branch",
            "name_ar": "الفرع الرئيسي",
            "slug": f"main-{uuid4().hex[:8]}",
            "phone": "+966500000001",
            "timezone": "Asia/Riyadh",
        }
        defaults.update(overrides)
        location = Location(**defaults)
        async with _owner_role(db_session):
            db_session.add(location)
            await db_session.flush()
        return location

    return _create


@pytest_asyncio.fixture
async def service_factory(db_session: AsyncSession):
    async def _create(location: Location, **overrides: object) -> Service:
        defaults = {
            "tenant_id": location.tenant_id,
            "location_id": location.id,
            "name_en": "Haircut",
            "name_ar": "قص شعر",
            "duration_minutes": 60,
            "price": Decimal("150.00"),
            "currency": "SAR",
        }
        defaults.update(overrides)
        service = Service(**defaults)
        async with _owner_role(db_session):
            db_session.add(service)
            await db_session.flush()
        return service

    return _create


@pytest_asyncio.fixture
async def provider_factory(db_session: AsyncSession):
    async def _create(location: Location, **overrides: object) -> Provider:
        defaults = {
            "tenant_id": location.tenant_id,
            "location_id": location.id,
            "name_en": "Sara",
            "name_ar": "سارة",
        }
        defaults.update(overrides)
        provider = Provider(**defaults)
        async with _owner_role(db_session):
            db_session.add(provider)
            await db_session.flush()
        return provider

    return _create


@pytest_asyncio.fixture
async def qualify(db_session: AsyncSession):
    """Assigns a provider to a service.

    Booking refuses a provider who is not qualified, so almost every booking
    test needs this — hence a fixture rather than three lines repeated.
    """

    async def _assign(provider: Provider, service: Service) -> ProviderService:
        assignment = ProviderService(
            tenant_id=provider.tenant_id, provider_id=provider.id, service_id=service.id
        )
        async with _owner_role(db_session):
            db_session.add(assignment)
            await db_session.flush()
        return assignment

    return _assign


@pytest_asyncio.fixture
async def customer_factory(db_session: AsyncSession):
    async def _create(tenant: Tenant, **overrides: object) -> Customer:
        defaults = {
            "tenant_id": tenant.id,
            "full_name": "Noura",
            "phone": f"+96650{uuid4().int % 10_000_000:07d}",
            "preferred_language": "ar",
            "whatsapp_consent": True,
        }
        defaults.update(overrides)
        customer = Customer(**defaults)
        async with _owner_role(db_session):
            db_session.add(customer)
            await db_session.flush()
        return customer

    return _create
