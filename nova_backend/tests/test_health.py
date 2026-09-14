from httpx import AsyncClient


async def test_health_is_liveness_only(client: AsyncClient) -> None:
    """Liveness must not touch the database — see main.py for why."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready_checks_the_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_every_response_carries_a_correlation_id(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.headers.get("X-Correlation-ID")


async def test_inbound_correlation_id_is_preserved(client: AsyncClient) -> None:
    """A trace started upstream must continue through this service."""
    response = await client.get("/health", headers={"X-Correlation-ID": "trace-abc-123"})
    assert response.headers["X-Correlation-ID"] == "trace-abc-123"
