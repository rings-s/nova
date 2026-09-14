"""re-map booking.source onto the commission attribution channels

`BookingSource` described the interface a booking arrived through (`pwa`,
`staff`, `whatsapp`, `ai_agent`). docs/11 section 4 needs it to describe who
introduced the customer, because that is what decides whether NOVA may charge
commission. The two are not the same question, and `pwa` in particular spanned
both answers — it covered the marketplace listing *and* the salon's own booking
page.

This migration rewrites existing rows onto the new vocabulary. It is a data
migration only: the column is already `VARCHAR(32)` with no CHECK constraint
(SQLAlchemy renders `native_enum=False` that way), so there is no DDL to
change. Without it, every pre-existing row fails to load — SQLAlchemy raises
`LookupError` on a value that is no longer an enum member.

The `pwa` -> `direct_link` mapping is deliberately lossy in NOVA's favour, not
the salon's. Historical `pwa` rows cannot be split into marketplace and direct
after the fact; that information was never recorded. `direct_link` bills at 0%,
so the worst outcome is that NOVA under-charges on bookings it may have
introduced. The reverse default would charge salons for customers they already
had, which docs/11 calls a P1. This is the whole reason the migration exists
rather than waiting for the billing module: from here forward the distinction is
captured, and it stays uncapturable for everything before.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-16

"""

from collections.abc import Sequence

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: old value -> new value. `whatsapp` and `ai_agent` carry over unchanged and
#: are omitted.
_FORWARD = {
    "pwa": "direct_link",
    "staff": "reception",
}

#: The reverse is lossy: `walk_in` and `marketplace` have no pre-existing
#: equivalent, so they collapse into `pwa` along with `direct_link`. Downgrading
#: and re-upgrading therefore does not round-trip, which is the honest outcome —
#: the old vocabulary cannot express the distinction.
_BACKWARD = {
    "direct_link": "pwa",
    "marketplace": "pwa",
    "walk_in": "pwa",
    "reception": "staff",
}


def _remap(mapping: dict[str, str]) -> None:
    for old, new in mapping.items():
        op.execute(f"UPDATE bookings SET source = '{new}' WHERE source = '{old}'")


def upgrade() -> None:
    """Upgrade schema."""
    _remap(_FORWARD)


def downgrade() -> None:
    """Downgrade schema."""
    _remap(_BACKWARD)
