"""The inference engine's choice of model server. No database, no model server:
a `FunctionModel` stands in for the model, and an unused port for a dead server.
"""

import socket
from datetime import UTC, datetime

import pytest

from app.core import metrics
from app.modules.ai_agents import runtime
from app.modules.ai_agents.runtime import InferenceEngine, clean_reply
from app.modules.ai_agents.schemas import AgentOutput
from app.modules.ai_agents.tools.base import _local

pytest.importorskip("pydantic_ai")

from pydantic_ai.messages import ModelMessage, ModelRequest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel


def _engine(**overrides) -> InferenceEngine:
    kwargs = {
        "base_url": "http://llm:8000/v1",
        "routing_model": "qwen3-1.7b",
        "reasoning_model": "qwen3-1.7b",
    }
    kwargs.update(overrides)
    return InferenceEngine(**kwargs)


def _unused_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestVllm:
    def test_vllm_is_spoken_to_as_an_openai_compatible_server(self):
        model = _engine()._chat_model("qwen3-1.7b")

        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "qwen3-1.7b"
        assert str(model.client.base_url).startswith("http://llm:8000/v1")

    def test_thinking_is_read_where_vllms_reasoning_parser_puts_it(self):
        # A qwen3 reply's reasoning arrives in `reasoning_content`; read
        # anywhere else, it would be shown to the customer as the answer.
        model = _engine()._chat_model("qwen3-1.7b")

        assert model.profile.get("openai_chat_thinking_field") == "reasoning_content"

    def test_the_alias_picks_the_model_family(self):
        from pydantic_ai.profiles.qwen import qwen_model_profile

        model = _engine()._chat_model("Qwen3-1.7B")
        qwen = qwen_model_profile("qwen3-1.7b")

        assert model.profile.get("json_schema_transformer") is qwen.get("json_schema_transformer")

    def test_an_unknown_family_still_gets_a_schema_transformer(self):
        from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer

        model = _engine()._chat_model("phi-4")

        assert model.profile.get("json_schema_transformer") is OpenAIJsonSchemaTransformer


def _settings_seen(seen: list[dict]) -> FunctionModel:
    """A model that records the settings of each call and answers validly."""

    def respond(messages: list[ModelMessage], info: AgentInfo):
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        seen.append(dict(info.model_settings or {}))
        tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool.name, {"reply": "ok", "confidence": 0.9})])

    return FunctionModel(respond)


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
        # Thinking multiplied a qwen3-8b turn's time about fivefold in testing,
        # and the generic `reasoning_effort` switch was not honoured.
        assert (await self._instructions()).endswith("/no_think")

    async def test_thinking_can_be_turned_back_on(self):
        assert "/no_think" not in await self._instructions(thinking=True)

    async def test_other_families_are_left_alone(self):
        instructions = await self._instructions(routing_model="llama3.1:8b")

        assert "/no_think" not in instructions

    async def _settings(self, **engine) -> dict:
        seen: list[dict] = []
        await _engine(model_override=_settings_seen(seen), **engine).run_turn(
            agent_name="concierge_agent",
            system_prompt="Be brief.",
            user_message="hello",
            deps=None,
            tools=[],
            locale="en",
            output_type=AgentOutput,
        )
        return seen[-1]

    async def test_vllm_switches_thinking_off_in_the_chat_template(self):
        # The template's own switch writes an empty <think></think>, so the
        # model cannot think even if it ignores `/no_think`.
        settings = await self._settings()

        assert settings["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
        assert settings["max_tokens"] == runtime.MAX_TOKENS_PER_CALL

    async def test_vllm_leaves_the_template_alone_when_thinking_is_on(self):
        settings = await self._settings(thinking=True)

        assert "extra_body" not in settings

    async def test_other_families_get_no_template_switch(self):
        assert "extra_body" not in await self._settings(routing_model="llama3.1-8b")


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


class TestLocalTime:
    """A time ready to repeat, in the app's language (`tools/base._local`)."""

    MOMENT = datetime(2026, 9, 24, 17, 0, tzinfo=UTC)

    def test_english(self):
        assert _local(self.MOMENT, "Asia/Riyadh") == "Thu 24 Sep 2026, 20:00 (Asia/Riyadh)"

    def test_arabic_names_the_day_month_and_city(self):
        assert _local(self.MOMENT, "Asia/Riyadh", locale="ar") == (
            "الخميس 24 سبتمبر 2026، 20:00 (بتوقيت الرياض)"
        )

    def test_an_unknown_city_keeps_its_zone_name(self):
        assert _local(self.MOMENT, "Europe/London", locale="ar").endswith("(بتوقيت Europe/London)")


def _replies(*replies: str) -> FunctionModel:
    """A model that answers with each reply in turn, the last one for ever."""
    queue = list(replies)

    def respond(messages: list[ModelMessage], info: AgentInfo):
        from pydantic_ai.messages import ModelResponse, ToolCallPart

        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"reply": reply})])

    return FunctionModel(respond)


class TestReplyLanguage:
    async def _turn(self, *replies: str, locale: str = "ar"):
        return await _engine(model_override=_replies(*replies)).run_turn(
            agent_name="concierge_agent",
            system_prompt="Be brief.",
            user_message="hello",
            deps=None,
            tools=[],
            locale=locale,
            output_type=AgentOutput,
            reply_locale=locale,
        )

    async def test_a_wrong_language_is_sent_back_and_counted(self):
        metrics.reset()

        result = await self._turn("Hello, how can I help you today?", "مرحبًا، كيف أساعدك اليوم؟")

        assert result.reply == "مرحبًا، كيف أساعدك اليوم؟"
        assert (
            'nova_ai_output_retries_total{agent="concierge_agent",reason="language"} 1'
            in metrics.render()
        )

    async def test_echoed_markup_is_not_read_as_the_other_language(self):
        result = await self._turn("زاد دخلكم هذا الشهر. <chart_ids>revenue_trend</chart_ids>")

        assert result.requires_human_handoff is False
        assert result.reply == "زاد دخلكم هذا الشهر."
