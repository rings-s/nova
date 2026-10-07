"""Store enum columns as their values, not their member names.

`Enum(..., native_enum=False)` wrote `CONFIRMED` while every hand-written
predicate (`ex_bookings_no_provider_overlap`'s `WHERE status IN ('confirmed',
...)`) says `confirmed`, so the exclusion constraint covered no rows. The
models now use `EnumValue`, which writes the value and still reads either; this
migration brings the existing rows across.

Expand-and-contract: deploy the code first (it reads both spellings), then run
this. Rows an old process writes in between still load.

Revision ID: a9c1d2e3f4b5
Revises: f1b21a26382c
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c1d2e3f4b5"
down_revision: str | None = "f1b21a26382c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every enum column. Each member's value is its name lower-cased (checked when
#: this was written), so `lower()` is the whole conversion.
_COLUMNS = (
    ("subscriptions", "tier"),
    ("subscriptions", "status"),
    ("commission_lines", "commission_class"),
    ("commission_lines", "status"),
    ("invoices", "status"),
    ("subscription_checkouts", "tier"),
    ("subscription_checkouts", "status"),
    ("bookings", "status"),
    ("bookings", "source"),
    ("notifications", "channel"),
    ("notifications", "template"),
    ("notifications", "status"),
    ("payments", "status"),
    ("queue_entries", "status"),
    ("queue_entries", "source"),
    ("tickets", "status"),
)

_BLOCKING = ("draft", "pending_payment", "confirmed", "checked_in", "in_service")


def _bypass_rls() -> None:
    """Tenant tables force RLS even on their owner, and no tenant is set here."""
    op.execute("SELECT set_config('app.bypass_rls', 'on', true)")


def _refuse_existing_overlaps() -> None:
    """The exclusion constraint starts applying to these rows the moment their
    status is spelled the way it expects. If the inert period let two bookings
    overlap, say so plainly instead of failing on an opaque constraint error."""
    blocking = ", ".join(f"'{s}'" for s in _BLOCKING)
    clashes = (
        op.get_bind()
        .execute(
            sa.text(
                f"""
                SELECT count(*) FROM bookings a
                JOIN bookings b
                  ON a.provider_id = b.provider_id AND a.id < b.id
                 AND tstzrange(a.starts_at, a.ends_at, '[)')
                  && tstzrange(b.starts_at, b.ends_at, '[)')
                WHERE lower(a.status) IN ({blocking})
                  AND lower(b.status) IN ({blocking})
                """
            )
        )
        .scalar_one()
    )
    if clashes:
        raise RuntimeError(
            f"{clashes} pairs of active bookings overlap for the same provider. "
            "They were allowed while ex_bookings_no_provider_overlap matched no rows. "
            "Cancel or move one of each pair, then run this migration again."
        )


def upgrade() -> None:
    """Upgrade schema."""
    _bypass_rls()
    _refuse_existing_overlaps()
    for table, column in _COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = lower({column}) WHERE {column} <> lower({column})"
        )


def downgrade() -> None:
    """Downgrade schema: back to member names, which the old models read."""
    _bypass_rls()
    for table, column in _COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = upper({column}) WHERE {column} <> upper({column})"
        )
