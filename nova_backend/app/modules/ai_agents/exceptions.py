"""ai_agents · module errors.

The guardrail errors live in `guardrails.py` beside the rules they enforce
(`GuardrailError`, `GuardrailViolation`), and `AgentUnavailableError` lives in
`service.py` beside the registry it consults.
"""

from app.modules.ai_agents.guardrails import GuardrailError, GuardrailViolation

__all__ = ["GuardrailError", "GuardrailViolation"]
