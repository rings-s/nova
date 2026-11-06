"""admin · APPLICATION layer — the platform console.

Reads any table across every tenant, masked (`domain.display_value`), and
records each read in the audit log. Writes two ways:

  - `run_action` hands a curated action to the module that owns the row,
    scoped to the row's tenant, so the module's rules and events apply as they
    would for that tenant's own staff.
  - `create_row`, `update_row` and `delete_row` change any row of any table but
    the audit log directly: no state machine, event or policy runs, only the
    database's own constraints. Each is scoped to the row's tenant first, and
    recorded with the values before and after (masked).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import Table
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationDomainError
from app.core.security import Principal
from app.db.session import set_tenant_scope
from app.modules.admin.domain import (
    ActionSpec,
    AdminAction,
    AdminAuditKind,
    action_spec,
    actions_for,
    clean_reason,
    contains_mask,
    decode_row_id,
    display_value,
    encode_row_id,
    group_of,
    is_editable_table,
    is_masked_column,
    self_edit_refusal,
)
from app.modules.admin.exceptions import (
    AdminActionNotFoundError,
    AdminActionRefusedError,
    AdminRowNotFoundError,
    AdminTableNotFoundError,
    AdminValueError,
)
from app.modules.admin.models import AdminAuditEntry
from app.modules.admin.repository import (
    AdminAuditRepository,
    AdminTableRepository,
    all_tables,
    coerce_value,
    enum_choices,
    find_table,
    is_filterable,
    is_required,
    is_searchable,
    is_writable,
    max_length,
    referenced_by,
    references,
    type_name,
)
from app.modules.booking.service import BookingService
from app.modules.catalog.service import CatalogService
from app.modules.identity.auth_service import AuthService

_FOREIGN_KEY_VIOLATION = "23503"


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


@dataclass(frozen=True, slots=True)
class TableSummary:
    name: str
    group: str
    estimated_rows: int


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    primary_key: bool
    masked: bool
    searchable: bool
    filterable: bool
    references: str | None
    choices: list[str]
    #: Whether a direct edit may set it, and whether a new row must.
    writable: bool
    required: bool
    max_length: int | None


@dataclass(frozen=True, slots=True)
class TableDescription:
    name: str
    group: str
    #: Whether rows may be added, edited and deleted directly.
    editable: bool
    columns: list[ColumnInfo]
    primary_key: list[str]
    actions: list[ActionSpec]
    #: (table, column) pairs that point at this table's rows.
    related: list[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class RowView:
    id: str
    values: dict[str, Any]
    tenant_id: str | None = None
    actions: list[ActionSpec] = field(default_factory=list)


class AdminService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        tables: AdminTableRepository,
        audit: AdminAuditRepository,
        auth: AuthService,
        catalog_for: Callable[[UUID], CatalogService],
        bookings_for: Callable[[UUID], BookingService],
    ) -> None:
        self.session = session
        self.tables = tables
        self.audit = audit
        self.auth = auth
        self.catalog_for = catalog_for
        self.bookings_for = bookings_for

    # --- reading ----------------------------------------------------------

    async def list_tables(self) -> list[TableSummary]:
        counts = await self.tables.estimated_counts()
        return [
            TableSummary(
                name=table.name,
                group=group_of(table.name),
                estimated_rows=counts.get(table.name, 0),
            )
            for table in all_tables()
        ]

    def describe(self, table_name: str) -> TableDescription:
        table = self._table(table_name)
        return TableDescription(
            name=table.name,
            group=group_of(table.name),
            editable=is_editable_table(table.name),
            columns=[
                ColumnInfo(
                    name=column.name,
                    type=type_name(column),
                    nullable=bool(column.nullable),
                    primary_key=column.primary_key,
                    masked=is_masked_column(column.name),
                    searchable=is_searchable(column),
                    filterable=is_filterable(column),
                    references=references(column),
                    choices=enum_choices(column),
                    writable=is_writable(column),
                    required=is_required(column),
                    max_length=max_length(column),
                )
                for column in table.columns
            ],
            primary_key=[column.name for column in table.primary_key.columns],
            actions=actions_for(table.name),
            related=referenced_by(table),
        )

    async def list_rows(
        self,
        principal: Principal,
        table_name: str,
        *,
        search: str | None = None,
        filters: dict[str, str] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RowView], int]:
        table = self._table(table_name)
        search = (search or "").strip() or None
        filters = filters or {}
        rows, total = await self.tables.list_rows(
            table,
            search=search,
            filters=filters,
            order_by=order_by,
            descending=descending,
            limit=limit,
            offset=offset,
        )
        await self._record(
            principal,
            AdminAuditKind.LIST,
            table.name,
            detail={
                "search": search,
                "filters": filters,
                "order_by": order_by,
                "descending": descending,
                "offset": offset,
                "returned": len(rows),
            },
        )
        return [self._view(table, row, with_actions=False) for row in rows], total

    async def get_row(self, principal: Principal, table_name: str, row_id: str) -> RowView:
        table = self._table(table_name)
        row = await self._fetch(table, row_id)
        await self._record(
            principal,
            AdminAuditKind.VIEW,
            table.name,
            row_id=row_id,
            target_tenant_id=row.get("tenant_id"),
        )
        return self._view(table, row, with_actions=True)

    # --- curated actions --------------------------------------------------

    async def run_action(
        self,
        principal: Principal,
        table_name: str,
        row_id: str,
        action: str,
        *,
        reason: str | None = None,
    ) -> RowView:
        table = self._table(table_name)
        spec = action_spec(table.name, action)
        if spec is None:
            raise AdminActionNotFoundError(table.name, action)
        try:
            reason = clean_reason(spec, reason)
        except ValueError as exc:
            raise ValidationDomainError(str(exc)) from exc

        row = await self._fetch(table, row_id)
        target = row["id"]
        tenant_id: UUID | None = row.get("tenant_id")

        match spec.action:
            case AdminAction.DEACTIVATE_USER:
                if target == principal.subject_id:
                    raise AdminActionRefusedError("You can't deactivate your own account.")
                await self.auth.set_account_active(target, active=False)
            case AdminAction.REACTIVATE_USER:
                await self.auth.set_account_active(target, active=True)
            case AdminAction.REVOKE_SESSIONS:
                await self.auth.revoke_all_tokens(target)
            case AdminAction.HIDE_LISTING | AdminAction.SHOW_LISTING:
                catalog = await self._scoped(tenant_id, self.catalog_for)
                await catalog.set_listing_visibility(
                    target, is_listed=spec.action is AdminAction.SHOW_LISTING
                )
            case AdminAction.CANCEL_BOOKING:
                bookings = await self._scoped(tenant_id, self.bookings_for)
                # As the business, not the customer: the customer-facing
                # cancellation deadline does not bind NOVA support.
                await bookings.cancel(target, reason=reason, by_staff=True)

        await self._record(
            principal,
            AdminAuditKind.ACTION,
            table.name,
            row_id=row_id,
            action=spec.action.value,
            target_tenant_id=tenant_id,
            detail={"reason": reason} if reason else {},
        )
        # Read back after the owning service flushed, through the scope it ran in.
        return self._view(table, await self._fetch(table, row_id), with_actions=True)

    # --- direct edits -------------------------------------------------------

    async def create_row(
        self, principal: Principal, table_name: str, values: dict[str, Any]
    ) -> RowView:
        table = self._editable(table_name)
        changes = self._changes(table, values, creating=True)
        missing = [
            column.name
            for column in table.columns
            if is_required(column) and column.name not in changes
        ]
        if missing:
            raise ValidationDomainError(f"A new row needs a value for: {', '.join(missing)}.")
        tenant_id: UUID | None = changes.get("tenant_id")
        await self._scope_write(tenant_id)
        row_id = encode_row_id(await self.tables.insert_row(table, changes))
        row = await self._fetch(table, row_id)
        await self._record(
            principal,
            AdminAuditKind.CREATE,
            table.name,
            row_id=row_id,
            target_tenant_id=tenant_id,
            detail={"values": self._shown(row)},
        )
        return self._view(table, row, with_actions=True)

    async def update_row(
        self, principal: Principal, table_name: str, row_id: str, values: dict[str, Any]
    ) -> RowView:
        table = self._editable(table_name)
        before = await self._fetch(table, row_id)
        changes = self._changes(table, values, creating=False)
        if not changes:
            raise ValidationDomainError("There is nothing to change.")
        refusal = self_edit_refusal(
            table.name, row_id, principal.subject_id, deleting=False, changes=changes
        )
        if refusal:
            raise AdminActionRefusedError(refusal)
        tenant_id: UUID | None = before.get("tenant_id")
        await self._scope_write(tenant_id)
        await self.tables.update_row(table, self._key(table, row_id), changes)
        after = await self._fetch(table, row_id)
        await self._record(
            principal,
            AdminAuditKind.UPDATE,
            table.name,
            row_id=row_id,
            target_tenant_id=tenant_id,
            detail={
                "before": {name: display_value(name, before[name]) for name in changes},
                "after": {name: display_value(name, after[name]) for name in changes},
            },
        )
        return self._view(table, after, with_actions=True)

    async def delete_row(self, principal: Principal, table_name: str, row_id: str) -> None:
        table = self._editable(table_name)
        row = await self._fetch(table, row_id)
        refusal = self_edit_refusal(
            table.name, row_id, principal.subject_id, deleting=True, changes={}
        )
        if refusal:
            raise AdminActionRefusedError(refusal)
        tenant_id: UUID | None = row.get("tenant_id")
        await self._scope_write(tenant_id)
        try:
            await self.tables.delete_row(table, self._key(table, row_id))
        except IntegrityError as exc:
            if _sqlstate(exc) == _FOREIGN_KEY_VIOLATION:
                raise AdminActionRefusedError(
                    "Other rows still point at this one. Delete or change them first."
                ) from exc
            raise
        await self._record(
            principal,
            AdminAuditKind.DELETE,
            table.name,
            row_id=row_id,
            target_tenant_id=tenant_id,
            # What was deleted, masked: enough to see what was lost.
            detail={"values": self._shown(row)},
        )

    def _editable(self, name: str) -> Table:
        table = self._table(name)
        if not is_editable_table(table.name):
            raise AdminActionRefusedError(f"'{table.name}' can't be changed from the console.")
        return table

    def _changes(self, table: Table, values: dict[str, Any], *, creating: bool) -> dict[str, Any]:
        """The submitted values, checked and coerced to each column's type."""
        changes: dict[str, Any] = {}
        for name, value in values.items():
            column = table.columns.get(name)
            if column is None:
                raise AdminValueError(name, f"is not a column of '{table.name}'")
            if not is_writable(column):
                raise AdminValueError(name, "is computed by the database")
            if not creating and (column.primary_key or name == "tenant_id"):
                raise AdminValueError(name, "can't be changed on an existing row")
            if contains_mask(value):
                raise AdminValueError(
                    name, "still holds the masked placeholder; enter a new value or leave it out"
                )
            changes[name] = coerce_value(column, value)
        return changes

    async def _scope_write(self, tenant_id: UUID | None) -> None:
        """Holds a direct edit to one tenant, as `_scoped` does a curated action:
        RLS then refuses a row written for any other. A platform table (no
        `tenant_id`) stays under the console's bypass."""
        if tenant_id is not None:
            await set_tenant_scope(self.session, tenant_id)

    def _key(self, table: Table, row_id: str) -> list[str]:
        key = decode_row_id(row_id, len(table.primary_key.columns))
        if key is None:
            raise AdminRowNotFoundError(table.name, row_id)
        return key

    @staticmethod
    def _shown(row: dict[str, Any]) -> dict[str, Any]:
        return {name: display_value(name, value) for name, value in row.items()}

    async def _scoped[S](self, tenant_id: UUID | None, build: Callable[[UUID], S]) -> S:
        """The owning module's service for the row's tenant, with the connection
        scoped to that tenant alone. `set_tenant_scope` also closes the console's
        bypass, so from here on RLS holds this transaction to the one tenant."""
        if tenant_id is None:
            raise AdminActionRefusedError("This row belongs to no tenant.")
        await set_tenant_scope(self.session, tenant_id)
        return build(tenant_id)

    # --- helpers ------------------------------------------------------------

    def _table(self, name: str) -> Table:
        table = find_table(name)
        if table is None:
            raise AdminTableNotFoundError(name)
        return table

    async def _fetch(self, table: Table, row_id: str) -> dict[str, Any]:
        key = decode_row_id(row_id, len(table.primary_key.columns))
        row = await self.tables.get_row(table, key) if key is not None else None
        if row is None:
            raise AdminRowNotFoundError(table.name, row_id)
        return row

    def _view(self, table: Table, row: dict[str, Any], *, with_actions: bool) -> RowView:
        tenant_id = row.get("tenant_id")
        return RowView(
            id=encode_row_id([row[column.name] for column in table.primary_key.columns]),
            values={name: display_value(name, value) for name, value in row.items()},
            tenant_id=str(tenant_id) if tenant_id is not None else None,
            actions=actions_for(table.name) if with_actions else [],
        )

    async def _record(
        self,
        principal: Principal,
        kind: AdminAuditKind,
        table_name: str,
        *,
        row_id: str | None = None,
        action: str | None = None,
        target_tenant_id: UUID | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await self.audit.record(
            AdminAuditEntry(
                actor_id=principal.subject_id,
                actor_kind=principal.kind.value,
                kind=kind,
                table_name=table_name,
                row_id=row_id,
                action=action,
                target_tenant_id=target_tenant_id,
                detail=detail or {},
            )
        )
