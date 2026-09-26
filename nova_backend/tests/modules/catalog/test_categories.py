"""Service categories: one platform list, edited by a superuser only.

Categories used to be free text typed by each salon, so the marketplace filter
saw "Hair", "hair" and "Hair & Beauty" as three things. Now a salon files a
service under a row of `service_categories`, and only an account with
`users.is_superuser` may add to or change that list, whatever its salon role.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.modules.identity.models import User

ADMIN = "/api/v1/admin/catalog/categories"
PUBLIC = "/api/v1/discovery/categories"


async def _account(db_session: AsyncSession, *, is_superuser: bool) -> User:
    user = User(
        email=f"user-{uuid4().hex[:8]}@example.com",
        full_name="Someone",
        password_hash="not-a-real-hash",
        is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _sign_in(app: FastAPI, user: User, kind: PrincipalKind, tenant_id=None) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=user.id,
        kind=kind,
        tenant_ids=frozenset({tenant_id}) if tenant_id else frozenset(),
        roles=frozenset({"owner"}) if kind is PrincipalKind.STAFF else frozenset(),
    )


async def test_a_superuser_adds_renames_and_retires_a_category(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    _sign_in(app, await _account(db_session, is_superuser=True), PrincipalKind.CUSTOMER)

    created = await client.post(ADMIN, json={"name_en": "Nail Art", "name_ar": "فن الأظافر"})
    assert created.status_code == 201, created.text
    category = created.json()
    assert category["slug"] == "nail-art"
    assert category["is_active"] is True

    renamed = await client.patch(f"{ADMIN}/{category['id']}", json={"name_en": "Nails"})
    assert renamed.status_code == 200
    # The slug stays: shared marketplace links filter by it.
    assert (renamed.json()["name_en"], renamed.json()["slug"]) == ("Nails", "nail-art")

    retired = await client.patch(f"{ADMIN}/{category['id']}", json={"is_active": False})
    assert retired.json()["is_active"] is False

    listed = (await client.get(ADMIN)).json()
    assert category["id"] in [row["id"] for row in listed]
    public = (await client.get(PUBLIC)).json()
    assert category["id"] not in [row["id"] for row in public]


async def test_a_duplicate_slug_is_refused(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    _sign_in(app, await _account(db_session, is_superuser=True), PrincipalKind.CUSTOMER)
    payload = {"name_en": "Brows Only", "name_ar": "حواجب"}
    assert (await client.post(ADMIN, json=payload)).status_code == 201

    again = await client.post(ADMIN, json=payload)

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "duplicate_slug"


@pytest.mark.parametrize("kind", [PrincipalKind.STAFF, PrincipalKind.CUSTOMER])
async def test_anyone_else_is_refused_whatever_their_salon_role(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, tenant_factory, kind
) -> None:
    """An owner runs one salon; the list is every salon's."""
    tenant = await tenant_factory()
    _sign_in(app, await _account(db_session, is_superuser=False), kind, tenant.id)

    responses = [
        await client.get(ADMIN),
        await client.post(ADMIN, json={"name_en": "Owner Made", "name_ar": "مالك"}),
        await client.patch(f"{ADMIN}/{uuid4()}", json={"is_active": False}),
    ]

    assert [r.status_code for r in responses] == [403, 403, 403]
    assert {r.json()["error"]["code"] for r in responses} == {"forbidden"}


async def test_me_says_whether_the_account_is_a_superuser(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _account(db_session, is_superuser=True)
    _sign_in(app, admin, PrincipalKind.CUSTOMER)

    body = (await client.get("/api/v1/auth/me")).json()

    assert (body["id"], body["is_superuser"]) == (str(admin.id), True)


async def test_a_service_is_filed_under_a_category_from_the_list(
    client: AsyncClient, tenant_factory, business_factory, location_factory, category_factory
) -> None:
    tenant = await tenant_factory()
    location = await location_factory(await business_factory(tenant))
    category = await category_factory(name_en="Hair Colour")

    response = await client.post(
        f"/api/v1/tenants/{tenant.id}/catalog/services",
        json={
            "location_id": str(location.id),
            "name_en": "Balayage",
            "name_ar": "بالاياج",
            "duration_minutes": 90,
            "price": "400.00",
            "category_id": str(category.id),
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category_id"] == str(category.id)
    assert body["category"]["name_en"] == "Hair Colour"


@pytest.mark.parametrize("retired", [True, False])
async def test_a_salon_cannot_use_a_retired_or_made_up_category(
    client: AsyncClient,
    tenant_factory,
    business_factory,
    location_factory,
    category_factory,
    retired,
) -> None:
    tenant = await tenant_factory()
    location = await location_factory(await business_factory(tenant))
    category_id = (await category_factory(is_active=False)).id if retired else uuid4()

    response = await client.post(
        f"/api/v1/tenants/{tenant.id}/catalog/services",
        json={
            "location_id": str(location.id),
            "name_en": "Mystery",
            "name_ar": "غامض",
            "duration_minutes": 30,
            "price": "10.00",
            "category_id": str(category_id),
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "category_not_found"


async def test_the_marketplace_filters_by_category_slug(
    client: AsyncClient,
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    category_factory,
) -> None:
    nails = await category_factory(slug=f"nails-{uuid4().hex[:6]}", name_en="Nails Filter")
    wanted = await business_factory(await tenant_factory(), name_en="Filter Nail Bar")
    await service_factory(await location_factory(wanted), category=nails)
    other = await business_factory(await tenant_factory(), name_en="Filter Barber")
    await service_factory(await location_factory(other))

    items = (
        await client.get(
            "/api/v1/discovery/businesses", params={"q": "Filter", "category": nails.slug}
        )
    ).json()["items"]

    assert [item["business_id"] for item in items] == [str(wanted.id)]


async def test_a_branch_is_created_without_a_phone(
    client: AsyncClient, tenant_factory, business_factory
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)

    response = await client.post(
        f"/api/v1/tenants/{tenant.id}/catalog/locations",
        json={"business_id": str(business.id), "name_en": "North", "name_ar": "الشمال"},
    )

    assert response.status_code == 201, response.text
    assert "phone" not in response.json()
