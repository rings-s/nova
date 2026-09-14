"""Whole agent turns over HTTP, with PydanticAI's FunctionModel standing in for Ollama.

Needs Postgres. No network and no GPU: the model is a script, so each test pins
exactly what a model does and checks what NOVA does about it (docs/13 section 12).
The real PydanticAI library runs every time, which is how a renamed class fails
this file instead of silently handing every chat to a human.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.modules.ai_agents.dependencies import get_inference_engine
from app.modules.ai_agents.runtime import InferenceEngine
from app.modules.booking.domain import BookingSource, BookingStatus
from app.modules.booking.models import BookingRecord
from app.modules.catalog.service import CatalogService
from app.modules.queue.models import QueueEntryRecord

FINAL = "final"
#: The model itself fails, as an unreachable or overloaded one would.
CRASH = "crash"


class Script:
    """A model that plays fixed moves: a tool call, its final answer, or a crash."""

    def __init__(self, *moves: tuple[str, dict[str, Any]]) -> None:
        self.moves = list(moves)
        #: What each tool handed back to the model, in order.
        self.tool_returns: list[Any] = []

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        for part in messages[-1].parts:
            if isinstance(part, ToolReturnPart):
                self.tool_returns.append(part.content)
        if self.moves:
            name, args = self.moves.pop(0)
        else:
            name, args = FINAL, {"reply": "Someone will follow up.", "requires_human_handoff": True}
        if name == CRASH:
            raise RuntimeError("The model stopped responding.")
        if name == FINAL:
            name = info.output_tools[0].name
        return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])


class Recorder:
    """A model that answers every turn, noting the customer messages it was shown."""

    def __init__(self) -> None:
        self.shown: list[list[str]] = []

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.shown.append(
            [
                part.content
                for message in messages
                for part in message.parts
                if isinstance(part, UserPromptPart)
            ]
        )
        answer = {"reply": f"Answer {len(self.shown)}."}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=answer)])


def use_model(app: FastAPI, model: Script | Recorder, *, tool_timeout_seconds: float = 5.0) -> None:
    app.dependency_overrides[get_inference_engine] = lambda: InferenceEngine(
        base_url="http://unused.invalid/v1",
        routing_model="routing",
        reasoning_model="reasoning",
        tool_timeout_seconds=tool_timeout_seconds,
        model_override=FunctionModel(model.respond),
    )


@pytest_asyncio.fixture
async def salon(
    tenant_factory,
    business_factory,
    location_factory,
    service_factory,
    provider_factory,
    customer_factory,
):
    tenant = await tenant_factory()
    business = await business_factory(tenant)
    location = await location_factory(business)
    return {
        "tenant": tenant,
        "business": business,
        "location": location,
        "service": await service_factory(location),
        "provider": await provider_factory(location),
        "customer": await customer_factory(tenant),
    }


async def add_bookings(
    db_session: AsyncSession,
    salon: dict,
    *,
    count: int,
    status: BookingStatus = BookingStatus.COMPLETED,
    days_from_now: int = -10,
) -> list[UUID]:
    # In the salon's own scope, as the requests that made them were.
    await set_tenant_scope(db_session, salon["tenant"].id)
    first = (datetime.now(UTC) + timedelta(days=days_from_now)).replace(
        minute=0, second=0, microsecond=0
    )
    ids = []
    for i in range(count):
        starts = first + timedelta(hours=2 * i)
        record = BookingRecord(
            id=uuid4(),
            tenant_id=salon["tenant"].id,
            business_id=salon["business"].id,
            location_id=salon["location"].id,
            service_id=salon["service"].id,
            provider_id=salon["provider"].id,
            customer_id=salon["customer"].id,
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            price=Decimal("150.00"),
            currency="SAR",
            status=status,
            source=BookingSource.DIRECT_LINK,
        )
        db_session.add(record)
        ids.append(record.id)
    await db_session.flush()
    return ids


async def subscribe_to_studio(client: AsyncClient, salon: dict) -> None:
    response = await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/billing/subscriptions",
        json={"business_id": str(salon["business"].id), "tier": "studio"},
    )
    assert response.status_code == 201, response.text


async def chat(
    client: AsyncClient,
    salon: dict,
    agent: str,
    *,
    with_business: bool = True,
    customer_id: UUID | None = None,
    message: str = "How is business?",
    session_id: str = "turn-test",
) -> Response:
    body: dict[str, Any] = {"session_id": session_id, "message": message, "locale": "en"}
    if with_business:
        body["business_id"] = str(salon["business"].id)
    if customer_id is not None:
        body["customer_id"] = str(customer_id)
    return await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/ai/chat", params={"agent": agent}, json=body
    )


async def test_the_analyst_shows_the_chart_a_tool_drew_and_drops_one_it_invented(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    await subscribe_to_studio(client, salon)
    await add_bookings(db_session, salon, count=4)
    script = Script(
        ("get_overview", {}),
        ("render_chart", {"chart_id": "revenue_trend"}),
        (
            FINAL,
            {
                "reply": "Here is completed revenue by day.",
                "chart_ids": ["revenue_trend", "invented_chart"],
                "metrics_used": ["revenue", "invented_metric"],
                "confidence": 0.8,
            },
        ),
    )
    use_model(app, script)

    response = await chat(client, salon, "analyst_agent")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent"] == "analyst_agent"
    assert body["requires_human_handoff"] is False
    assert [chart["chart_id"] for chart in body["charts"]] == ["revenue_trend"]
    assert body["charts"][0]["figure"]["data"]
    assert body["metrics_used"] == ["revenue"]


async def test_an_invented_figure_is_retried_then_handed_off(
    app: FastAPI, client: AsyncClient, salon
):
    await subscribe_to_studio(client, salon)
    invented = (FINAL, {"reply": "Revenue was 91,250.00 SAR.", "confidence": 0.9})
    use_model(app, Script(invented, invented, invented, invented))

    response = await chat(client, salon, "analyst_agent")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_human_handoff"] is True
    assert body["degraded"] is True
    assert "91,250" not in body["reply"]


async def test_the_old_billing_agent_name_reaches_the_accountant_with_grounded_figures(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    await add_bookings(db_session, salon, count=2)
    script = Script(
        ("get_financial_summary", {}),
        (FINAL, {"reply": "Completed bookings earned 300.00 SAR.", "metrics_used": ["revenue"]}),
    )
    use_model(app, script)

    response = await chat(client, salon, "billing_agent")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent"] == "accountant_agent"
    assert body["reply"] == "Completed bookings earned 300.00 SAR."
    assert body["requires_human_handoff"] is False
    assert body["metrics_used"] == ["revenue"]
    assert script.tool_returns[0]["revenue"] == "300.00"


async def test_customer_service_cannot_read_or_cancel_a_strangers_booking(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    [booking_id] = await add_bookings(
        db_session, salon, count=1, status=BookingStatus.CONFIRMED, days_from_now=5
    )
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )
    script = Script(
        ("get_booking_status", {"booking_id": str(booking_id)}),
        ("cancel_booking", {"booking_id": str(booking_id), "reason": "Changed my mind"}),
        (FINAL, {"reply": "I could not find that booking.", "requires_human_handoff": True}),
    )
    use_model(app, script)

    response = await chat(client, salon, "customer_service_agent", with_business=False)

    assert response.status_code == 200, response.text
    assert len(script.tool_returns) == 2
    assert all("not_found" in result["error"] for result in script.tool_returns)
    status = (
        await db_session.execute(select(BookingRecord.status).where(BookingRecord.id == booking_id))
    ).scalar_one()
    assert status == BookingStatus.CONFIRMED


async def test_the_manager_proposes_an_action_and_changes_nothing(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    await subscribe_to_studio(client, salon)
    await add_bookings(db_session, salon, count=3)
    provider_id = str(salon["provider"].id)
    script = Script(
        ("get_overview", {}),
        (
            "propose_action",
            {
                "kind": "adjust_working_hours",
                "title": "Open Sara on Saturday mornings",
                "rationale": "Weekday utilization is low while weekends book up.",
                "metric": "utilization",
                "target_id": provider_id,
            },
        ),
        (
            FINAL,
            {
                "reply": "One change is worth considering.",
                "proposed_action_ids": ["pa_1", "pa_9"],
                "metrics_used": ["utilization"],
            },
        ),
    )
    use_model(app, script)

    response = await chat(client, salon, "business_manager_agent")

    assert response.status_code == 200, response.text
    [action] = response.json()["proposed_actions"]
    assert action["kind"] == "adjust_working_hours"
    assert action["target_id"] == provider_id
    assert action["apply_via"].startswith("PUT /api/v1/tenants/")
    assert action["requires_confirmation"] is True


async def test_the_analyst_needs_a_plan_with_insights(app: FastAPI, client: AsyncClient, salon):
    use_model(app, Script())
    response = await chat(client, salon, "analyst_agent")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "plan_feature_required"


async def test_a_staff_agent_needs_a_business(app: FastAPI, client: AsyncClient, salon):
    use_model(app, Script())
    response = await chat(client, salon, "accountant_agent", with_business=False)
    assert response.status_code == 422


# --- units of work ---------------------------------------------------------


async def test_a_stalled_tool_hands_off_and_leaves_nothing_broken(
    app: FastAPI, client: AsyncClient, salon, monkeypatch
):
    """The tool's own unit of work is rolled back and the turn degrades.

    A turn used to share the request's transaction, so a tool cancelled
    mid-query left it needing a rollback, and the router's commit raised: a
    500 where docs/10 section 12 promises a handoff.
    """

    async def stalled(self, location_id):
        await asyncio.sleep(5)

    monkeypatch.setattr(CatalogService, "list_services", stalled)
    use_model(
        app,
        Script(("search_services", {"location_id": str(salon["location"].id)})),
        tool_timeout_seconds=0.05,
    )

    response = await chat(client, salon, "concierge_agent", with_business=False)

    assert response.status_code == 200, response.text
    assert response.json()["requires_human_handoff"] is True
    assert response.json()["degraded"] is True
    # The connection is still good for the next request that needs it.
    business = await client.get(
        f"/api/v1/tenants/{salon['tenant'].id}/catalog/businesses/{salon['business'].id}"
    )
    assert business.status_code == 200, business.text


async def test_a_place_in_the_queue_is_kept_returned_and_not_taken_twice_when_the_model_fails(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    """`join_queue` committed as it returned; the retry would join again.

    The receptionist prefers the reasoning model, whose failure normally earns
    a second attempt on the routing model. That attempt starts the turn over,
    so after a committed write it is skipped and the turn hands off instead —
    with the place in line in the response, because the customer has it.
    """
    base = f"/api/v1/tenants/{salon['tenant'].id}"
    queue = (
        await client.post(f"{base}/queues", json={"location_id": str(salon["location"].id)})
    ).json()
    join = ("join_queue", {"queue_id": queue["id"], "service_id": str(salon["service"].id)})
    script = Script(join, (CRASH, {}), join, (FINAL, {"reply": "You are in line."}))
    use_model(app, script)

    response = await chat(
        client,
        salon,
        "receptionist_agent",
        with_business=False,
        customer_id=salon["customer"].id,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requires_human_handoff"] is True
    [place] = body["queue_places"]
    assert place["queue_id"] == queue["id"]
    assert place["place_in_line"] == 1
    entries = (
        await db_session.execute(
            select(QueueEntryRecord.id).where(QueueEntryRecord.queue_id == UUID(queue["id"]))
        )
    ).scalars()
    assert [str(entry_id) for entry_id in entries] == [place["entry_id"]]
    # The routing model never ran: its moves are still unplayed.
    assert len(script.moves) == 2


async def test_a_held_slot_reaches_the_client_with_its_token_and_the_model_never_sees_it(
    app: FastAPI, client: AsyncClient, salon, qualify
):
    await qualify(salon["provider"], salon["service"])
    starts_at = (datetime.now(UTC) + timedelta(days=2)).replace(microsecond=0)
    slot = {
        "provider_id": str(salon["provider"].id),
        "service_id": str(salon["service"].id),
        "starts_at": starts_at.isoformat(),
    }
    script = Script(("hold_slot", slot), (FINAL, {"reply": "I am holding that time for you."}))
    use_model(app, script)

    response = await chat(
        client,
        salon,
        "receptionist_agent",
        with_business=False,
        customer_id=salon["customer"].id,
    )

    assert response.status_code == 200, response.text
    [held] = response.json()["held_slots"]
    assert held["hold_token"]
    assert held["provider_id"] == slot["provider_id"]
    # The model heard that the time is held, never the credential for it.
    assert script.tool_returns[0]["held"] is True
    assert "hold_token" not in script.tool_returns[0]

    booked = await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/bookings",
        json={
            **slot,
            "location_id": str(salon["location"].id),
            "hold_token": held["hold_token"],
            "on_behalf_of_customer_id": str(salon["customer"].id),
        },
    )
    assert booked.status_code == 201, booked.text


# --- conversation memory ----------------------------------------------------


async def test_a_conversation_remembers_its_own_earlier_turns_and_nobody_elses(
    app: FastAPI, client: AsyncClient, salon
):
    recorder = Recorder()
    use_model(app, recorder)

    await chat(client, salon, "concierge_agent", with_business=False, message="Do you do keratin?")
    await chat(client, salon, "concierge_agent", with_business=False, message="How long is it?")
    await chat(
        client,
        salon,
        "concierge_agent",
        with_business=False,
        message="Hello",
        session_id="another-chat",
    )
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=uuid4(), kind=PrincipalKind.CUSTOMER
    )
    await chat(client, salon, "concierge_agent", with_business=False, message="Anyone there?")

    assert recorder.shown[1] == ["Do you do keratin?", "How long is it?"]
    # Another session, and another caller naming the first session: both fresh.
    assert recorder.shown[2] == ["Hello"]
    assert recorder.shown[3] == ["Anyone there?"]


async def test_a_figure_a_tool_returned_in_an_earlier_turn_is_still_grounded(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    await add_bookings(db_session, salon, count=2)
    use_model(
        app,
        Script(
            ("get_financial_summary", {}),
            (FINAL, {"reply": "Completed bookings earned 300.00 SAR."}),
        ),
    )
    first = await chat(client, salon, "accountant_agent")
    assert first.json()["requires_human_handoff"] is False, first.text

    # No tool this time: the figure comes from the conversation itself.
    use_model(app, Script((FINAL, {"reply": "As I said, 300.00 SAR."})))
    again = await chat(client, salon, "accountant_agent", message="Say that again?")

    assert again.status_code == 200, again.text
    assert again.json()["requires_human_handoff"] is False
    assert again.json()["reply"] == "As I said, 300.00 SAR."
