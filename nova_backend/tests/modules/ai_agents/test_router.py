"""The AI routes over HTTP. Needs Postgres, as every `client` test does.

No model runs here: each request below is refused before inference would start.
"""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.security import Principal, PrincipalKind
from app.modules.ai_agents.dependencies import get_conversation_store, get_inference_engine
from app.modules.ai_agents.history import ConversationKey, RedisConversationStore
from app.modules.ai_agents.runtime import InferenceEngine


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


async def test_the_catalog_says_what_each_agent_needs_and_whether_a_model_answers(
    app: FastAPI, client: AsyncClient, tenant_factory
) -> None:
    """A client hides the agents a role can't use, and the whole chat when the
    local model server is down. The engine points at nothing, so the answer does
    not depend on whether this machine happens to run LM Studio."""
    app.dependency_overrides[get_inference_engine] = lambda: InferenceEngine(
        base_url="http://unused.invalid/v1",
        routing_model="routing",
        reasoning_model="reasoning",
    )
    tenant = await tenant_factory()

    response = await client.get(f"/api/v1/tenants/{tenant.id}/ai/agents")

    assert response.status_code == 200
    body = response.json()
    assert body["inference_available"] is False
    agents = {agent["name"]: agent for agent in body["agents"]}
    assert agents["accountant_agent"]["required_permission"] == "view_financials"
    assert agents["accountant_agent"]["needs_business"] is True
    assert agents["receptionist_agent"]["required_permission"] is None
    assert agents["receptionist_agent"]["needs_business"] is False


async def test_forgetting_my_conversations_clears_them_at_every_business(
    app: FastAPI, client: AsyncClient, principal: Principal
) -> None:
    """The caller's memory goes everywhere at once; nobody else's is touched."""
    memory = app.dependency_overrides[get_conversation_store]()
    mine = ConversationKey(
        tenant_id=uuid4(), principal_id=principal.subject_id, business_id=None, session_id="s1"
    )
    theirs = ConversationKey(
        tenant_id=mine.tenant_id, principal_id=uuid4(), business_id=None, session_id="s1"
    )
    await memory.append(mine, b"turn")
    await memory.append(theirs, b"turn")

    response = await client.delete("/api/v1/ai/conversations")

    assert response.status_code == 200
    assert response.json() == {"forgotten": 1}
    assert await memory.load(mine) == []
    assert await memory.load(theirs) == [b"turn"]


async def test_an_unreachable_memory_answers_503_not_done(
    app: FastAPI, client: AsyncClient
) -> None:
    app.dependency_overrides[get_conversation_store] = lambda: RedisConversationStore(
        None, ttl_seconds=60, max_turns=3
    )

    response = await client.delete("/api/v1/ai/conversations")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "ai_memory_unavailable"
    assert error["retryable"] is True
