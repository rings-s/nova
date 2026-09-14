"""ai_agents · INFRASTRUCTURE — the inference engine adapter.

PydanticAI and Ollama are reached through this file and nowhere else, for two
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

PydanticAI 2.x is the target: `OpenAIChatModel` with `OllamaProvider`. Until
ADR-0011 this file imported `OpenAIModel`, which 2.x no longer has; the
ImportError happened inside the turn, read as an ordinary inference failure,
and every chat handed off to a human. Tests now inject a `FunctionModel`
through `model_override`, so the next rename fails a build instead.
"""

import asyncio
import importlib.util
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

logger = logging.getLogger(__name__)

PYDANTIC_AI_AVAILABLE = importlib.util.find_spec("pydantic_ai") is not None

#: A looping model must not be able to hold the GPU (ADR-0011).
REQUEST_LIMIT = 8
TOOL_CALLS_LIMIT = 12

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

    docs/10 section 12, first row: "Ollama unreachable -> endpoint returns
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
        reasoning_model: str,
        request_timeout_seconds: float = 30.0,
        tool_timeout_seconds: float = 5.0,
        enabled: bool = True,
        model_override: Any | None = None,
    ) -> None:
        self.base_url = base_url
        self.routing_model = routing_model
        self.reasoning_model = reasoning_model
        self.request_timeout_seconds = request_timeout_seconds
        self.tool_timeout_seconds = tool_timeout_seconds
        self.enabled = enabled
        #: A PydanticAI model instance used instead of Ollama. Tests pass a
        #: `FunctionModel`; production leaves it None.
        self.model_override = model_override

    @property
    def available(self) -> bool:
        """Whether a turn can even be attempted."""
        return self.enabled and PYDANTIC_AI_AVAILABLE

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

        if not prefer_reasoning_model:
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
    ) -> InferenceResult:
        """The one place PydanticAI is actually called."""
        from pydantic_ai import Agent, ModelRetry, RunContext
        from pydantic_ai.messages import ModelMessagesTypeAdapter, ToolReturnPart
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.ollama import OllamaProvider
        from pydantic_ai.usage import UsageLimits

        from app.modules.ai_agents.guardrails import (
            find_ungrounded_numbers,
            grounded_values_in_result,
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

        # Ollama speaks the OpenAI chat protocol at /v1.
        chat_model = self.model_override or OpenAIChatModel(
            model, provider=OllamaProvider(base_url=self.base_url)
        )
        agent: Agent[Any, Any] = Agent(
            chat_model,
            name=agent_name,
            deps_type=type(deps),
            output_type=output_type or AgentOutput,
            instructions=system_prompt,
            tools=tools,
            # docs/10 section 11: output that fails validation is retried once,
            # then handed to a human.
            retries=1,
        )

        if grounded:

            @agent.output_validator
            async def only_grounded_numbers(ctx: RunContext[Any], output: Any) -> Any:
                """docs/13 section 5.2: every figure in the reply came from a tool."""
                ungrounded = find_ungrounded_numbers(
                    output.reply, ctx.deps.artifacts.grounded_values
                )
                if ungrounded:
                    raise ModelRetry(
                        "These figures did not come from any tool in this conversation: "
                        f"{', '.join(ungrounded)}. Call a tool for them, or leave them out."
                    )
                return output

        run = await agent.run(
            user_message,
            deps=deps,
            message_history=message_history or None,
            usage_limits=UsageLimits(
                request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT
            ),
        )
        output = run.output

        return InferenceResult(
            reply=output.reply,
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
        base_url=settings.ollama_base_url,
        routing_model=settings.ai_routing_model,
        reasoning_model=settings.ai_reasoning_model,
        request_timeout_seconds=settings.ai_request_timeout_seconds,
        tool_timeout_seconds=settings.ai_tool_timeout_seconds,
        enabled=settings.ai_enabled,
    )
