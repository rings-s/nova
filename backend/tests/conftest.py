"""Pytest fixtures for the backend test suite.

Test DB strategy: a real Postgres database (schema uses UUID PKs, TIMESTAMPTZ,
and will grow enums/JSONB — SQLite would fake too much of that). Migrations
are applied once per session via Alembic (the same migrations that run in
production), and each test gets an isolated outer transaction that is rolled
back afterward, so tests never see each other's data without paying for a
drop/recreate per test. See docs/decisions/0005-test-database-strategy.md.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.command import upgrade
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

# Point Settings.database_url at the test database before anything imports
# app.core.config — get_settings() is process-wide cached, so this must run
# before the first call anywhere in the import graph below.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nova:nova@localhost:5432/nova_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.deps import get_db_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.tenants.models import Branch, Tenant  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    upgrade(config, "head")


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    # Function-scoped (not session-scoped) so the engine/connection are always
    # used from the same event loop pytest-asyncio creates for this test —
    # avoids "attached to a different loop" errors from a shared engine.
    engine: AsyncEngine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection, connection.begin() as outer_transaction:
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        yield session
        await session.close()
        await outer_transaction.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def app(db_session: AsyncSession) -> AsyncIterator[FastAPI]:
    application = create_app()

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = _override_get_db_session
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
async def branch_factory(db_session: AsyncSession):
    async def _create(tenant: Tenant, **overrides: object) -> Branch:
        defaults = {
            "tenant_id": tenant.id,
            "name_en": "Main Branch",
            "name_ar": "الفرع الرئيسي",
            "slug": f"main-{uuid4().hex[:8]}",
            "phone": "+966500000001",
            "timezone": "Asia/Riyadh",
        }
        defaults.update(overrides)
        branch = Branch(**defaults)
        db_session.add(branch)
        await db_session.flush()
        return branch

    return _create
