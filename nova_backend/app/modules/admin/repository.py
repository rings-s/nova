"""admin · PERSISTENCE layer — generic reads over every table, and the audit log.

The console reads tables through `Base.metadata`, the SQLAlchemy Core `Table`
objects every module's models register, not through those modules' ORM classes:
importing another module's `models` is forbidden (tests/test_architecture.py),
and a generic browser has no use for their behaviour anyway. Every table is
present by the time a request arrives, because `app.modules.registry` imports
every module's models before the app is built.

Reads only. The one write is the audit entry; the console's curated actions go
through the owning module's service (`AdminService.run_action`).

The caller must have opened `bypass_tenant_scope` (`get_admin_session`), or
RLS correctly returns no tenant rows.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    ColumnElement,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    and_,
    false,
    func,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.types import EnumValue
from app.modules.admin.domain import is_masked_column
from app.modules.admin.exceptions import AdminFilterError
from app.modules.admin.models import AdminAuditEntry


def all_tables() -> list[Table]:
    return sorted(Base.metadata.tables.values(), key=lambda table: table.name)


def find_table(name: str) -> Table | None:
    return Base.metadata.tables.get(name)


def type_name(column: Column[Any]) -> str:
    """A short, stable name for the console to pick an input and a renderer."""
    kind = column.type
    if isinstance(kind, EnumValue):
        return "enum"
    if isinstance(kind, Boolean):
        return "boolean"
    if isinstance(kind, PG_UUID):
        return "uuid"
    if isinstance(kind, DateTime):
        return "datetime"
    if isinstance(kind, Date):
        return "date"
    if isinstance(kind, Integer | Numeric | Float):
        return "number"
    if isinstance(kind, String | Text):
        return "text"
    return "json"


def enum_choices(column: Column[Any]) -> list[str]:
    if isinstance(column.type, EnumValue):
        return [str(member.value) for member in column.type.enum_class]
    return []


def is_searchable(column: Column[Any]) -> bool:
    return (
        isinstance(column.type, String | Text)
        and not isinstance(column.type, EnumValue)
        and not is_masked_column(column.name)
    )


def is_filterable(column: Column[Any]) -> bool:
    return type_name(column) != "json" and not is_masked_column(column.name)


def references(column: Column[Any]) -> str | None:
    """The table a foreign key column points at, so the console can link it."""
    for foreign_key in column.foreign_keys:
        return foreign_key.column.table.name
    return None


def referenced_by(table: Table) -> list[tuple[str, str]]:
    """(table, column) pairs holding a foreign key into `table`'s rows."""
    found = [
        (other.name, column.name)
        for other in all_tables()
        for column in other.columns
        if any(fk.column.table is table for fk in column.foreign_keys)
    ]
    return sorted(set(found))


def _coerce(column: Column[Any], raw: str) -> Any:
    """A filter value as the column's own Python type, so the comparison can
    use the column's index instead of casting every row to text."""
    kind = column.type
    try:
        if isinstance(kind, EnumValue):
            return kind.enum_class(raw)
        if isinstance(kind, Boolean):
            if raw.lower() not in ("true", "false"):
                raise ValueError(raw)
            return raw.lower() == "true"
        if isinstance(kind, PG_UUID):
            return uuid.UUID(raw)
        if isinstance(kind, DateTime):
            return datetime.fromisoformat(raw)
        if isinstance(kind, Date):
            return date.fromisoformat(raw)
        if isinstance(kind, Integer):
            return int(raw)
        if isinstance(kind, Numeric | Float):
            return Decimal(raw)
    except (ValueError, KeyError, InvalidOperation) as exc:
        raise AdminFilterError(column.name, raw) from exc
    return raw


class AdminTableRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def estimated_counts(self) -> dict[str, int]:
        """Postgres's own row estimates, from the last ANALYZE. Exact counts of
        every table on each visit to the console would scan all of them."""
        result = await self.session.execute(
            text(
                "SELECT c.relname, c.reltuples::bigint FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')"
            )
        )
        return {name: max(int(count), 0) for name, count in result.all()}

    def _where(
        self, table: Table, *, search: str | None, filters: dict[str, str]
    ) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = []
        for name, raw in filters.items():
            column = table.columns.get(name)
            if column is None or not is_filterable(column):
                raise AdminFilterError(name, raw)
            clauses.append(column == _coerce(column, raw))
        if search:
            pattern = f"%{search}%"
            matches: list[ColumnElement[bool]] = [
                column.ilike(pattern) for column in table.columns if is_searchable(column)
            ]
            # An id pasted into the search box finds its row in any table.
            try:
                as_uuid = uuid.UUID(search)
            except ValueError:
                as_uuid = None
            if as_uuid is not None:
                matches.extend(
                    column == as_uuid
                    for column in table.columns
                    if isinstance(column.type, PG_UUID)
                )
            clauses.append(or_(*matches) if matches else false())
        return clauses

    async def list_rows(
        self,
        table: Table,
        *,
        search: str | None,
        filters: dict[str, str],
        order_by: str | None,
        descending: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        where = self._where(table, search=search, filters=filters)

        total = await self.session.scalar(
            select(func.count()).select_from(table).where(and_(true(), *where))
        )

        if order_by is not None:
            column = table.columns.get(order_by)
            if column is None:
                raise AdminFilterError(order_by, "order")
            ordering = [column.desc() if descending else column.asc()]
        elif "created_at" in table.columns:
            ordering = [table.columns["created_at"].desc()]
        elif "occurred_at" in table.columns:
            ordering = [table.columns["occurred_at"].desc()]
        else:
            ordering = []
        # The primary key last, so pages never overlap when the ordering ties.
        ordering.extend(column.asc() for column in table.primary_key.columns)

        stmt = (
            select(table)
            .where(and_(true(), *where))
            .order_by(*ordering)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return [dict(row) for row in result.mappings().all()], int(total or 0)

    async def get_row(self, table: Table, key: list[str]) -> dict[str, Any] | None:
        columns = list(table.primary_key.columns)
        clauses = [column == _coerce(column, raw) for column, raw in zip(columns, key, strict=True)]
        result = await self.session.execute(select(table).where(*clauses))
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None


class AdminAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, entry: AdminAuditEntry) -> AdminAuditEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry
