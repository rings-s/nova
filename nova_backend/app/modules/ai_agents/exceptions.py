"""ai_agents · module errors.

The guardrail errors live in `guardrails.py` beside the rules they enforce
(`GuardrailError`, `GuardrailViolation`), and `AgentUnavailableError` lives in
`service.py` beside the registry it consults.
"""

from app.core.exceptions import DomainError
from app.modules.ai_agents.guardrails import GuardrailError, GuardrailViolation


class AiBusyError(DomainError):
    """The assistant is answering someone else; try again in a moment.

    Raised by `concurrency.InferenceGate` when the model server's slots are all
    taken for longer than the queue wait, or the caller already has a turn
    running. Retryable: nothing was done.
    """

    status_code = 429
    code = "ai_busy"


class AiMemoryUnavailableError(DomainError):
    """Conversation memory could not be reached, so nothing was forgotten.

    Only a request to forget raises it. A turn that cannot reach memory starts
    fresh instead (`history.py`), but a "forget me" must not answer done.
    """

    status_code = 503
    code = "ai_memory_unavailable"
    retryable = True


__all__ = ["AiBusyError", "AiMemoryUnavailableError", "GuardrailError", "GuardrailViolation"]
