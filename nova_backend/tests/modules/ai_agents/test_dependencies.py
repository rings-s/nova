"""The unit of work every agent tool call runs in. Pure — no database.

`TenantServiceScope` is what keeps a chat turn from holding a transaction across
inference, so what it does on the way in and on the way out is pinned here.
"""

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.modules.ai_agents.dependencies import TenantServiceScope


class _Session:
    """Records what is executed; the services built on it never reach a database."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []

    async def execute(self, statement: Any, params: Any = None) -> None:
        self.executed.append((str(statement), params))


def _transaction_over(session: _Session):
    @asynccontextmanager
    async def transaction():
        yield session

    return transaction


async def test_a_unit_of_work_is_scoped_to_the_tenant_before_any_service_runs():
    session = _Session()
    tenant_id = uuid4()
    scope = TenantServiceScope(tenant_id, transaction=_transaction_over(session))

    async with scope() as services:
        assert session.executed, "scoped before the services were handed over"
        assert services.booking is not None

    [(statement, params)] = session.executed
    assert "app.current_tenant_id" in statement
    assert params == {"tenant_id": str(tenant_id)}


async def test_a_lost_race_reaches_the_tool_as_a_refusal_not_a_crash():
    scope = TenantServiceScope(uuid4(), transaction=_transaction_over(_Session()))

    with pytest.raises(ConflictError):
        async with scope():
            raise IntegrityError("INSERT INTO slot_holds ...", {}, Exception("duplicate key"))
