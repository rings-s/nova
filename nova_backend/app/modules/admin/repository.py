"""admin · PERSISTENCE layer — generic reads over every table, and the audit log.

The console reads tables through `Base.metadata`, the SQLAlchemy Core `Table`
objects every module's models register, not through those modules' ORM classes:
importing another module's `models` is forbidden (tests/test_architecture.py),
and a generic browser has no use for their behaviour anyway. Every table is
present by the time a request arrives, because `app.modules.registry` imports
every module's models before the app is built.

Reads, and the console's direct edits (`insert_row`, `update_row`,
`delete_row`) as plain Core statements: no ORM class, so no domain rule, event
or state machine runs. The curated actions go through the owning module's
service instead (`AdminService.run_action`).

The caller must have opened `bypass_tenant_scope` (`get_admin_session`), or
RLS correctly returns no tenant rows.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import (
    ARRAY,
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
    delete,
    false,
    func,
    insert,
    or_,
    select,
    text,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.types import EnumValue
from app.modules.admin.domain import is_masked_column
from app.modules.admin.exceptions import AdminFilterError, AdminValueError
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


def is_writable(column: Column[Any]) -> bool:
    """Whether the console can set this column. A generated column is computed
    by Postgres from the others."""
    return column.computed is None


def is_required(column: Column[Any]) -> bool:
    """Whether a new row must be given a value for this column: it can't be
    null, and neither Python nor Postgres fills it in."""
    return (
        is_writable(column)
        and not column.nullable
        and column.default is None
        and column.server_default is None
        and not (column.primary_key and column.autoincrement is True)
    )


def max_length(column: Column[Any]) -> int | None:
    kind = column.type
    if isinstance(kind, EnumValue):
        return None
    return getattr(kind, "length", None) if isinstance(kind, String) else None


def coerce_value(column: Column[Any], value: Any) -> Any:
    """A submitted JSON value as the column's own Python type, or
    `AdminValueError` saying why it isn't one. Checked here, before the
    statement, so a bad value is a 422 naming the column rather than a
    database error."""
    if value is None:
        if not column.nullable:
            raise AdminValueError(column.name, "can't be empty")
        return None
    kind = column.type
    try:
        if isinstance(kind, EnumValue):
            return kind.enum_class(value)
        if isinstance(kind, Boolean):
            if isinstance(value, bool):
                return value
            if str(value).lower() in ("true", "false"):
                return str(value).lower() == "true"
            raise ValueError(value)
        if isinstance(kind, PG_UUID):
            return uuid.UUID(str(value))
        if isinstance(kind, DateTime):
            parsed = datetime.fromisoformat(str(value))
            if kind.timezone and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        if isinstance(kind, Date):
            return date.fromisoformat(str(value))
        if isinstance(kind, Integer):
            if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
                raise ValueError(value)
            return int(value)
        if isinstance(kind, Numeric) and not isinstance(kind, Float):
            if isinstance(value, bool):
                raise ValueError(value)
            return Decimal(str(value))
        if isinstance(kind, Float):
            if isinstance(value, bool):
                raise ValueError(value)
            return float(value)
        if isinstance(kind, String | Text):
            if not isinstance(value, str):
                raise ValueError(value)
            limit = max_length(column)
            if limit is not None and len(value) > limit:
                raise AdminValueError(column.name, f"is longer than {limit} characters")
            return value
        if isinstance(kind, ARRAY):
            if not isinstance(value, list):
                raise ValueError(value)
            item = Column(column.name, kind.item_type, nullable=False)
            return [coerce_value(item, entry) for entry in value]
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        raise AdminValueError(column.name, f"isn't a valid {type_name(column)}") from exc
    # JSON, and any type the console has no input for: stored as given.
    return value


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

    def _key_clauses(self, table: Table, key: list[str]) -> list[ColumnElement[bool]]:
        columns = list(table.primary_key.columns)
        return [column == _coerce(column, raw) for column, raw in zip(columns, key, strict=True)]

    async def get_row(self, table: Table, key: list[str]) -> dict[str, Any] | None:
        result = await self.session.execute(select(table).where(*self._key_clauses(table, key)))
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None

    # --- direct edits -----------------------------------------------------
    #
    # Each runs in a savepoint: a statement Postgres refuses (a unique value
    # taken, a row still referenced) then leaves the request's transaction
    # usable, and the IntegrityError reaches the error handler as usual.

    async def insert_row(self, table: Table, values: dict[str, Any]) -> list[Any]:
        """Adds a row; returns its primary key values. Python-side defaults
        (`uuid4` ids) and server defaults (timestamps) fill what isn't given."""
        stmt = insert(table).values(values).returning(*table.primary_key.columns)
        async with self.session.begin_nested():
            return list((await self.session.execute(stmt)).one())

    async def update_row(self, table: Table, key: list[str], values: dict[str, Any]) -> None:
        stmt = update(table).where(*self._key_clauses(table, key)).values(values)
        async with self.session.begin_nested():
            await self.session.execute(stmt)

    async def delete_row(self, table: Table, key: list[str]) -> None:
        stmt = delete(table).where(*self._key_clauses(table, key))
        async with self.session.begin_nested():
            await self.session.execute(stmt)


class AdminAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, entry: AdminAuditEntry) -> AdminAuditEntry:
        self.session.add(entry)
        await self.session.flush()
        return entry
