"""The roster (docs/13 section 2, ADR-0011). Pure — no database.

Every rule that differs between agents lives in an `AgentSpec`, so the rules
themselves can be asserted here rather than trusted to a reviewer.
"""

import inspect

import pytest

from app.modules.ai_agents.agents import (
    AGENT_ALIASES,
    AGENTS,
    INSIGHTS_FEATURE,
    UNAVAILABLE_AGENTS,
    WRITE_TOOLS,
    AgentUnavailableError,
    Audience,
    resolve_agent,
)
from app.modules.ai_agents.guardrails import OWNER_ONLY_AGENTS
from app.modules.ai_agents.schemas import InsightOutput, ManagerOutput
from app.modules.ai_agents.tools import AgentToolkit
from app.modules.analytics.domain import ChartId

LEDGER_CHARTS = {ChartId.PAYOUTS_BREAKDOWN, ChartId.NOVA_CHARGES, ChartId.COMMISSION_BY_CLASS}


def test_the_roster_is_the_one_docs_13_describes():
    assert set(AGENTS) == {
        "concierge_agent",
        "receptionist_agent",
        "customer_service_agent",
        "accountant_agent",
        "analyst_agent",
        "business_manager_agent",
    }


@pytest.mark.parametrize(("alias", "agent"), sorted(AGENT_ALIASES.items()))
def test_every_old_name_resolves_to_its_replacement(alias: str, agent: str):
    assert resolve_agent(alias).name == agent


@pytest.mark.parametrize("name", sorted(UNAVAILABLE_AGENTS | {"horoscope_agent"}))
def test_an_unavailable_or_unknown_agent_is_refused(name: str):
    with pytest.raises(AgentUnavailableError):
        resolve_agent(name)


def test_every_staff_agent_and_every_alias_to_one_is_owner_only():
    staff = {name for name, spec in AGENTS.items() if spec.audience is Audience.STAFF}
    aliases_to_staff = {alias for alias, target in AGENT_ALIASES.items() if target in staff}
    assert staff | aliases_to_staff == OWNER_ONLY_AGENTS


def test_only_customer_facing_agents_hold_write_tools():
    for spec in AGENTS.values():
        if spec.audience is Audience.STAFF:
            assert not spec.tools & WRITE_TOOLS, spec.name


def test_every_listed_tool_exists_and_describes_itself():
    for spec in AGENTS.values():
        for tool in spec.tools:
            method = getattr(AgentToolkit, tool, None)
            assert method is not None, f"{spec.name} lists '{tool}', which does not exist"
            assert inspect.iscoroutinefunction(method), tool
            # PydanticAI hands the docstring to the model as the tool's description.
            assert method.__doc__, f"'{tool}' needs a docstring"


def test_owner_agents_are_grounded_and_bound_to_one_business():
    for spec in AGENTS.values():
        is_staff = spec.audience is Audience.STAFF
        assert spec.grounded_numbers is is_staff, spec.name
        assert spec.needs_business is is_staff, spec.name
        assert issubclass(spec.output_type, InsightOutput) is is_staff, spec.name


def test_only_the_insight_agents_need_the_insights_feature():
    gated = {name for name, spec in AGENTS.items() if spec.required_feature}
    assert gated == {"analyst_agent", "business_manager_agent"}
    assert {AGENTS[name].required_feature for name in gated} == {INSIGHTS_FEATURE}


def test_only_the_accountant_draws_the_ledger():
    for spec in AGENTS.values():
        if spec.charts & LEDGER_CHARTS:
            assert spec.name == "accountant_agent"
    assert LEDGER_CHARTS.issubset(AGENTS["accountant_agent"].charts)


def test_only_the_manager_proposes_actions():
    holders = {name for name, spec in AGENTS.items() if "propose_action" in spec.tools}
    assert holders == {"business_manager_agent"}
    assert AGENTS["business_manager_agent"].output_type is ManagerOutput


def test_every_owner_agent_needs_a_role_permission_and_no_customer_agent_does():
    """Staff is not enough: the HTTP routes behind these tools are gated by role."""
    for spec in AGENTS.values():
        is_staff = spec.audience is Audience.STAFF
        assert (spec.required_permission is not None) is is_staff, spec.name
