"""admin · DELIVERY layer — API contracts for the platform console."""

from typing import Any

from pydantic import Field

from app.core.schemas import ApiSchema
from app.modules.admin.domain import MAX_REASON_LENGTH, ActionSpec
from app.modules.admin.service import RowView, TableDescription


class TableOut(ApiSchema):
    name: str
    group: str
    #: Postgres's estimate from the last ANALYZE, not an exact count.
    estimated_rows: int


class ColumnOut(ApiSchema):
    name: str
    type: str
    nullable: bool
    primary_key: bool
    #: Shown as `••••••` (or with only the last four characters) in every row.
    masked: bool
    searchable: bool
    filterable: bool
    #: The table this column's foreign key points at.
    references: str | None = None
    #: An enum column's allowed values.
    choices: list[str] = []


class ActionOut(ApiSchema):
    name: str
    label: str
    destructive: bool
    requires_reason: bool

    @classmethod
    def of(cls, spec: ActionSpec) -> "ActionOut":
        return cls(
            name=spec.action.value,
            label=spec.label,
            destructive=spec.destructive,
            requires_reason=spec.requires_reason,
        )


class RelatedOut(ApiSchema):
    table: str
    column: str


class TableDetailOut(ApiSchema):
    name: str
    group: str
    columns: list[ColumnOut]
    primary_key: list[str]
    actions: list[ActionOut]
    related: list[RelatedOut]

    @classmethod
    def of(cls, description: TableDescription) -> "TableDetailOut":
        return cls(
            name=description.name,
            group=description.group,
            columns=[ColumnOut.model_validate(column) for column in description.columns],
            primary_key=description.primary_key,
            actions=[ActionOut.of(spec) for spec in description.actions],
            related=[
                RelatedOut(table=table, column=column) for table, column in description.related
            ],
        )


class RowOut(ApiSchema):
    #: The primary key, `~`-joined when it has more than one column.
    id: str
    tenant_id: str | None = None
    values: dict[str, Any]
    actions: list[ActionOut] = []

    @classmethod
    def of(cls, row: RowView) -> "RowOut":
        return cls(
            id=row.id,
            tenant_id=row.tenant_id,
            values=row.values,
            actions=[ActionOut.of(spec) for spec in row.actions],
        )


class RowsPageOut(ApiSchema):
    items: list[RowOut]
    total: int
    limit: int
    offset: int


class RunActionRequest(ApiSchema):
    reason: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)
