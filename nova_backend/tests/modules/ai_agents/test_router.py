"""The AI routes over HTTP. Needs Postgres, as every `client` test does.

No model runs here: each request below is refused before inference would start.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.security import Principal, PrincipalKind


@pytest.fixture
def principal() -> Principal:
    """A signed-in customer, who can reach every tenant on the marketplace."""
    return Principal(subject_id=uuid4(), kind=PrincipalKind.CUSTOMER)


async def test_a_customer_cannot_reach_the_billing_agent(
    client: AsyncClient, tenant_factory
) -> None:
    """docs/10 section 4. The billing routes are staff-only, and chat must not be
    a way around them."""
    tenant = await tenant_factory()

    response = await client.post(
        f"/api/v1/tenants/{tenant.id}/ai/chat",
        params={"agent": "billing_agent"},
        json={"session_id": "s1", "message": "How much is this month's invoice?"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "agent_guardrail"
