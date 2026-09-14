"""Shared domain value objects, per docs/06-Domain-Models-and-Aggregates.md section 3.

Pure Pydantic. No SQLAlchemy, no FastAPI — these are safe to import from any
module's domain.py without violating the dependency rule.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class Money(BaseModel):
    """An amount in a single currency.

    Decimal, never float — money arithmetic on binary floats silently loses
    fils. The persistence layer stores this as NUMERIC(12, 2).
    """

    model_config = {"frozen": True}

    amount: Decimal = Field(ge=0, decimal_places=2)
    currency: str = Field(default="SAR", min_length=3, max_length=3)

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"Cannot combine {self.currency} with {other.currency}.")


class TimeRange(BaseModel):
    """A half-open interval [starts_at, ends_at).

    Half-open is deliberate: a 10:00-11:00 booking and an 11:00-12:00 booking
    do not overlap. Treating the end as inclusive would make every
    back-to-back appointment collide.
    """

    model_config = {"frozen": True}

    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_range(self) -> "TimeRange":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self

    @property
    def duration(self) -> timedelta:
        return self.ends_at - self.starts_at

    def overlaps(self, other: "TimeRange") -> bool:
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at

    def contains(self, moment: datetime) -> bool:
        return self.starts_at <= moment < self.ends_at


def to_minor_units(amount: Decimal) -> int:
    """An amount in integer minor units (fils), for exact aggregation.

    Analytics sums money in pandas as int64 (docs/13 section 6.3). A float
    column would lose fils; a Decimal column would turn every sum into a Python
    loop over objects.
    """
    return int((amount * 100).quantize(Decimal("1")))
