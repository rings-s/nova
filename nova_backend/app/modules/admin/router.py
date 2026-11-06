"""admin · DELIVERY layer — HTTP.

Layer rule: schemas, service, dependencies. No business rules here.

Every route depends on `require_superuser` through the router, and every data
route on `get_admin_session` through `get_admin_service`
(`tests/test_route_guards.py`). The reads commit too: the audit entry each one
records is the point.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Principal
from app.core.throttling import write_rate_limit
from app.modules.admin.dependencies import get_admin_service, get_admin_session
from app.modules.admin.exceptions import AdminFilterError
from app.modules.admin.schemas import (
    RowOut,
    RowsPageOut,
    RowValuesRequest,
    RunActionRequest,
    TableDetailOut,
    TableOut,
)
from app.modules.admin.service import AdminService
from app.modules.identity.dependencies import require_superuser

router = APIRouter(
    prefix="/admin/tables",
    tags=["admin"],
    dependencies=[Depends(require_superuser)],
)


def _parse_filters(raw: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for item in raw:
        column, sep, value = item.partition(":")
        if not sep or not column:
            raise AdminFilterError(item, "filter")
        filters[column] = value
    return filters


@router.get("", response_model=list[TableOut])
async def admin_list_tables(service: Annotated[AdminService, Depends(get_admin_service)]) -> object:
    """Every table in NOVA, grouped by the module that owns it, with an
    estimated row count. NOVA administrators only."""
    return await service.list_tables()


@router.get("/{table}", response_model=TableDetailOut)
async def admin_describe_table(
    table: str, service: Annotated[AdminService, Depends(get_admin_service)]
) -> TableDetailOut:
    """A table's columns (which are masked, searchable and filterable, and
    where each foreign key points), the tables that point at it, and the
    actions its rows offer. NOVA administrators only."""
    return TableDetailOut.of(service.describe(table))


@router.get("/{table}/rows", response_model=RowsPageOut)
async def admin_list_rows(
    table: str,
    *,
    q: Annotated[str | None, Query(max_length=200)] = None,
    filter_: Annotated[list[str], Query(alias="filter", default_factory=list)],
    order_by: Annotated[str | None, Query(max_length=64)] = None,
    desc: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: Annotated[Principal, Depends(require_superuser)],
    session: Annotated[AsyncSession, Depends(get_admin_session)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RowsPageOut:
    """One page of a table's rows, across every tenant. NOVA administrators only.

    `q` searches every unmasked text column (and, given an id, every id column);
    each `filter=column:value` matches one column exactly. Secrets are masked.
    The read is recorded in the audit log."""
    rows, total = await service.list_rows(
        principal,
        table,
        search=q,
        filters=_parse_filters(filter_),
        order_by=order_by,
        descending=desc,
        limit=limit,
        offset=offset,
    )
    await session.commit()
    return RowsPageOut(
        items=[RowOut.of(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{table}/rows/{row_id}", response_model=RowOut)
async def admin_get_row(
    table: str,
    row_id: str,
    principal: Annotated[Principal, Depends(require_superuser)],
    session: Annotated[AsyncSession, Depends(get_admin_session)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RowOut:
    """One row, with the actions it offers. Secrets are masked. NOVA
    administrators only; the read is recorded in the audit log."""
    row = await service.get_row(principal, table, row_id)
    await session.commit()
    return RowOut.of(row)


@router.post(
    "/{table}/rows/{row_id}/actions/{action}",
    response_model=RowOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(write_rate_limit)],
)
async def admin_run_action(
    table: str,
    row_id: str,
    action: str,
    payload: RunActionRequest,
    principal: Annotated[Principal, Depends(require_superuser)],
    session: Annotated[AsyncSession, Depends(get_admin_session)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RowOut:
    """Runs one of the row's curated actions (deactivate an account, hide a
    listing, cancel a booking…) through the module that owns it, scoped to the
    row's tenant. NOVA administrators only; recorded in the audit log.

    Prefer an action over a direct edit where one exists: it runs the module's
    rules and events. An action the table doesn't list is a 404."""
    row = await service.run_action(principal, table, row_id, action, reason=payload.reason)
    await session.commit()
    return RowOut.of(row)


@router.post(
    "/{table}/rows",
    response_model=RowOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(write_rate_limit)],
)
async def admin_create_row(
    table: str,
    payload: RowValuesRequest,
    principal: Annotated[Principal, Depends(require_superuser)],
    session: Annotated[AsyncSession, Depends(get_admin_session)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RowOut:
    """Adds a row to any table but the audit log, as given. A column left out
    takes its default. NOVA administrators only; recorded in the audit log.

    A direct edit: only the database's constraints apply, no module's rules,
    and no event is published."""
    row = await service.create_row(principal, table, payload.values)
    await session.commit()
    return RowOut.of(row)


@router.patch(
    "/{table}/rows/{row_id}",
    response_model=RowOut,
    dependencies=[Depends(write_rate_limit)],
)
async def admin_update_row(
    table: str,
    row_id: str,
    payload: RowValuesRequest,
    principal: Annotated[Principal, Depends(require_superuser)],
    session: Annotated[AsyncSession, Depends(get_admin_session)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> RowOut:
    """Changes the given columns of any row but the audit log's. The primary
    key and `tenant_id` stay as they are. NOVA administrators only; recorded in
    the audit log with the values before and after.

    A direct edit: only the database's constraints apply, no module's rules,
    and no event is published."""
    row = await service.update_row(principal, table, row_id, payload.values)
    await session.commit()
    return RowOut.of(row)


@router.delete(
    "/{table}/rows/{row_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(write_rate_limit)],
)
async def admin_delete_row(
    table: str,
    row_id: str,
    principal: Annotated[Principal, Depends(require_superuser)],
    session: Annotated[AsyncSession, Depends(get_admin_session)],
    service: Annotated[AdminService, Depends(get_admin_service)],
) -> Response:
    """Deletes any row but the audit log's. Refused with 409 while other rows
    still point at it (unless their foreign key cascades). NOVA administrators
    only; the audit log keeps what was deleted, masked."""
    await service.delete_row(principal, table, row_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
