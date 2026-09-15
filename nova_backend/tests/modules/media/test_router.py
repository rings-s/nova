"""Who may see a salon's media library through the API.

Every route is staff-only. A customer principal reaches every tenant on the
marketplace, and these routes list unready and unpublished assets and mint
public share links. The customer is refused before any row is read, so those
cases need no assets. Needs Postgres.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.security import Principal, PrincipalKind, get_principal


@pytest.fixture
def as_customer(app: FastAPI) -> None:
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )


@pytest.mark.parametrize("path", ["", "/{asset_id}", "/{asset_id}/link"])
async def test_a_customer_cannot_list_read_or_share_a_salons_media(
    client: AsyncClient, tenant_factory, as_customer, path: str
) -> None:
    tenant = await tenant_factory()

    response = await client.get(
        f"/api/v1/tenants/{tenant.id}/media{path.format(asset_id=uuid4())}",
        params={"business_id": str(uuid4())},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_staff_still_list_their_media(
    client: AsyncClient, tenant_factory, business_factory
) -> None:
    tenant = await tenant_factory()
    business = await business_factory(tenant)

    response = await client.get(
        f"/api/v1/tenants/{tenant.id}/media", params={"business_id": str(business.id)}
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
