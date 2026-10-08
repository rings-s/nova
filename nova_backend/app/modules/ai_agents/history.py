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
The marketplace assistant has no tenant yet: its key says `market` instead.

Beside the turns, a conversation keeps its **offers**: the slots an agent held
and showed the customer. `book_held_slot` may only book one of these, and only
one offered in an *earlier* turn — one the customer has seen and answered. The
offers hold hold tokens, so they live here, server-side and short-lived, and
never in the turns the model reads.

A person may ask for all of it to go (`forget_principal`): every conversation
and offer they have with any business or the marketplace. Unlike the rest of
this store, that one does not swallow a Redis failure. A "forget me" answered
"done" while the turns survive would be the one lie this store can tell.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationKey:
    #: None for the marketplace assistant, which works across tenants.
    tenant_id: UUID | None
    principal_id: UUID
    business_id: UUID | None
    session_id: str

    def storage_key(self) -> str:
        # Hashed, because the session id is text the client chose.
        session = hashlib.sha256(self.session_id.encode()).hexdigest()
        business = self.business_id or "-"
        tenant = self.tenant_id or "market"
        return f"ai:conversation:{tenant}:{self.principal_id}:{business}:{session}"

    def offers_key(self) -> str:
        return f"{self.storage_key()}:offers"


def principal_pattern(principal_id: UUID) -> str:
    """Every key one person's conversations and offers live under, as a glob."""
    return f"ai:conversation:*:{principal_id}:*"


class ConversationStore(Protocol):
    async def load(self, key: ConversationKey) -> list[bytes]:
        """The remembered turns, oldest first; empty when there are none."""
        ...

    async def append(self, key: ConversationKey, turn: bytes) -> None:
        """Remembers one more turn, forgetting the oldest beyond the limit."""
        ...

    async def load_offers(self, key: ConversationKey) -> bytes | None:
        """The slots offered in earlier turns, as the service encoded them."""
        ...

    async def save_offers(self, key: ConversationKey, offers: bytes, ttl_seconds: int) -> None:
        """Replaces the offers; they expire with the last hold they describe."""
        ...

    async def forget_principal(self, principal_id: UUID) -> int:
        """Deletes every conversation and offer of one person; how many keys.

        Raises when the store cannot be reached, rather than reporting nothing
        to delete.
        """
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

    async def load_offers(self, key: ConversationKey) -> bytes | None:
        if self._redis is None:
            return None
        try:
            value = await self._redis.get(key.offers_key())
        except Exception:
            logger.warning("ai_offers_unavailable", exc_info=True)
            return None
        return bytes(value) if value is not None else None

    async def save_offers(self, key: ConversationKey, offers: bytes, ttl_seconds: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key.offers_key(), offers, ex=max(1, ttl_seconds))
        except Exception:
            logger.warning("ai_offers_not_saved", exc_info=True)

    async def forget_principal(self, principal_id: UUID) -> int:
        if self._redis is None:
            raise ConnectionError("conversation memory has no Redis client")
        names = [
            name
            async for name in self._redis.scan_iter(
                match=principal_pattern(principal_id), count=500
            )
        ]
        for start in range(0, len(names), 500):
            await self._redis.unlink(*names[start : start + 500])
        return len(names)


class InMemoryConversationStore:
    """The same contract in one process, with no expiry. For tests."""

    def __init__(self, *, max_turns: int = 10) -> None:
        self._max_turns = max_turns
        self._turns: dict[str, list[bytes]] = {}
        self._offers: dict[str, bytes] = {}

    async def load(self, key: ConversationKey) -> list[bytes]:
        return list(self._turns.get(key.storage_key(), []))

    async def append(self, key: ConversationKey, turn: bytes) -> None:
        turns = self._turns.setdefault(key.storage_key(), [])
        turns.append(turn)
        del turns[: -self._max_turns]

    async def load_offers(self, key: ConversationKey) -> bytes | None:
        return self._offers.get(key.offers_key())

    async def save_offers(self, key: ConversationKey, offers: bytes, ttl_seconds: int) -> None:
        self._offers[key.offers_key()] = offers

    async def forget_principal(self, principal_id: UUID) -> int:
        marker = f":{principal_id}:"
        forgotten = 0
        for store in (self._turns, self._offers):
            for name in [name for name in store if marker in name]:
                del store[name]
                forgotten += 1
        return forgotten


__all__ = [
    "ConversationKey",
    "ConversationStore",
    "InMemoryConversationStore",
    "RedisConversationStore",
    "principal_pattern",
]
