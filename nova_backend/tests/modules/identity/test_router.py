from uuid import uuid4

from httpx import AsyncClient


async def test_create_tenant_returns_created_tenant(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/tenants",
        json={"name_en": "Glow Salon", "name_ar": "صالون جلو", "phone": "+966500000002"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["slug"] == "glow-salon"
    assert body["default_currency"] == "SAR"


async def test_create_tenant_rejects_duplicate_slug(client: AsyncClient) -> None:
    payload = {"name_en": "Dup Salon", "name_ar": "صالون مكرر", "phone": "+966500000003"}

    first = await client.post("/api/v1/tenants", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/tenants", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_slug"


async def test_create_tenant_rejects_non_gcc_phone(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/tenants",
        json={"name_en": "US Salon", "name_ar": "صالون", "phone": "+15550000000"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_get_unknown_tenant_returns_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/tenants/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "tenant_not_found"
