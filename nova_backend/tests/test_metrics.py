"""`/metrics`: absent unless a token is configured, never public, bounded labels."""

import pytest
from httpx import AsyncClient

from app.core import metrics
from app.core.config import get_settings


@pytest.fixture
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("METRICS_TOKEN", "scrape-token-for-tests")
    get_settings.cache_clear()
    yield "scrape-token-for-tests"
    get_settings.cache_clear()


async def test_with_no_token_configured_the_endpoint_does_not_exist(client: AsyncClient) -> None:
    assert (await client.get("/metrics")).status_code == 404


async def test_a_wrong_or_missing_token_is_refused(client: AsyncClient, token: str) -> None:
    assert (await client.get("/metrics")).status_code == 401
    wrong = await client.get("/metrics", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


async def test_the_right_token_gets_request_counts_by_route_template(
    client: AsyncClient, token: str
) -> None:
    metrics.reset()
    await client.get("/health")

    response = await client.get("/metrics", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.text
    assert 'nova_http_requests_total{method="GET",route="/health",status="2xx"} 1' in body
    assert "nova_http_request_duration_seconds_count" in body
    # Present whether or not the outbox could be read from this test's database.
    assert "nova_outbox_scrape_ok" in body


def test_a_latency_lands_in_every_bucket_at_or_above_it() -> None:
    metrics.reset()
    metrics.record_request(method="GET", route="/x", status=200, seconds=0.03)

    text = metrics.render()

    assert 'le="0.025"} 0' in text
    assert 'le="0.05"} 1' in text
    assert 'le="+Inf"} 1' in text
