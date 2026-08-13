from uuid import uuid4

from httpx import AsyncClient


async def test_create_tenant_returns_201(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/tenants",
        json={"name_en": "Nova Salon", "name_ar": "صالون نوفا", "phone": "+966500000000"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "nova-salon"
    assert body["default_currency"] == "SAR"


async def test_create_tenant_rejects_duplicate_slug(client: AsyncClient) -> None:
    payload = {"name_en": "Dup Salon", "name_ar": "صالون مكرر", "phone": "+966500000003"}
    first = await client.post("/api/v1/tenants", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/tenants", json=payload)
    assert second.status_code == 409


async def test_create_branch_and_list_branches(client: AsyncClient) -> None:
    tenant_response = await client.post(
        "/api/v1/tenants",
        json={"name_en": "Branch Test Salon", "name_ar": "صالون فروع", "phone": "+966500000004"},
    )
    tenant_id = tenant_response.json()["id"]

    branch_response = await client.post(
        f"/api/v1/tenants/{tenant_id}/branches",
        json={"name_en": "Main", "name_ar": "الرئيسي", "phone": "+966500000005"},
    )
    assert branch_response.status_code == 201

    list_response = await client.get(f"/api/v1/tenants/{tenant_id}/branches")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_get_tenant_not_found_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/tenants/{uuid4()}")
    assert response.status_code == 404
