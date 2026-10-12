"""The platform console's audit log, append-only for the app role.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-11 12:00:00.000000

A platform table with no `tenant_id`, so no RLS policy. Default privileges
grant `nova_app` full DML on it; UPDATE and DELETE are taken back so a
superuser cannot erase their trail through the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "nova_app"


def upgrade() -> None:
    """Create admin_audit_log and make it append-only for nova_app."""
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_kind", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("row_id", sa.String(length=160), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("target_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_log")),
    )
    op.create_index("ix_admin_audit_log_occurred_at", "admin_audit_log", ["occurred_at"])
    op.create_index("ix_admin_audit_log_actor_id", "admin_audit_log", ["actor_id"])
    # A database without the role (a bare CI database) has nothing to revoke.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                REVOKE UPDATE, DELETE, TRUNCATE ON admin_audit_log FROM {_ROLE};
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Drop admin_audit_log."""
    op.drop_index("ix_admin_audit_log_actor_id", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_occurred_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
