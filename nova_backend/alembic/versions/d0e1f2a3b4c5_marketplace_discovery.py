"""marketplace discovery surface

Ships the public discovery surface (ADR-0010) and, with it, the writer that
`BookingSource.MARKETPLACE` has been waiting for since ADR-0008.

Three things happen here:

1. `businesses.is_listed` and `locations.city` — the two facts a marketplace
   listing needs that the catalog did not record: whether a business wants to
   be advertised at all, and where its branch is in words rather than
   coordinates.

2. `marketplace_referrals` — the server-side click record from docs/11 §3
   rule 4. ADR-0008 named its absence as the reason no booking could honestly
   be billed as a marketplace booking.

3. `public_discovery` RLS policies — a second, SELECT-only window onto the
   catalog tables for requests that have no tenant, because a customer
   searching for a salon has not chosen one yet.

On (3), and why it is not `app.bypass_rls`: that switch turns tenant isolation
off wholesale and is documented as never belonging on a request path. These
policies are permissive additions that OR with `tenant_isolation`, so an
ordinary tenant-scoped request is unaffected, and they differ from a bypass in
the two ways that matter — they cover SELECT only, so nothing on the public
path can write across tenants, and they match only rows a business has
published, so an unlisted or retired salon stays invisible.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Guard shared by every policy below. `current_setting(..., true)` returns
#: NULL rather than erroring when the variable is unset, so a connection that
#: never opened the window matches nothing — it fails closed, exactly like
#: `tenant_isolation`.
_DISCOVERY_ON = "current_setting('app.discovery_mode', true) = 'on'"

def _business_is_public(alias: str) -> str:
    """A business is public only if it is live, switched on, and listed.

    Every column is qualified with `alias`. That is not cosmetic: these
    predicates are pasted into subqueries that also have the outer table in
    scope, and an unqualified `is_active` there silently binds to the *outer*
    row instead. The result still parses and still runs — it just answers a
    different question — which is the kind of mistake a policy should not be
    able to make quietly.
    """
    return (
        f"{alias}.is_deleted = false "
        f"AND {alias}.is_active = true "
        f"AND {alias}.is_listed = true"
    )


def _location_is_public(alias: str) -> str:
    """A branch is public when it is live and its business is public."""
    return (
        f"{alias}.is_deleted = false "
        f"AND {alias}.is_active = true "
        f"AND EXISTS ("
        f"    SELECT 1 FROM businesses b"
        f"    WHERE b.id = {alias}.business_id AND {_business_is_public('b')}"
        f")"
    )


def _child_of_public_location(table: str) -> str:
    """Services and providers: live themselves, and under a live branch.

    Written as one EXISTS over the whole chain rather than leaning on the
    policies already on `locations` and `businesses`, because a policy on one
    table does not constrain a subquery the planner runs against another.
    De-listing a business has to hide its price list in the same instant, not
    merely make the business row unreadable while its services stay visible.
    """
    return (
        f"{table}.is_deleted = false "
        f"AND {table}.is_active = true "
        f"AND EXISTS ("
        f"    SELECT 1 FROM locations l"
        f"    JOIN businesses b ON b.id = l.business_id"
        f"    WHERE l.id = {table}.location_id"
        f"      AND l.is_deleted = false AND l.is_active = true"
        f"      AND {_business_is_public('b')}"
        f")"
    )


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "businesses",
        sa.Column("is_listed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("locations", sa.Column("city", sa.String(length=120), nullable=True))

    # Marketplace search filters on city constantly and on nothing else that is
    # not already indexed. Lower-cased because the filter is case-insensitive:
    # a plain index on `city` cannot serve `city ILIKE 'riyadh'`.
    op.create_index(
        "ix_locations_city_lower",
        "locations",
        [sa.text("lower(city)")],
        unique=False,
    )

    op.create_table(
        "marketplace_referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_referrals_tenant_id", "marketplace_referrals", ["tenant_id"])
    # Unique, not merely indexed: two rows sharing a hash would make attribution
    # ambiguous, and the constraint turns a token collision into a database
    # error rather than a silent mis-attribution.
    op.create_index(
        "uq_marketplace_referrals_token_hash",
        "marketplace_referrals",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_marketplace_referrals_expires_at", "marketplace_referrals", ["expires_at"]
    )

    # Referrals are tenant-owned like everything else, so they get the ordinary
    # isolation policy and no discovery policy at all. The public path never
    # needs to write across tenants: by the time it has a row to insert, the
    # storefront lookup has told it which tenant owns the click.
    op.execute("ALTER TABLE marketplace_referrals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE marketplace_referrals FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON marketplace_referrals
        USING (
            current_setting('app.bypass_rls', true) = 'on'
            OR tenant_id::text = current_setting('app.current_tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.bypass_rls', true) = 'on'
            OR tenant_id::text = current_setting('app.current_tenant_id', true)
        )
        """
    )

    op.execute(
        f"""
        CREATE POLICY public_discovery ON businesses
        FOR SELECT
        USING ({_DISCOVERY_ON} AND {_business_is_public("businesses")})
        """
    )
    op.execute(
        f"""
        CREATE POLICY public_discovery ON locations
        FOR SELECT
        USING ({_DISCOVERY_ON} AND {_location_is_public("locations")})
        """
    )
    for table in ("services", "providers"):
        op.execute(
            f"""
            CREATE POLICY public_discovery ON {table}
            FOR SELECT
            USING ({_DISCOVERY_ON} AND {_child_of_public_location(table)})
            """
        )

    # `provider_services` carries no visibility flags of its own; it is public
    # exactly when both ends are. The marketplace needs it to offer only the
    # providers a salon actually qualified for the service being booked.
    op.execute(
        f"""
        CREATE POLICY public_discovery ON provider_services
        FOR SELECT
        USING (
            {_DISCOVERY_ON}
            AND EXISTS (
                SELECT 1 FROM providers p
                JOIN locations l ON l.id = p.location_id
                JOIN businesses b ON b.id = l.business_id
                WHERE p.id = provider_services.provider_id
                  AND p.is_deleted = false AND p.is_active = true
                  AND l.is_deleted = false AND l.is_active = true
                  AND {_business_is_public("b")}
            )
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("businesses", "locations", "services", "providers", "provider_services"):
        op.execute(f"DROP POLICY IF EXISTS public_discovery ON {table}")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON marketplace_referrals")
    op.execute("ALTER TABLE marketplace_referrals NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE marketplace_referrals DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_marketplace_referrals_expires_at", table_name="marketplace_referrals")
    op.drop_index("uq_marketplace_referrals_token_hash", table_name="marketplace_referrals")
    op.drop_index("ix_marketplace_referrals_tenant_id", table_name="marketplace_referrals")
    op.drop_table("marketplace_referrals")

    op.drop_index("ix_locations_city_lower", table_name="locations")
    op.drop_column("locations", "city")
    # Every de-listing recorded here is lost on the way down: the old schema has
    # nowhere to put it, so a business hidden for non-payment reappears in a
    # search the moment this runs.
    op.drop_column("businesses", "is_listed")
