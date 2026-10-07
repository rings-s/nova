"""Indexes the marketplace search can actually use.

Two problems, found by EXPLAIN as `nova_app` with RLS in force:

- Discovery runs with no tenant, so every tenant-led composite
  (`(tenant_id, business_id)`, ...) is useless to it. The join and the
  correlated price lookups scanned. Plain single-column indexes fix that.
- `ix_locations_city_lower` was never used: with RLS the planner may only use
  an index for operators marked leakproof, and `lower()` and ILIKE are not.
  `city_key`, a stored generated column compared with `=`, is.

The `unaccent`/ILIKE text search over names and descriptions stays a scan on
purpose: a trigram index would be ignored for the same reason, and the
listing set is small enough to scan.

Revision ID: a1d2e3f4b5c6
Revises: a9c1d2e3f4b5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1d2e3f4b5c6"
down_revision: str | None = "a9c1d2e3f4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "locations",
        sa.Column("city_key", sa.String(length=120), sa.Computed("lower(city)", persisted=True)),
    )
    op.create_index("ix_locations_city_key", "locations", ["city_key"])
    op.drop_index("ix_locations_city_lower", table_name="locations")
    op.create_index("ix_locations_business_id", "locations", ["business_id"])
    op.create_index("ix_services_location_id", "services", ["location_id"])
    op.create_index("ix_services_category_id", "services", ["category_id"])
    op.create_index("ix_providers_location_id", "providers", ["location_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_providers_location_id", table_name="providers")
    op.drop_index("ix_services_category_id", table_name="services")
    op.drop_index("ix_services_location_id", table_name="services")
    op.drop_index("ix_locations_business_id", table_name="locations")
    op.create_index("ix_locations_city_lower", "locations", [sa.text("lower(city)")])
    op.drop_index("ix_locations_city_key", table_name="locations")
    op.drop_column("locations", "city_key")
