"""The platform console: superusers browse every tenant, masked and audited,
and change things only through curated actions.

A superuser here signs in as a CUSTOMER principal, as in
`tests/modules/catalog/test_categories.py`: the flag is on the account, not a
salon role, so belonging to no salon must not matter.

The console opens `bypass_tenant_scope` with `SET LOCAL`, which lasts for the
test's outer transaction; nothing below relies on RLS after a console call.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.modules.admin.domain import MASK
from app.modules.admin.models import AdminAuditEntry
from app.modules.booking.domain import BookingSource, BookingStatus
from app.modules.booking.models import BookingRecord
from app.modules.identity.models import User

TABLES = "/api/v1/admin/tables"


async def _account(db_session: AsyncSession, *, is_superuser: bool = False) -> User:
    user = User(
        email=f"user-{uuid4().hex[:8]}@example.com",
        full_name="Someone",
        password_hash="argon2-not-a-real-hash",
        is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _sign_in(app: FastAPI, user: User) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=user.id, kind=PrincipalKind.CUSTOMER
    )


async def _audit(db_session: AsyncSession, actor: User) -> list[AdminAuditEntry]:
    rows = await db_session.scalars(
        select(AdminAuditEntry)
        .where(AdminAuditEntry.actor_id == actor.id)
        .order_by(AdminAuditEntry.occurred_at, AdminAuditEntry.id)
    )
    return list(rows)


async def test_an_account_that_is_not_a_superuser_is_refused(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    _sign_in(app, await _account(db_session))
    for path in (TABLES, f"{TABLES}/users", f"{TABLES}/users/rows"):
        response = await client.get(path)
        assert response.status_code == 403, (path, response.text)


async def test_the_console_lists_every_table_and_describes_one(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    _sign_in(app, await _account(db_session, is_superuser=True))

    tables = await client.get(TABLES)
    assert tables.status_code == 200, tables.text
    names = {table["name"]: table["group"] for table in tables.json()}
    assert names["bookings"] == "booking"
    assert names["users"] == "identity"
    assert names["customer_business_first_bookings"] == "billing"
    assert "admin_audit_log" in names

    first_bookings = (
        await client.get(f"{TABLES}/customer_business_first_bookings")
    ).json()
    assert first_bookings["group"] == "billing"
    assert {
        column["name"] for column in first_bookings["columns"]
    } >= {"business_id", "customer_id", "booking_id", "first_completed_at"}

    users = (await client.get(f"{TABLES}/users")).json()
    columns = {column["name"]: column for column in users["columns"]}
    assert columns["password_hash"]["masked"] is True
    assert columns["password_hash"]["searchable"] is False
    assert columns["email"]["searchable"] is True
    assert {action["name"] for action in users["actions"]} >= {"deactivate_user"}
    # Memberships point at users, so the console can link a user to theirs.
    assert {"table": "memberships", "column": "user_id"} in users["related"]

    assert (await client.get(f"{TABLES}/no_such_table")).status_code == 404


async def test_a_superuser_reads_across_tenants_masked_and_audited(
    app: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory,
    business_factory,
) -> None:
    admin = await _account(db_session, is_superuser=True)
    marker = uuid4().hex[:8]
    first = await business_factory(await tenant_factory(), name_en=f"Salon {marker} A")
    second = await business_factory(await tenant_factory(), name_en=f"Salon {marker} B")
    _sign_in(app, admin)

    page = await client.get(f"{TABLES}/businesses/rows", params={"q": marker})
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 2
    assert {row["id"] for row in body["items"]} == {str(first.id), str(second.id)}
    assert {row["tenant_id"] for row in body["items"]} == {
        str(first.tenant_id),
        str(second.tenant_id),
    }

    one = await client.get(f"{TABLES}/businesses/rows", params={"filter": f"id:{first.id}"})
    assert [row["id"] for row in one.json()["items"]] == [str(first.id)]

    shown = await client.get(f"{TABLES}/users/rows/{admin.id}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["values"]["password_hash"] == MASK
    assert shown.json()["values"]["email"] == admin.email

    trail = await _audit(db_session, admin)
    assert [(entry.kind.value, entry.table_name) for entry in trail] == [
        ("list", "businesses"),
        ("list", "businesses"),
        ("view", "users"),
    ]
    assert trail[0].detail["search"] == marker
    assert trail[2].row_id == str(admin.id)


async def test_masked_columns_cannot_be_searched_or_filtered(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    _sign_in(app, await _account(db_session, is_superuser=True))

    by_secret = await client.get(f"{TABLES}/users/rows", params={"filter": "password_hash:x"})
    assert by_secret.status_code == 422
    unknown = await client.get(f"{TABLES}/users/rows", params={"filter": "nope:x"})
    assert unknown.status_code == 422
    malformed = await client.get(f"{TABLES}/users/rows", params={"filter": "is_active:maybe"})
    assert malformed.status_code == 422


async def test_boolean_filter_matches_rows_by_the_selected_value(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    enabled = await _account(db_session, is_superuser=True)
    disabled = await _account(db_session)
    _sign_in(app, enabled)

    active_rows = await client.get(
        f"{TABLES}/users/rows", params={"filter": "is_superuser:true"}
    )
    inactive_rows = await client.get(
        f"{TABLES}/users/rows", params={"filter": "is_superuser:false"}
    )

    assert active_rows.status_code == 200, active_rows.text
    assert inactive_rows.status_code == 200, inactive_rows.text
    assert {row["id"] for row in active_rows.json()["items"]} == {str(enabled.id)}
    assert {row["id"] for row in inactive_rows.json()["items"]} == {str(disabled.id)}


async def test_deactivating_an_account_ends_its_sessions_but_never_your_own(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _account(db_session, is_superuser=True)
    target = await _account(db_session)
    version = target.token_version
    _sign_in(app, admin)

    done = await client.post(f"{TABLES}/users/rows/{target.id}/actions/deactivate_user", json={})
    assert done.status_code == 200, done.text
    assert done.json()["values"]["is_active"] is False
    await db_session.refresh(target)
    assert target.is_active is False
    assert target.token_version == version + 1

    restored = await client.post(
        f"{TABLES}/users/rows/{target.id}/actions/reactivate_user", json={}
    )
    assert restored.json()["values"]["is_active"] is True

    own = await client.post(f"{TABLES}/users/rows/{admin.id}/actions/deactivate_user", json={})
    assert own.status_code == 409

    actions = [entry.action for entry in await _audit(db_session, admin) if entry.action]
    assert actions == ["deactivate_user", "reactivate_user"]


async def test_hiding_a_listing_goes_through_catalog_for_the_rows_tenant(
    app: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory,
    business_factory,
) -> None:
    admin = await _account(db_session, is_superuser=True)
    business = await business_factory(await tenant_factory(), is_listed=True)
    _sign_in(app, admin)

    hidden = await client.post(
        f"{TABLES}/businesses/rows/{business.id}/actions/hide_listing", json={}
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["values"]["is_listed"] is False

    (entry,) = [e for e in await _audit(db_session, admin) if e.action]
    assert entry.target_tenant_id == business.tenant_id

    # Not an action on this table, and there is no generic edit.
    wrong = await client.post(
        f"{TABLES}/businesses/rows/{business.id}/actions/cancel_booking", json={}
    )
    assert wrong.status_code == 404


async def test_cancelling_a_booking_needs_a_reason_and_runs_the_state_machine(
    app: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    customer_factory,
    qualify,
) -> None:
    admin = await _account(db_session, is_superuser=True)
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    service = await service_factory(location)
    provider = await provider_factory(location)
    await qualify(provider, service)
    customer = await customer_factory(tenant)
    await set_tenant_scope(db_session, tenant.id)
    # Inside the customer-facing deadline: NOVA support cancels as the business.
    starts = datetime.now(UTC) + timedelta(hours=2)
    booking = BookingRecord(
        tenant_id=tenant.id,
        business_id=business.id,
        location_id=location.id,
        service_id=service.id,
        provider_id=provider.id,
        customer_id=customer.id,
        starts_at=starts,
        ends_at=starts + timedelta(hours=1),
        price=Decimal("150.00"),
        currency="SAR",
        status=BookingStatus.CONFIRMED,
        source=BookingSource.DIRECT_LINK,
    )
    db_session.add(booking)
    await db_session.flush()
    _sign_in(app, admin)

    path = f"{TABLES}/bookings/rows/{booking.id}/actions/cancel_booking"
    assert (await client.post(path, json={})).status_code == 422

    cancelled = await client.post(path, json={"reason": "Provider ill"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["values"]["status"] == "cancelled"
    assert cancelled.json()["values"]["cancellation_reason"] == "Provider ill"

    (entry,) = [e for e in await _audit(db_session, admin) if e.action]
    assert entry.detail == {"reason": "Provider ill"}
