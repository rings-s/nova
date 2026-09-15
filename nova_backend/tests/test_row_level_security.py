"""Row-level security, checked as the role the deployed app connects as.

Needs Postgres. `db_session` runs as `nova_app` (see conftest.py), so each query
below returns what the policies allow and nothing more.

Until migration `e1f2a3b4c5d6` the app and this suite connected as a superuser,
which Postgres exempts from RLS even under FORCE. No test could see a policy,
and the first test here is the one that would have said so.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import (
    APP_DB_ROLE,
    bypass_tenant_scope,
    role_exempt_from_rls,
    set_tenant_scope,
)
from app.modules.catalog.models import Business

OwnerRole = Callable[[], AbstractAsyncContextManager[None]]

#: Tables that carry `tenant_id` and deliberately have no policy.
UNPOLICED_TENANT_TABLES = frozenset(
    {
        # The outbox: written inside the publishing request's own transaction,
        # read only by the dispatcher, which crosses tenants by design.
        "domain_events",
        # Replay records. Scoped in code instead: every lookup matches key,
        # endpoint, tenant and principal (`core/idempotency.py`).
        "idempotency_keys",
        # Recorded by the gateway webhook before it knows which tenant it is for.
        "webhook_events",
    }
)


async def _visible(session: AsyncSession, business_id: UUID) -> bool:
    count = await session.scalar(
        text("SELECT count(*) FROM businesses WHERE id = :id"), {"id": business_id}
    )
    return count == 1


async def test_the_suite_runs_as_the_app_role_and_rls_applies_to_it(db_session: AsyncSession):
    assert await db_session.scalar(text("SELECT current_user")) == APP_DB_ROLE
    assert await role_exempt_from_rls(db_session) is None


async def test_the_role_check_names_an_exempt_role(db_session: AsyncSession, as_owner: OwnerRole):
    # The owner here is POSTGRES_USER, a superuser: the role the app used to be.
    async with as_owner():
        assert await role_exempt_from_rls(db_session) is not None


async def test_every_tenant_table_is_under_a_forced_tenant_policy(db_session: AsyncSession):
    rows = await db_session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a
              ON a.attrelid = c.oid AND a.attname = 'tenant_id' AND NOT a.attisdropped
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND NOT (
                c.relrowsecurity
                AND c.relforcerowsecurity
                AND EXISTS (
                  SELECT FROM pg_policy p
                  WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation'
                )
              )
            """
        )
    )
    # Autogenerate emits no RLS, so a new tenant table fails here until its
    # migration adds the policy by hand.
    assert set(rows.scalars()) == UNPOLICED_TENANT_TABLES


async def test_the_app_role_holds_dml_on_every_table_but_migration_state(
    db_session: AsyncSession,
):
    rows = await db_session.execute(
        text(
            """
            SELECT DISTINCT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']) AS p(privilege)
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
              AND NOT has_table_privilege(current_user, c.oid, p.privilege)
            """
        )
    )
    # Default privileges cover a later migration's tables; this catches one
    # created by some other owner.
    assert set(rows.scalars()) == {"alembic_version"}
    # A privilege list means "any of", so False here means none at all.
    assert not await db_session.scalar(
        text(
            "SELECT has_table_privilege("
            "current_user, 'alembic_version', 'SELECT, INSERT, UPDATE, DELETE')"
        )
    )


async def test_an_unscoped_transaction_sees_no_tenant_rows(
    db_session: AsyncSession, tenant_factory, business_factory
):
    business = await business_factory(await tenant_factory())

    assert not await _visible(db_session, business.id)


async def test_a_tenant_scope_shows_that_tenant_and_no_other(
    db_session: AsyncSession, tenant_factory, business_factory
):
    mine = await business_factory(await tenant_factory())
    theirs = await business_factory(await tenant_factory())

    await set_tenant_scope(db_session, mine.tenant_id)

    assert await _visible(db_session, mine.id)
    assert not await _visible(db_session, theirs.id)


async def test_a_write_into_another_tenant_is_refused(db_session: AsyncSession, tenant_factory):
    mine = await tenant_factory()
    theirs = await tenant_factory()
    await set_tenant_scope(db_session, mine.id)

    with pytest.raises(DBAPIError, match="row-level security"):
        async with db_session.begin_nested():
            db_session.add(
                Business(
                    tenant_id=theirs.id,
                    name_en="Elsewhere",
                    name_ar="مكان آخر",
                    slug=f"elsewhere-{uuid4().hex[:8]}",
                )
            )
            await db_session.flush()


async def test_scoping_to_a_tenant_closes_an_earlier_bypass(
    db_session: AsyncSession, tenant_factory, business_factory
):
    """The payment webhook and the outbox bypass to find a tenant, then scope to it."""
    mine = await business_factory(await tenant_factory())
    theirs = await business_factory(await tenant_factory())

    await bypass_tenant_scope(db_session)
    assert await _visible(db_session, theirs.id)

    await set_tenant_scope(db_session, mine.tenant_id)
    assert not await _visible(db_session, theirs.id)
