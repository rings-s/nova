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

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal, PrincipalKind, get_principal
from app.db.session import set_tenant_scope
from app.modules.ai_agents.agents import AGENTS
from app.modules.ai_agents.dependencies import get_inference_engine
from app.modules.ai_agents.runtime import InferenceEngine
from app.modules.billing.dependencies import build_billing_service
from app.modules.billing.domain import (
    TRIAL_AI_MESSAGES,
    TRIAL_DAYS,
    PlanTier,
    plan_for,
)
from app.modules.billing.models import SubscriptionRecord
from app.modules.booking.dependencies import build_booking_service
from app.modules.booking.domain import BookingSource, BookingStatus, WorkingWindow
from app.modules.booking.models import BookingRecord
from app.modules.catalog.service import CatalogService
from app.modules.identity.models import User
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
        # Every plan starts on its free week, during which it applies at once.
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
    confirm_hold_token: str | None = None,
) -> Response:
    body: dict[str, Any] = {"session_id": session_id, "message": message, "locale": "en"}
    if confirm_hold_token is not None:
        body["confirm_hold_token"] = confirm_hold_token
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
    await subscribe_to_studio(client, salon)
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
        ("request_cancellation", {"booking_id": str(booking_id), "reason": "Changed my mind"}),
        (FINAL, {"reply": "I could not find that booking.", "requires_human_handoff": True}),
    )
    use_model(app, script)

    response = await chat(client, salon, "customer_service_agent", with_business=False)

    assert response.status_code == 200, response.text
    assert len(script.tool_returns) == 2
    assert all("not_found" in result["error"] for result in script.tool_returns)
    assert response.json()["pending_cancellations"] == []
    status = (
        await db_session.execute(select(BookingRecord.status).where(BookingRecord.id == booking_id))
    ).scalar_one()
    assert status == BookingStatus.CONFIRMED


async def test_customer_service_offers_a_cancellation_and_only_the_customer_makes_it(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon, customer_factory
):
    user = User(
        email=f"customer-{uuid4().hex[:8]}@example.com",
        phone=f"+96650{uuid4().int % 10_000_000:07d}",
        full_name="Noura",
        password_hash="not-a-real-hash",
    )
    db_session.add(user)
    await db_session.flush()
    salon["customer"] = await customer_factory(salon["tenant"], user_id=user.id)
    [booking_id] = await add_bookings(
        db_session, salon, count=1, status=BookingStatus.CONFIRMED, days_from_now=5
    )
    # Began at the top of this hour: past any cancellation deadline.
    [started_id] = await add_bookings(
        db_session, salon, count=1, status=BookingStatus.CONFIRMED, days_from_now=0
    )
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject_id=user.id, kind=PrincipalKind.CUSTOMER
    )
    script = Script(
        ("request_cancellation", {"booking_id": str(started_id)}),
        ("request_cancellation", {"booking_id": str(booking_id), "reason": "Changed my mind"}),
        (FINAL, {"reply": "Please confirm the cancellation in the app."}),
    )
    use_model(app, script)

    response = await chat(client, salon, "customer_service_agent", with_business=False)

    assert response.status_code == 200, response.text
    assert script.tool_returns[0]["error"] == "cancellation_too_late"
    assert script.tool_returns[1]["cancelled"] is False
    [pending] = response.json()["pending_cancellations"]
    assert pending["booking_id"] == str(booking_id)
    assert pending["reason"] == "Changed my mind"
    statuses = await db_session.execute(
        select(BookingRecord.status).where(BookingRecord.id.in_([booking_id, started_id]))
    )
    assert set(statuses.scalars()) == {BookingStatus.CONFIRMED}

    # The customer confirms through the route the app already uses.
    confirmed = await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/bookings/{booking_id}/cancel",
        json={"reason": pending["reason"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "cancelled"


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
    await subscribe(client, salon, PlanTier.SOLO)
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
    from tests.modules.ai_agents.test_booking_turns import open_all_week

    await qualify(salon["provider"], salon["service"])
    await open_all_week(client, salon)
    # On the booking grid: the hold tool holds only a time that is really free.
    starts_at = (datetime.now(UTC) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
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
    await subscribe_to_studio(client, salon)
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


# --- plans -----------------------------------------------------------------

#: Every agent a tenant's chat route serves, which business it is told about,
#: and whether each plan unlocks it — read from the roster and the price list,
#: so a plan or agent added later is covered without editing this file.
TENANT_AGENTS = sorted(name for name, spec in AGENTS.items() if not spec.marketplace)


async def subscribe(client: AsyncClient, salon: dict, tier: PlanTier, **extra: Any) -> None:
    body = {"business_id": str(salon["business"].id), "tier": str(tier), **extra}
    response = await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/billing/subscriptions", json=body
    )
    assert response.status_code == 201, response.text


@pytest.mark.parametrize("tier", list(PlanTier))
@pytest.mark.parametrize("agent", TENANT_AGENTS)
async def test_every_plan_runs_the_agents_it_includes_and_only_those(
    app: FastAPI, client: AsyncClient, salon, tier: PlanTier, agent: str
):
    # On its free week a plan applies at once, as a paid-up plan would.
    await subscribe(client, salon, tier)
    spec = AGENTS[agent]
    use_model(app, Recorder())

    response = await chat(client, salon, agent, with_business=spec.needs_business)

    included = spec.required_feature is None or (
        spec.required_feature in plan_for(tier).included_features
    )
    if included:
        assert response.status_code == 200, response.text
        assert response.json()["reply"] == "Answer 1."
        assert response.json()["requires_human_handoff"] is False
    else:
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "plan_feature_required"


async def test_a_locked_business_runs_no_agents(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    """The free week ended unpaid: no assistant answers until the plan is paid."""
    await subscribe(client, salon, PlanTier.STUDIO)
    await set_tenant_scope(db_session, salon["tenant"].id)
    billing = build_billing_service(db_session, salon["tenant"].id)
    week_later = datetime.now(UTC) + timedelta(days=TRIAL_DAYS)
    assert await billing.expire_trial(salon["business"].id, now=week_later)
    use_model(app, Recorder())

    refused = await chat(client, salon, "accountant_agent")

    assert refused.status_code == 402
    assert refused.json()["error"]["code"] == "subscription_required"


async def test_the_trial_allows_ten_ai_messages(app: FastAPI, client: AsyncClient, salon):
    await subscribe(client, salon, PlanTier.STUDIO)
    use_model(app, Recorder())

    for _ in range(TRIAL_AI_MESSAGES):
        assert (await chat(client, salon, "accountant_agent")).status_code == 200
    refused = await chat(client, salon, "accountant_agent")

    assert refused.status_code == 402
    assert refused.json()["error"]["code"] == "trial_ai_limit_reached"


async def test_a_cancelled_plan_stops_unlocking_agents_after_its_paid_period(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon
):
    await subscribe(client, salon, PlanTier.STUDIO)
    cancelled = await client.post(
        f"/api/v1/tenants/{salon['tenant'].id}/billing/subscriptions/{salon['business'].id}/cancel",
        json={"at_period_end": False},
    )
    assert cancelled.status_code == 200, cancelled.text
    use_model(app, Recorder())
    # Still inside the period it paid for: still Studio (docs/11 section 5).
    assert (await chat(client, salon, "analyst_agent")).status_code == 200

    await set_tenant_scope(db_session, salon["tenant"].id)
    await db_session.execute(
        update(SubscriptionRecord)
        .where(SubscriptionRecord.business_id == salon["business"].id)
        .values(current_period_end=datetime.now(UTC).date())
    )
    await db_session.flush()

    # Past it, the business is locked: nothing runs until it pays.
    refused = await chat(client, salon, "analyst_agent")
    assert refused.status_code == 402
    assert refused.json()["error"]["code"] == "subscription_required"


# --- what a customer is told ------------------------------------------------


async def test_the_receptionist_can_say_where_a_branch_is(
    app: FastAPI, client: AsyncClient, location_factory, salon
):
    """Live, asked "Where is your branch located?", it had only a name and a city
    to go on, and gave the question back. Now each branch carries its map link."""
    await subscribe_to_studio(client, salon)
    await location_factory(
        salon["business"], name_en="Olaya Branch", city="Riyadh", latitude=24.69, longitude=46.6853
    )
    script = Script(
        ("list_branches", {}),
        (FINAL, {"reply": "Our Olaya Branch is in Riyadh."}),
    )
    use_model(app, script)

    response = await chat(client, salon, "receptionist_agent", message="Where are you?")

    assert response.status_code == 200, response.text
    branches = {b["name"]: b for b in script.tool_returns[0]["branches"]}
    assert branches["Olaya Branch"]["city"] == "Riyadh"
    assert branches["Olaya Branch"]["map_url"] == (
        "https://www.openstreetmap.org/?mlat=24.690000&mlon=46.685300#map=17/24.690000/46.685300"
    )
    # A branch never put on the map has no link to share, rather than a wrong one.
    assert branches["Main Branch"]["map_url"] is None


async def test_a_reply_that_only_repeats_the_question_is_not_shown(
    app: FastAPI, client: AsyncClient, salon
):
    await subscribe_to_studio(client, salon)
    use_model(
        app,
        Script(
            (
                FINAL,
                {
                    "reply": "<untrusted_user_text>Where is your branch located?"
                    "</untrusted_user_text>"
                },
            )
        ),
    )

    response = await chat(
        client, salon, "receptionist_agent", message="Where is your branch located?"
    )

    reply = response.json()["reply"]
    assert "untrusted_user_text" not in reply
    # Said for the model, from the records: where the storefront's branch is.
    assert reply.startswith("Here is where to find us:\n- Main Branch")
    assert response.json()["requires_human_handoff"] is False


async def test_the_internal_frame_never_reaches_a_customer(
    app: FastAPI, client: AsyncClient, salon
):
    await subscribe_to_studio(client, salon)
    use_model(
        app,
        Script((FINAL, {"reply": "<untrusted_user_text>We open at nine.</untrusted_user_text>"})),
    )

    response = await chat(client, salon, "receptionist_agent", message="When do you open?")

    assert response.json()["reply"] == "We open at nine."


class Briefed:
    """A model that notes the instructions it was given, then answers."""

    def __init__(self) -> None:
        self.instructions = ""

    async def respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.instructions = "\n".join(
            part.content
            for message in messages
            for part in message.parts
            if isinstance(part, SystemPromptPart)
        ) + "\n".join(getattr(message, "instructions", None) or "" for message in messages)
        answer = {"reply": "Noted."}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=answer)])


async def _bookable_salon(db_session: AsyncSession, salon: dict, qualify, service_factory):
    """`salon["service"]` is performed by a provider with hours; a second
    service is performed by nobody."""
    await qualify(salon["provider"], salon["service"])
    await set_tenant_scope(db_session, salon["tenant"].id)
    await build_booking_service(db_session, salon["tenant"].id).set_provider_schedule(
        provider_id=salon["provider"].id,
        windows=[WorkingWindow(weekday=d, start_minute=540, end_minute=1020) for d in range(7)],
    )
    return await service_factory(salon["location"], name_en="Hot Stone Massage", name_ar="مساج")


async def test_a_service_nobody_can_perform_is_marked_not_bookable(
    app: FastAPI, client: AsyncClient, db_session: AsyncSession, salon, qualify, service_factory
):
    """Live, the receptionist offered three services when only one had anyone
    to perform it."""
    await subscribe_to_studio(client, salon)
    unstaffed = await _bookable_salon(db_session, salon, qualify, service_factory)
    script = Script(("search_services", {}), (FINAL, {"reply": "Here they are."}))
    use_model(app, script)

    await chat(client, salon, "receptionist_agent", message="What do you offer?")

    listed = {s["service_id"]: s["bookable"] for s in script.tool_returns[0]["services"]}
    assert listed[str(salon["service"].id)] is True
    assert listed[str(unstaffed.id)] is False


async def test_the_receptionist_starts_with_the_business_facts(
    app: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
    salon,
    qualify,
    service_factory,
    location_factory,
):
    await subscribe_to_studio(client, salon)
    await _bookable_salon(db_session, salon, qualify, service_factory)
    await location_factory(
        salon["business"], name_en="Olaya Branch", city="Riyadh", latitude=24.69, longitude=46.6853
    )
    model = Briefed()
    use_model(app, model)

    await chat(client, salon, "receptionist_agent", message="Where are you?")

    facts = model.instructions
    assert "Olaya Branch (Riyadh, map: https://www.openstreetmap.org/?mlat=24.690000" in facts
    assert "Hot Stone Massage" in facts and "(not bookable right now)" in facts
    assert "(bookable)" in facts
