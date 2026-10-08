"""Conversation memory (`ai_agents/history.py`). No database.

The last test needs a real Redis. It runs inside the compose stack and is
skipped wherever Redis is not reachable, CI included.
"""

import os
from uuid import uuid4

import pytest

from app.modules.ai_agents.history import (
    ConversationKey,
    InMemoryConversationStore,
    RedisConversationStore,
)


def _key(**overrides) -> ConversationKey:
    fields = {
        "tenant_id": uuid4(),
        "principal_id": uuid4(),
        "business_id": None,
        "session_id": "chat-1",
    }
    fields.update(overrides)
    return ConversationKey(**fields)


def test_a_guessed_session_id_opens_nobody_elses_conversation():
    mine = _key()
    someone_else = _key(tenant_id=mine.tenant_id, session_id=mine.session_id)
    assert mine.storage_key() != someone_else.storage_key()


def test_one_business_conversation_never_grounds_another():
    about_one = _key(business_id=uuid4())
    about_another = _key(
        tenant_id=about_one.tenant_id,
        principal_id=about_one.principal_id,
        business_id=uuid4(),
        session_id=about_one.session_id,
    )
    assert about_one.storage_key() != about_another.storage_key()


def test_the_client_chosen_session_id_is_not_written_into_the_key():
    key = _key(session_id="text the client chose")
    assert key.session_id not in key.storage_key()


async def test_memory_keeps_the_most_recent_turns_in_order():
    store = InMemoryConversationStore(max_turns=3)
    key = _key()
    for n in range(5):
        await store.append(key, f"turn {n}".encode())
    assert await store.load(key) == [b"turn 2", b"turn 3", b"turn 4"]


async def test_with_no_redis_client_every_turn_starts_fresh():
    store = RedisConversationStore(None, ttl_seconds=60, max_turns=3)
    key = _key()
    await store.append(key, b"turn")
    assert await store.load(key) == []


async def test_an_unreachable_redis_is_a_fresh_start_not_an_error():
    store = RedisConversationStore.from_url("redis://127.0.0.1:1/0", ttl_seconds=60, max_turns=3)
    key = _key()
    await store.append(key, b"turn")
    assert await store.load(key) == []


async def test_redis_keeps_the_last_turns_and_forgets_them_in_time():
    from redis.asyncio import Redis

    client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("Redis is not reachable here")

    store = RedisConversationStore(client, ttl_seconds=60, max_turns=3)
    key = _key()
    try:
        for n in range(5):
            await store.append(key, f"turn {n}".encode())
        assert await store.load(key) == [b"turn 2", b"turn 3", b"turn 4"]
        assert 0 < await client.ttl(key.storage_key()) <= 60
    finally:
        await client.delete(key.storage_key())
        await client.aclose()


async def test_forgetting_a_person_removes_their_conversations_everywhere_and_no_one_elses():
    store = InMemoryConversationStore()
    me = uuid4()
    at_a_salon = _key(principal_id=me)
    at_the_marketplace = _key(tenant_id=None, principal_id=me, session_id="market-1")
    someone_else = _key(tenant_id=at_a_salon.tenant_id, session_id=at_a_salon.session_id)
    for key in (at_a_salon, at_the_marketplace, someone_else):
        await store.append(key, b"turn")
    await store.save_offers(at_a_salon, b"offers", ttl_seconds=60)

    assert await store.forget_principal(me) == 3

    assert await store.load(at_a_salon) == []
    assert await store.load(at_the_marketplace) == []
    assert await store.load_offers(at_a_salon) is None
    assert await store.load(someone_else) == [b"turn"]


async def test_forgetting_without_redis_raises_rather_than_reporting_nothing_to_forget():
    """A turn may start fresh without Redis; a "forget me" must not answer done."""
    store = RedisConversationStore(None, ttl_seconds=60, max_turns=3)
    with pytest.raises(ConnectionError):
        await store.forget_principal(uuid4())

    unreachable = RedisConversationStore.from_url(
        "redis://127.0.0.1:1/0", ttl_seconds=60, max_turns=3
    )
    with pytest.raises(Exception):  # noqa: B017 - whatever the client raises
        await unreachable.forget_principal(uuid4())


async def test_redis_forgets_one_person_at_every_business_and_keeps_everyone_else():
    from redis.asyncio import Redis

    client = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        pytest.skip("Redis is not reachable here")

    store = RedisConversationStore(client, ttl_seconds=60, max_turns=3)
    me = uuid4()
    mine = [_key(principal_id=me), _key(tenant_id=None, principal_id=me)]
    theirs = _key()
    try:
        for key in [*mine, theirs]:
            await store.append(key, b"turn")
        await store.save_offers(mine[0], b"offers", ttl_seconds=60)

        assert await store.forget_principal(me) == 3

        for key in mine:
            assert await client.exists(key.storage_key(), key.offers_key()) == 0
        assert await store.load(theirs) == [b"turn"]
    finally:
        await client.delete(*(key.storage_key() for key in [*mine, theirs]), mine[0].offers_key())
        await client.aclose()
