"""The inference engine's choice of model server. No database, no model server:
a `FunctionModel` stands in for the model, and an unused port for a dead server.
"""

import socket

import pytest

from app.modules.ai_agents import runtime
from app.modules.ai_agents.runtime import InferenceEngine, clean_reply
from app.modules.ai_agents.schemas import AgentOutput

pytest.importorskip("pydantic_ai")

from pydantic_ai.messages import ModelMessage, ModelRequest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel


def _engine(**overrides) -> InferenceEngine:
    kwargs = {
        "base_url": "http://127.0.0.1:1234/v1",
        "provider": "lmstudio",
        "routing_model": "qwen/qwen3-8b",
        "reasoning_model": "qwen/qwen3-8b",
    }
    kwargs.update(overrides)
    return InferenceEngine(**kwargs)


def _unused_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestProviders:
    def test_lm_studio_is_spoken_to_as_an_openai_compatible_server(self):
        model = _engine()._chat_model("qwen/qwen3-8b")

        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "qwen/qwen3-8b"
        assert str(model.client.base_url).startswith("http://127.0.0.1:1234/v1")

    def test_lm_studio_reads_thinking_where_it_puts_it(self):
        # A qwen3 reply's reasoning arrives in `reasoning_content`; read
        # anywhere else, it would be shown to the customer as the answer.
        model = _engine()._chat_model("qwen/qwen3-8b")

        assert model.profile.get("openai_chat_thinking_field") == "reasoning_content"

    def test_the_publisher_prefix_does_not_hide_the_model_family(self):
        # `qwen/qwen3-8b` must get the qwen profile, as `qwen3:8b` does on Ollama.
        lm_studio = _engine()._chat_model("qwen/qwen3-8b")
        ollama = _engine(provider="ollama")._chat_model("qwen3:8b")

        assert lm_studio.profile.get("json_schema_transformer") is ollama.profile.get(
            "json_schema_transformer"
        )

    def test_ollama_keeps_its_own_provider(self):
        model = _engine(provider="ollama", base_url="http://localhost:11434/v1")._chat_model(
            "llama3.1:8b"
        )

        assert model.system == "ollama"


def _instructions_seen(seen: list[str]) -> FunctionModel:
    """A model that records its instructions and answers with a valid output."""

    def respond(messages: list[ModelMessage], info: AgentInfo):
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        for message in messages:
            if isinstance(message, ModelRequest) and message.instructions:
                seen.append(message.instructions)
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, {"reply": "ok", "confidence": 0.9})])

    return FunctionModel(respond)


class TestThinking:
    async def _instructions(self, **engine) -> str:
        seen: list[str] = []
        result = await _engine(model_override=_instructions_seen(seen), **engine).run_turn(
            agent_name="concierge_agent",
            system_prompt="Be brief.",
            user_message="hello",
            deps=None,
            tools=[],
            locale="en",
            output_type=AgentOutput,
        )
        assert result.reply == "ok"
        return seen[-1]

    async def test_qwen3_is_told_not_to_think_by_default(self):
        # Thinking multiplied a qwen3-8b turn's time about fivefold in LM Studio,
        # and the generic `reasoning_effort` switch was not honoured.
        assert (await self._instructions()).endswith("/no_think")

    async def test_thinking_can_be_turned_back_on(self):
        assert "/no_think" not in await self._instructions(thinking=True)

    async def test_other_families_are_left_alone(self):
        instructions = await self._instructions(routing_model="llama3.1:8b")

        assert "/no_think" not in instructions


class TestReachability:
    async def test_a_dead_server_is_unreachable(self, monkeypatch):
        monkeypatch.setattr(runtime, "_probe_cache", {})
        engine = _engine(base_url=f"http://127.0.0.1:{_unused_port()}/v1")

        assert await engine.reachable() is False

    async def test_a_disabled_engine_is_unreachable_without_asking(self, monkeypatch):
        monkeypatch.setattr(runtime, "_probe_cache", {})

        assert await _engine(enabled=False).reachable() is False

    async def test_an_injected_model_needs_no_server(self):
        engine = _engine(model_override=_instructions_seen([]))

        assert await engine.reachable() is True


class TestReplyCleanup:
    def test_an_echoed_structured_field_is_removed_from_the_text(self):
        # qwen3-1.7b, verbatim apart from the figure: the chart itself arrives
        # through `chart_ids`, so the markup is noise to a reader.
        reply = "We earned SAR 480.00 this month. <chart_ids>nova_charges</chart_ids> 📊"

        assert clean_reply(reply) == "We earned SAR 480.00 this month. 📊"

    def test_multiline_echoes_and_several_fields_go(self):
        reply = (
            'Done.\n\n<chart_ids>\n{"chart_id": "x"}\n</chart_ids>\n<metrics_used>[]</metrics_used>'
        )

        assert clean_reply(reply) == "Done."

    def test_ordinary_text_is_untouched(self):
        assert clean_reply("Revenue is up 5% <3") == "Revenue is up 5% <3"


async def test_a_plain_text_answer_is_accepted_as_the_reply():
    """qwen3-1.7b, live: it answered in prose instead of calling the output tool,
    the output failed validation twice, and a good answer became a handoff."""
    from pydantic_ai.messages import ModelResponse, TextPart

    def prose(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("We have manicures at 9:45 and 10:00. Shall I book?")])

    result = await _engine(model_override=FunctionModel(prose)).run_turn(
        agent_name="marketplace_agent",
        system_prompt="Be brief.",
        user_message="manicure?",
        deps=None,
        tools=[],
        locale="en",
        output_type=AgentOutput,
    )

    assert result.degraded is False
    assert result.requires_human_handoff is False
    assert result.reply.startswith("We have manicures")


class TestJsonReplies:
    """qwen3-1.7b, live: once plain text was accepted, it sometimes wrote JSON."""

    async def _turn(self, *texts: str):
        from pydantic_ai.messages import ModelResponse, TextPart

        answers = list(texts)

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[TextPart(answers.pop(0))])

        return await _engine(model_override=FunctionModel(respond)).run_turn(
            agent_name="marketplace_agent",
            system_prompt="Be brief.",
            user_message="manicure?",
            deps=None,
            tools=[],
            locale="en",
            output_type=AgentOutput,
        )

    async def test_an_output_tool_call_written_as_text_is_unwrapped(self):
        written = (
            '{"name": "final_result", "arguments": {"reply": "The earliest is 09:45. '
            'Shall I book it?", "suggested_actions": []}}'
        )
        result = await self._turn(written)

        assert result.reply == "The earliest is 09:45. Shall I book it?"

    async def test_a_raw_tool_result_is_sent_back_for_prose(self):
        result = await self._turn(
            '{"businesses": [{"business_slug": "lumi-re-spa", "name": "Lumière Spa"}]}',
            "Lumière Spa in Riyadh offers manicures.",
        )

        assert result.reply == "Lumière Spa in Riyadh offers manicures."
