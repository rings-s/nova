"""enable row level security on tenant-owned tables

Closes the gap ADR-0003 documented: tenant isolation was enforced only in the
application layer, so raw SQL, a psql session, or a future module that forgot
to extend `TenantScopedRepository` could read across tenants.

With RLS, the database itself refuses. `TenantScopedRepository` stays — it
gives better errors and lets the ORM plan efficient queries — but it is no
longer the only thing standing between two salons' data.

How it works: each request sets `app.current_tenant_id` on its connection
(see `app/db/session.py`), and every policy compares `tenant_id` against it.
A connection that never sets it sees nothing.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-15

"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every table carrying a tenant_id that scopes business data.
_TENANT_TABLES = (
    "businesses",
    "locations",
    "services",
    "providers",
    "provider_services",
    "bookings",
    "memberships",
)


def upgrade() -> None:
    """Upgrade schema."""
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE applies the policy to the table owner too. Without it, the
        # role that owns the table — which is the role the app connects as in
        # most single-database deployments — bypasses RLS entirely and the
        # whole exercise is decorative.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # `current_setting(..., true)` returns NULL rather than erroring when
        # the variable is unset, so an unscoped connection matches no rows
        # instead of raising — it fails closed.
        #
        # Migrations and the outbox dispatcher legitimately need to cross
        # tenants; they set app.bypass_rls = 'on'.
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
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


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
