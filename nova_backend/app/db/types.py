"""Column types shared by every module's models."""

from enum import Enum
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class EnumValue[E: Enum](TypeDecorator[E]):
    """A `StrEnum` stored as its *value*, in a plain VARCHAR.

    `sqlalchemy.Enum(..., native_enum=False)` stores the member NAME
    (`CONFIRMED`) unless told otherwise, while the hand-written SQL in
    migrations and constraints (`WHERE status IN ('confirmed', ...)`) uses the
    value. The two never matched, so `ex_bookings_no_provider_overlap` covered
    no rows. Storing the value makes the SQL and the column agree.

    Reading accepts the legacy member name too, so a row an older process wrote
    before the `lowercase_enum_values` migration ran still loads. That is what
    lets code and data change in separate steps (expand, then contract).
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[E], *, length: int = 32) -> None:
        super().__init__(length)
        self.enum_class = enum_class

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return str(value.value)
        # A plain string must still name a real member (by value, or by name as
        # older callers wrote it): a typo fails here, not as an unreadable row.
        try:
            return str(self.enum_class(value).value)
        except ValueError:
            return str(self.enum_class[value].value)

    def process_result_value(self, value: Any, dialect: Dialect) -> E | None:
        if value is None:
            return None
        try:
            return self.enum_class(value)
        except ValueError:
            return self.enum_class[value]  # a row written before values were stored
