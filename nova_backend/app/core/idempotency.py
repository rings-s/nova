"""Idempotency keys for POST endpoints.

ADR-0006 left retried POSTs able to create duplicates. A customer on a flaky
mobile connection taps "Book" twice, or a client library retries a request
whose response was lost — and gets two bookings.

Contract:
  - Client sends `Idempotency-Key: <unique-value>` on a POST.
  - First request executes normally; its status and body are stored.
  - A repeat with the same key returns the stored response without re-running
    anything.
  - The same key with a *different* body is a client bug and returns 422 —
    silently serving the first response would hide it.
  - Keys expire after 24 hours.

Concurrency: uniqueness on (key, endpoint) means two simultaneous requests
race to INSERT and exactly one wins. The loser waits for the winner's result
rather than executing.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.exceptions import ConflictError, ValidationDomainError
from app.db.base import Base
from app.db.mixins import UUIDPKMixin

IDEMPOTENCY_HEADER = "Idempotency-Key"
KEY_TTL = timedelta(hours=24)


class IdempotencyKeyReused(ValidationDomainError):
    code = "idempotency_key_reused"

    def __init__(self) -> None:
        super().__init__("This Idempotency-Key was already used with a different request body.")


class IdempotentRequestInFlight(ConflictError):
    code = "request_in_flight"
    # 409 rather than 425: the client should simply retry shortly.

    def __init__(self) -> None:
        super().__init__("An identical request is currently being processed. Retry shortly.")


class IdempotencyKey(Base, UUIDPKMixin):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("idempotency_key", "endpoint", name="uq_idempotency_keys_key_endpoint"),
        Index("ix_idempotency_keys_expires", "expires_at"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: "in_progress" until the handler completes, then "completed".
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC) + KEY_TTL
    )


def fingerprint_request(body: Any) -> str:
    """Stable hash of the request body, so key reuse with different data is caught."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def begin_idempotent(
    session: AsyncSession,
    *,
    key: str,
    endpoint: str,
    body: Any,
    tenant_id: uuid.UUID | None = None,
) -> tuple[bool, dict[str, Any] | None, int | None]:
    """Claims the key.

    Returns `(should_execute, stored_body, stored_status)`:
      - (True, None, None)      -> caller runs the handler, then calls `complete_idempotent`
      - (False, body, status)   -> caller replays the stored response
    """
    now = datetime.now(UTC)
    fingerprint = fingerprint_request(body)

    existing = await _find(session, key=key, endpoint=endpoint, now=now)
    if existing is not None:
        return _replay(existing, fingerprint)

    record = IdempotencyKey(
        tenant_id=tenant_id,
        idempotency_key=key,
        endpoint=endpoint,
        request_fingerprint=fingerprint,
        state="in_progress",
    )
    session.add(record)
    try:
        # Forces the unique constraint to be evaluated now, so a concurrent
        # duplicate is detected before the handler does any work.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await _find(session, key=key, endpoint=endpoint, now=now)
        if existing is None:
            raise
        return _replay(existing, fingerprint)

    return True, None, None


def _replay(
    existing: IdempotencyKey, fingerprint: str
) -> tuple[bool, dict[str, Any] | None, int | None]:
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyKeyReused()
    if existing.state != "completed":
        raise IdempotentRequestInFlight()
    return False, existing.response_body, existing.response_status


async def _find(
    session: AsyncSession, *, key: str, endpoint: str, now: datetime
) -> IdempotencyKey | None:
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.idempotency_key == key,
        IdempotencyKey.endpoint == endpoint,
        IdempotencyKey.expires_at > now,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def complete_idempotent(
    session: AsyncSession,
    *,
    key: str,
    endpoint: str,
    status_code: int,
    body: Any,
) -> None:
    """Stores the response so a retry can replay it."""
    record = await _find(session, key=key, endpoint=endpoint, now=datetime.now(UTC))
    if record is None:
        return
    record.state = "completed"
    record.response_status = status_code
    record.response_body = json.loads(json.dumps(body, default=str))
    await session.flush()


class IdempotencyGuard:
    """The route-level handle on the machinery above.

    Used explicitly rather than as a transparent dependency, because a
    dependency cannot short-circuit a handler and return the stored response —
    and hiding a replay would make an endpoint that silently does nothing very
    hard to debug. The route reads:

        replay = await guard.begin(payload)
        if replay is not None:
            return replay
        ...
        await guard.complete(status_code=201, body=out)

    With no `Idempotency-Key` header the guard is inert, so the header stays
    optional and existing clients keep working.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        key: str | None,
        endpoint: str,
        tenant_id: uuid.UUID | None = None,
    ) -> None:
        self.session = session
        self.key = key
        self.endpoint = endpoint
        self.tenant_id = tenant_id

    @property
    def active(self) -> bool:
        return bool(self.key)

    async def begin(self, body: Any) -> Any | None:
        """Claims the key. Returns the stored response if this is a retry."""
        if not self.key:
            return None

        should_execute, stored_body, stored_status = await begin_idempotent(
            self.session,
            key=self.key,
            endpoint=self.endpoint,
            body=body,
            tenant_id=self.tenant_id,
        )
        if should_execute:
            return None

        # Import here: `core.idempotency` is imported by `modules/registry.py`
        # purely for its table, and that import must not drag in Starlette.
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=stored_status or 200,
            content=stored_body,
            headers={"Idempotent-Replay": "true"},
        )

    async def complete(self, *, status_code: int, body: Any) -> None:
        if not self.key:
            return
        await complete_idempotent(
            self.session,
            key=self.key,
            endpoint=self.endpoint,
            status_code=status_code,
            body=body,
        )


def idempotency_guard(endpoint: str):
    """Builds a FastAPI dependency producing a guard for one endpoint.

    Scoped per endpoint so the same key reused against a *different* operation
    is a separate record rather than replaying an unrelated response.
    """
    from fastapi import Depends, Header

    from app.core.deps import get_db_session

    async def _dependency(
        session: AsyncSession = Depends(get_db_session),
        idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> IdempotencyGuard:
        return IdempotencyGuard(session, key=idempotency_key, endpoint=endpoint)

    return _dependency
