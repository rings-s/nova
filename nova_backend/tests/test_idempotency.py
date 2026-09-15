"""Idempotency keys against the database: replay, expiry and scope.

The HTTP contract (a replay returns the first booking, a changed body is 422)
is covered in tests/test_customer_journey.py. These pin what `begin_idempotent`
does with a row its lookup cannot see: an expired key still holds its unique
slot until the nightly purge deletes it, so reusing the key must clear it first.
Needs Postgres.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.idempotency import IdempotencyKey, begin_idempotent, complete_idempotent

BODY = {"service_id": "a-service", "starts_at": "2026-10-01T09:00:00+00:00"}


def a_caller() -> dict[str, Any]:
    return {
        "key": "tap-once",
        "endpoint": "POST /bookings",
        "tenant_id": uuid4(),
        "principal_id": uuid4(),
    }


async def use_key(session: AsyncSession, caller: dict[str, Any]) -> None:
    """One request through the key: claimed, handled, its response stored."""
    assert await begin_idempotent(session, body=BODY, **caller) == (True, None, None)
    await complete_idempotent(session, status_code=201, body={"id": "first"}, **caller)


async def expire(session: AsyncSession, caller: dict[str, Any]) -> None:
    await session.execute(
        update(IdempotencyKey)
        .where(
            IdempotencyKey.idempotency_key == caller["key"],
            IdempotencyKey.principal_id == caller["principal_id"],
        )
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )


async def test_an_unexpired_key_replays_the_stored_response(db_session: AsyncSession):
    caller = a_caller()
    await use_key(db_session, caller)

    replay = await begin_idempotent(db_session, body=BODY, **caller)

    assert replay == (False, {"id": "first"}, 201)


async def test_a_key_reused_after_it_expired_runs_the_request_again(db_session: AsyncSession):
    """The expired row is invisible to the lookup but still holds the unique slot.

    Left in place, the new claim failed on the constraint, and the caller got a
    409 `duplicate_value` until the nightly purge happened to delete the row.
    """
    caller = a_caller()
    await use_key(db_session, caller)
    await expire(db_session, caller)

    assert await begin_idempotent(db_session, body=BODY, **caller) == (True, None, None)


async def test_clearing_an_expired_key_leaves_other_callers_rows(db_session: AsyncSession):
    mine = a_caller()
    theirs = {**mine, "principal_id": uuid4()}
    await use_key(db_session, mine)
    await use_key(db_session, theirs)
    await expire(db_session, mine)
    await expire(db_session, theirs)

    await begin_idempotent(db_session, body=BODY, **mine)

    remaining = await db_session.scalar(
        select(func.count())
        .select_from(IdempotencyKey)
        .where(IdempotencyKey.principal_id == theirs["principal_id"])
    )
    assert remaining == 1
