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


__all__ = ["AiBusyError", "GuardrailError", "GuardrailViolation"]
