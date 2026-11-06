"""support · DOMAIN layer — what a follow-up records.

Pure-function style: a follow-up is open or resolved, so the ORM model is the
entity and these are its field rules.
"""

import hashlib
from enum import StrEnum
from uuid import UUID


class FollowUpSource(StrEnum):
    CHAT = "chat"
    CALL = "call"


class FollowUpReason(StrEnum):
    """Why a person has to get back to the customer."""

    #: The agent handed off with a summary (`escalate_to_human`).
    ESCALATED = "escalated"
    #: The agent said it could not help, without a summary.
    AGENT_COULD_NOT_HELP = "agent_could_not_help"
    #: No model could answer, and the customer was told a person would.
    ASSISTANT_UNAVAILABLE = "assistant_unavailable"
    #: Sara could not send the caller their verification code.
    CODE_NOT_SENT = "code_not_sent"
    #: The caller pressed 2 to cancel and the booking could not be cancelled.
    CANCELLATION_FAILED = "cancellation_failed"
    #: The call reached its turn cap before the caller was helped.
    CALL_TOO_LONG = "call_too_long"


class FollowUpStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


#: Longest summary or customer message kept. Enough to act on, not a transcript.
MAX_TEXT_LENGTH = 1000


def clip_text(text: str | None) -> str | None:
    """Trimmed and cut to `MAX_TEXT_LENGTH`, or None for nothing worth keeping."""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    return text[:MAX_TEXT_LENGTH]


def chat_reference(principal_id: UUID, business_id: UUID | None, session_id: str) -> str:
    """One conversation, as a follow-up names it: a hash, so the client's own
    session id is never stored, and every handoff in it updates one follow-up."""
    raw = f"{principal_id}:{business_id or ''}:{session_id}"
    return hashlib.sha256(raw.encode()).hexdigest()
