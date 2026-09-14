"""ai_agents · INFRASTRUCTURE — conversation memory.

A turn used to start from nothing: the model saw only the newest message, so a
receptionist that had just offered three times could not hold "the second one",
and a customer who named their booking once had to name it again.

This keeps a conversation's recent turns as PydanticAI's own message JSON
(`runtime.py` does the encoding, so this file never imports PydanticAI) and
hands them to the next turn. It stores what the model saw: the message after PII
redaction, and tool results, which carry no customer contact details and no
hold token.

Redis rather than Postgres, because a chat is working memory rather than a
record: it expires after `ai_history_ttl_seconds`, keeps the last
`ai_history_max_turns` turns, and nothing else reads it. Losing it costs a
customer repeating themselves, not a booking, so an unreachable Redis means a
turn that starts fresh, never one that fails.

A conversation is keyed by tenant, principal and business as well as by the
client's `session_id`. A guessed session id opens nobody else's conversation,
and an owner's questions about one business never ground a figure about another.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationKey:
    tenant_id: UUID
    principal_id: UUID
    business_id: UUID | None
    session_id: str

    def storage_key(self) -> str:
        # Hashed, because the session id is text the client chose.
        session = hashlib.sha256(self.session_id.encode()).hexdigest()
        business = self.business_id or "-"
        return f"ai:conversation:{self.tenant_id}:{self.principal_id}:{business}:{session}"


class ConversationStore(Protocol):
    async def load(self, key: ConversationKey) -> list[bytes]:
        """The remembered turns, oldest first; empty when there are none."""
        ...

    async def append(self, key: ConversationKey, turn: bytes) -> None:
        """Remembers one more turn, forgetting the oldest beyond the limit."""
        ...


class RedisConversationStore:
    def __init__(self, redis: Any, *, ttl_seconds: int, max_turns: int) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns

    @classmethod
    def from_url(cls, url: str, *, ttl_seconds: int, max_turns: int) -> "RedisConversationStore":
        try:
            from redis.asyncio import Redis

            client: Any = Redis.from_url(url)
        except Exception:
            logger.warning("ai_history_client_unavailable", exc_info=True)
            client = None
        return cls(client, ttl_seconds=ttl_seconds, max_turns=max_turns)

    async def load(self, key: ConversationKey) -> list[bytes]:
        if self._redis is None:
            return []
        try:
            return list(await self._redis.lrange(key.storage_key(), 0, -1))
        except Exception:
            logger.warning("ai_history_unavailable", exc_info=True)
            return []

    async def append(self, key: ConversationKey, turn: bytes) -> None:
        if self._redis is None:
            return
        name = key.storage_key()
        try:
            pipe = self._redis.pipeline()
            pipe.rpush(name, turn)
            pipe.ltrim(name, -self._max_turns, -1)
            pipe.expire(name, self._ttl_seconds)
            await pipe.execute()
        except Exception:
            logger.warning("ai_history_not_saved", exc_info=True)


class InMemoryConversationStore:
    """The same contract in one process, with no expiry. For tests."""

    def __init__(self, *, max_turns: int = 10) -> None:
        self._max_turns = max_turns
        self._turns: dict[str, list[bytes]] = {}

    async def load(self, key: ConversationKey) -> list[bytes]:
        return list(self._turns.get(key.storage_key(), []))

    async def append(self, key: ConversationKey, turn: bytes) -> None:
        turns = self._turns.setdefault(key.storage_key(), [])
        turns.append(turn)
        del turns[: -self._max_turns]


__all__ = [
    "ConversationKey",
    "ConversationStore",
    "InMemoryConversationStore",
    "RedisConversationStore",
]
