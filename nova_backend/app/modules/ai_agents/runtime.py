"""ai_agents · INFRASTRUCTURE — the inference engine adapter.

PydanticAI and the model server are reached through this file and nowhere else, for two
reasons:

  1. docs/10 section 12 requires the whole platform to keep working with every
     agent offline: "the booking, queue, and payment flows must remain fully
     usable with every agent offline." That is only true if the inference
     dependency is optional at import time, not just at call time.
  2. PydanticAI is deliberately not a runtime dependency in `pyproject.toml`
     (install with `uv sync --extra ai`). A local-first deployment that never
     enables AI should not carry the inference stack. The dev group installs it
     so the tests exercise the real library.

So the import is deferred to the turn, and everything degrades to a static
reply with `requires_human_handoff=True` rather than raising.

Conversation memory is encoded here as well, as PydanticAI's own message JSON,
so `history.py` stores bytes and never imports the library either.

The one model server is vLLM (ADR-0019): the compose `llm` service, in every
environment, on a GPU where there is one and on vLLM's CPU build otherwise.
llama.cpp served the models from 2026-10-23 to 2026-10-28 (ADR-0018), and
Ollama, LM Studio and hosted servers before that; none is supported now. vLLM
speaks the OpenAI chat protocol at /v1, so `_chat_model` is an
`OpenAIChatModel` with the model family's profile. Sara's voice model
(`build_voice_inference_engine`, ADR-0017) is vLLM too, at its own
`VOICE_AI_BASE_URL` if a faster one is run for her.

PydanticAI 2.x is the target: `OpenAIChatModel` with `OpenAIProvider`. Until
ADR-0011 this file imported `OpenAIModel`, which 2.x no longer has; the
ImportError happened inside the turn, read as an ordinary inference failure,
and every chat handed off to a human. Tests now inject a `FunctionModel`
through `model_override`, so the next rename fails a build instead.
"""

import asyncio
import importlib.util
import json
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.core import metrics

if TYPE_CHECKING:
    from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

PYDANTIC_AI_AVAILABLE = importlib.util.find_spec("pydantic_ai") is not None

#: How long a reachability answer is reused. A client asks on every page that
#: shows a chat; the model server should not see a request for each one.
_PROBE_TTL_SECONDS = 15.0
_probe_cache: dict[str, tuple[float, bool]] = {}

#: Model families that take Qwen3's `/no_think` soft switch in the prompt. It
#: is the one switch every Qwen3 chat template honours; the OpenAI
#: `reasoning_effort` parameter did not finish a turn in testing. vLLM also
#: gets the chat template's hard switch (`_model_settings`).
_NO_THINK_FAMILIES = ("qwen3",)

#: Small models sometimes repeat a structured field in the reply text as markup
#: (`<chart_ids>nova_charges</chart_ids>`). The field itself is what counts
#: (the service keeps only ids a tool produced), so the echo is removed.
_ECHOED_FIELDS = re.compile(
    r"<(chart_ids|metrics_used|proposed_action_ids|suggested_actions)>.*?</\1>", re.DOTALL
)


def reply_from_json(text: str) -> str | None:
    """The reply inside a JSON answer: `{"reply": …}`, or an output-tool call
    written out as text, `{"name": "final_result", "arguments": {"reply": …}}`."""
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`").removeprefix("json").strip()
    if not body.startswith("{"):
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if isinstance(data, dict) and isinstance(data.get("arguments"), dict):
        data = data["arguments"]
    if isinstance(data, dict) and isinstance(data.get("reply"), str) and data["reply"].strip():
        return str(data["reply"])
    return None


def clean_reply(reply: str) -> str:
    text = _ECHOED_FIELDS.sub("", reply)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"[ \t]+\n", "\n", text).strip()


#: A looping model must not be able to hold the GPU (ADR-0011).
REQUEST_LIMIT = 8
TOOL_CALLS_LIMIT = 12
#: Tokens one model call may generate. A tool call needs under a hundred and a
#: reply a few hundred; a small model left unbounded wrote 500-token preambles
#: before its tool calls, over a minute each on a CPU.
MAX_TOKENS_PER_CALL = 600

#: What a customer sees when inference is unavailable. Deliberately not an
#: error message: the customer did nothing wrong, and a salon's chat saying
#: "500 Internal Server Error" is worse than one saying "someone will reply".
_FALLBACK_REPLY = {
    "ar": "سنحوّلك إلى أحد موظفينا للمساعدة. شكراً لصبرك.",
    "en": "I'm handing you to a member of our team who can help. Thanks for your patience.",
}


@dataclass(frozen=True)
class InferenceResult:
    reply: str
    suggested_actions: list[str]
    requires_human_handoff: bool
    confidence: float
    model_used: str | None = None
    degraded: bool = False
    #: Ids the model referenced. The service keeps only those a tool produced.
    chart_ids: tuple[str, ...] = ()
    metrics_used: tuple[str, ...] = ()
    proposed_action_ids: tuple[str, ...] = ()
    #: This turn's messages, encoded for conversation memory. None when no
    #: model answered, so a fallback reply is never remembered as the model's.
    new_turn: bytes | None = None


def fallback_result(*, locale: str = "ar", reason: str = "unavailable") -> InferenceResult:
    """The response when no model can answer.

    docs/10 section 12, first row: "model server unreachable -> endpoint returns
    `requires_human_handoff=True` with a static reply."
    """
    logger.info("ai_fallback", extra={"reason": reason})
    return InferenceResult(
        reply=_FALLBACK_REPLY.get(locale, _FALLBACK_REPLY["en"]),
        suggested_actions=[],
        requires_human_handoff=True,
        confidence=0.0,
        model_used=None,
        degraded=True,
    )


class InferenceEngine:
    """Runs one agent turn, with the fallback matrix from docs/10 section 12."""

    def __init__(
        self,
        *,
        base_url: str,
        routing_model: str,
        api_key: str | None = None,
        thinking: bool = False,
        reasoning_model: str,
        request_timeout_seconds: float = 30.0,
        tool_timeout_seconds: float = 5.0,
        enabled: bool = True,
        model_override: Any | None = None,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.thinking = thinking
        self.routing_model = routing_model
        self.reasoning_model = reasoning_model
        self.request_timeout_seconds = request_timeout_seconds
        self.tool_timeout_seconds = tool_timeout_seconds
        self.enabled = enabled
        #: A PydanticAI model instance used instead of the model server. Tests pass a
        #: `FunctionModel`; production leaves it None.
        self.model_override = model_override

    @property
    def available(self) -> bool:
        """Whether a turn can even be attempted."""
        return self.enabled and PYDANTIC_AI_AVAILABLE

    async def reachable(self) -> bool:
        """Whether the model server answers at all, so a client can hide a chat
        that would only hand off. A short, cached `GET /models`; never raises.
        A test engine with `model_override` needs no server."""
        if not self.available:
            return False
        if self.model_override is not None:
            return True
        now = time.monotonic()
        cached = _probe_cache.get(self.base_url)
        if cached is not None and now - cached[0] < _PROBE_TTL_SECONDS:
            return cached[1]

        import httpx

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url.rstrip('/')}/models", headers=headers)
            ok = response.status_code == 200
        except httpx.HTTPError:
            ok = False
        _probe_cache[self.base_url] = (now, ok)
        return ok

    def _chat_model(self, model: str) -> Any:
        """The PydanticAI model for the vLLM server."""
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.profiles import merge_profile
        from pydantic_ai.profiles.deepseek import deepseek_model_profile
        from pydantic_ai.profiles.google import google_model_profile
        from pydantic_ai.profiles.meta import meta_model_profile
        from pydantic_ai.profiles.mistral import mistral_model_profile
        from pydantic_ai.profiles.openai import OpenAIJsonSchemaTransformer, OpenAIModelProfile
        from pydantic_ai.profiles.qwen import qwen_model_profile
        from pydantic_ai.providers.openai import OpenAIProvider

        # vLLM names the model by its `--served-model-name` (`qwen3-4b`), and the
        # family decides the profile.
        families = {
            "qwen": qwen_model_profile,
            "llama": meta_model_profile,
            "gemma": google_model_profile,
            "deepseek": deepseek_model_profile,
            "mistral": mistral_model_profile,
        }
        name = model.lower()
        family = next((f(name) for prefix, f in families.items() if name.startswith(prefix)), None)
        profile = merge_profile(
            # A fallback: the family's own transformer wins if it has one.
            OpenAIModelProfile(json_schema_transformer=OpenAIJsonSchemaTransformer),
            family,
            OpenAIModelProfile(
                # Where vLLM's qwen3 reasoning parser puts the thinking; read
                # anywhere else, it would be shown as the answer.
                openai_chat_thinking_field="reasoning_content",
                openai_supports_strict_tool_definition=False,
                supports_json_schema_output=True,
                supports_json_object_output=True,
            ),
        )
        # The OpenAI client insists on a key; vLLM ignores it unless
        # started with one.
        provider = OpenAIProvider(base_url=self.base_url, api_key=self.api_key or "vllm")
        return OpenAIChatModel(model, provider=provider, profile=profile)

    def _model_settings(self, model: str) -> "ModelSettings":
        """Per-call settings. A Qwen3 model's thinking is also switched off in
        its chat template (`enable_thinking`), which writes an empty
        `<think></think>` rather than asking the model to skip it."""
        settings: ModelSettings = {"max_tokens": MAX_TOKENS_PER_CALL}
        if not self.thinking and any(f in model.lower() for f in _NO_THINK_FAMILIES):
            settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        return settings

    async def run_turn(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_message: str,
        deps: Any,
        tools: list[Any],
        locale: str = "ar",
        prefer_reasoning_model: bool = False,
        output_type: type | None = None,
        grounded: bool = False,
        history: Sequence[bytes] = (),
        before_attempt: Callable[[], None] | None = None,
        retry_is_safe: Callable[[], bool] | None = None,
        reply_locale: str | None = None,
    ) -> InferenceResult:
        """Attempts one turn, degrading rather than failing.

        The escalation path mirrors docs/10 section 12 exactly:
          - engine unavailable          -> static reply, handoff
          - reasoning model unavailable -> retry on the routing model, flagged
                                           as reduced confidence
          - timeout or any other error  -> static reply, handoff

        "Any other error" includes a reply that failed the grounding check
        twice, and a turn that hit its usage limits.

        The retry starts the turn over, and a tool's writes commit as it
        returns. So the retry is skipped when `retry_is_safe` says the failed
        attempt already wrote: a second attempt would hold the slot or join the
        queue again. `before_attempt` runs before each attempt, so the caller
        can clear what the last one presented.

        `history` is the conversation's earlier turns, each as `new_turn` bytes
        from a previous result.

        `reply_locale`, when given, is the app's language: a reply written in
        the other one is sent back to the model once to be rewritten, and a
        second one fails the turn, so it is never shown.
        """
        if not self.available:
            return fallback_result(
                locale=locale,
                reason="pydantic_ai_not_installed" if self.enabled else "ai_disabled",
            )

        primary = self.reasoning_model if prefer_reasoning_model else self.routing_model
        attempt = {
            "agent_name": agent_name,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "deps": deps,
            "tools": tools,
            "output_type": output_type,
            "grounded": grounded,
            "history": history,
            "reply_locale": reply_locale,
        }

        if before_attempt is not None:
            before_attempt()
        try:
            return await asyncio.wait_for(
                self._invoke(model=primary, **attempt), timeout=self.request_timeout_seconds
            )
        except TimeoutError:
            logger.warning("ai_turn_timeout", extra={"agent": agent_name, "model": primary})
            return fallback_result(locale=locale, reason="timeout")
        except Exception:
            logger.warning(
                "ai_primary_model_failed",
                extra={"agent": agent_name, "model": primary},
                exc_info=True,
            )

        if not prefer_reasoning_model or self.routing_model == self.reasoning_model:
            # Retrying on the same model repeats the failure and doubles the
            # wait: on a laptop running one small model for both roles, a turn
            # took two full timeouts before handing off.
            return fallback_result(locale=locale, reason="inference_failed")
        if retry_is_safe is not None and not retry_is_safe():
            logger.warning("ai_retry_skipped_after_write", extra={"agent": agent_name})
            return fallback_result(locale=locale, reason="write_committed")

        # docs/10 section 12, second row: the 70b model may simply not fit in
        # VRAM alongside whatever else the GPU is doing. Falling back to the 8b
        # is far better than handing off, but the answer is worth less and the
        # caller is told so.
        if before_attempt is not None:
            before_attempt()
        try:
            degraded = await asyncio.wait_for(
                self._invoke(model=self.routing_model, **attempt),
                timeout=self.request_timeout_seconds,
            )
        except Exception:
            logger.warning("ai_fallback_model_failed", extra={"agent": agent_name}, exc_info=True)
            return fallback_result(locale=locale, reason="inference_failed")

        # Halved rather than zeroed: the answer is real, just less reliable.
        return replace(
            degraded,
            confidence=degraded.confidence * 0.5,
            model_used=self.routing_model,
            degraded=True,
        )

    async def _invoke(
        self,
        *,
        agent_name: str,
        model: str,
        system_prompt: str,
        user_message: str,
        deps: Any,
        tools: list[Any],
        output_type: type | None,
        grounded: bool,
        history: Sequence[bytes],
        reply_locale: str | None = None,
    ) -> InferenceResult:
        """The one place PydanticAI is actually called."""
        from pydantic_ai import Agent, ModelRetry, RunContext
        from pydantic_ai.messages import ModelMessagesTypeAdapter, ToolReturnPart
        from pydantic_ai.usage import UsageLimits

        from app.modules.ai_agents.guardrails import (
            find_ungrounded_numbers,
            grounded_values_in_result,
            in_wrong_language,
        )
        from app.modules.ai_agents.schemas import AgentOutput

        message_history: list[Any] = []
        for turn in history:
            try:
                message_history.extend(ModelMessagesTypeAdapter.validate_json(turn))
            except ValueError:
                # Each turn is whole on its own, so one this version cannot read
                # is forgotten without breaking the turns around it.
                logger.warning("ai_history_turn_unreadable", extra={"agent": agent_name})

        if grounded:
            # A figure a tool returned earlier in this conversation is still a
            # figure a tool returned.
            for message in message_history:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        deps.artifacts.grounded_values |= grounded_values_in_result(part.content)

        chat_model = self.model_override or self._chat_model(model)
        if not self.thinking and any(f in model.lower() for f in _NO_THINK_FAMILIES):
            system_prompt = f"{system_prompt}\n\n/no_think"
        agent: Agent[Any, Any] = Agent(
            chat_model,
            name=agent_name,
            deps_type=type(deps),
            # Plain text is accepted as the reply too. A small model often
            # answers in prose instead of calling the output tool, and prose is
            # a fine reply; refusing it turned good answers into handoffs.
            output_type=[output_type or AgentOutput, str],
            instructions=system_prompt,
            tools=tools,
            # docs/10 section 11: output that fails validation is retried once,
            # then handed to a human.
            retries=1,
        )

        def retry(reason: str, message: str) -> Exception:
            """A reply sent back to the model, counted: how often a model needs
            correcting is the first sign a model or prompt change made it worse."""
            metrics.count("nova_ai_output_retries_total", agent=agent_name, reason=reason)
            return ModelRetry(message)

        @agent.output_validator
        async def readable(ctx: RunContext[Any], output: Any) -> Any:
            """Prose for the customer, never JSON. Live, qwen3-1.7b answered with
            its output-tool call written out as text, or with a tool's raw result."""
            if not isinstance(output, str):
                return output
            reply = reply_from_json(output)
            if reply is not None:
                return reply
            if output.strip().lstrip("`").startswith(("{", "[", "json")):
                raise retry("json", "Answer the customer in plain sentences, not JSON.")
            return output

        if reply_locale is not None:
            language = "Arabic" if reply_locale == "ar" else "English"

            @agent.output_validator
            async def in_app_language(ctx: RunContext[Any], output: Any) -> Any:
                """The reply is in the app's language, whatever the customer wrote in.
                Asked for in the instructions; a small model still answered an
                English question in English in an Arabic app."""
                texts = [output] if isinstance(output, str) else [output.reply]
                if not isinstance(output, str):
                    texts += output.suggested_actions
                # Judged as the customer will see it: without echoed field
                # markup (`<chart_ids>…`), which is Latin in any language.
                if any(in_wrong_language(clean_reply(text), reply_locale) for text in texts):
                    raise retry(
                        "language",
                        f"The app is set to {language}. Write the whole reply again in "
                        f"{language} only.",
                    )
                return output

        if grounded:

            @agent.output_validator
            async def only_grounded_numbers(ctx: RunContext[Any], output: Any) -> Any:
                """docs/13 section 5.2: every figure in the reply came from a tool."""
                text = output if isinstance(output, str) else output.reply
                ungrounded = find_ungrounded_numbers(text, ctx.deps.artifacts.grounded_values)
                if ungrounded:
                    raise retry(
                        "ungrounded",
                        "These figures did not come from any tool in this conversation: "
                        f"{', '.join(ungrounded)}. Call a tool for them, or leave them out.",
                    )
                return output

        run = await agent.run(
            user_message,
            deps=deps,
            message_history=message_history or None,
            usage_limits=UsageLimits(
                request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT
            ),
            model_settings=self._model_settings(model),
        )
        output = run.output
        if isinstance(output, str):
            return InferenceResult(
                reply=clean_reply(output),
                suggested_actions=[],
                requires_human_handoff=False,
                # Unstructured, so it carries no confidence of its own.
                confidence=0.5,
                model_used=model if self.model_override is None else chat_model.model_name,
                new_turn=run.new_messages_json(),
            )

        return InferenceResult(
            reply=clean_reply(output.reply),
            suggested_actions=list(output.suggested_actions),
            requires_human_handoff=output.requires_human_handoff,
            confidence=output.confidence,
            model_used=model if self.model_override is None else chat_model.model_name,
            degraded=False,
            chart_ids=tuple(getattr(output, "chart_ids", ())),
            metrics_used=tuple(getattr(output, "metrics_used", ())),
            proposed_action_ids=tuple(getattr(output, "proposed_action_ids", ())),
            new_turn=run.new_messages_json(),
        )


def build_inference_engine(settings) -> InferenceEngine:
    return InferenceEngine(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        thinking=settings.ai_thinking,
        routing_model=settings.ai_routing_model,
        reasoning_model=settings.ai_reasoning_model,
        request_timeout_seconds=settings.ai_request_timeout_seconds,
        tool_timeout_seconds=settings.ai_tool_timeout_seconds,
        enabled=settings.ai_enabled,
    )


def build_voice_inference_engine(settings) -> InferenceEngine:
    """Sara's engine (ADR-0017): one fast model for every turn, short timeouts.

    A caller waits in silence while the model thinks, so the voice model is its
    own setting rather than the chat agents' local one. Each `VOICE_AI_*` value
    left unset falls back to its `AI_*` setting.
    """
    model = settings.voice_ai_model or settings.ai_routing_model
    return InferenceEngine(
        base_url=settings.voice_ai_base_url or settings.ai_base_url,
        api_key=settings.voice_ai_api_key or settings.ai_api_key,
        thinking=False,
        routing_model=model,
        reasoning_model=model,
        request_timeout_seconds=settings.voice_ai_request_timeout_seconds,
        tool_timeout_seconds=settings.voice_ai_tool_timeout_seconds,
        enabled=settings.ai_enabled,
    )
