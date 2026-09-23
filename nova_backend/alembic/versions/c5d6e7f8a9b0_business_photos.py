"""business photos

`business_photos`: a business's cover and gallery (catalog). The pixels are
files in `integrations.storage`; this table indexes them.

Two policies, as for every catalog table the marketplace shows:

  - `tenant_isolation`, forced, like all tenant-owned tables (autogenerate
    does not emit RLS);
  - `public_discovery`, SELECT-only under `app.discovery_mode`, matching only
    photos of a business that is live, active and listed — the predicate
    `d0e1f2a3b4c5` uses for `businesses` itself, repeated here because a
    policy on one table does not constrain a subquery against another.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = """
    current_setting('app.bypass_rls', true) = 'on'
    OR tenant_id::text = current_setting('app.current_tenant_id', true)
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "business_photos",
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("storage_prefix", sa.String(length=80), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('cover', 'gallery')", name=op.f("ck_business_photos_kind_valid")
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_business_photos_business_id_businesses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_business_photos_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_photos")),
    )
    op.create_index(
        "ix_business_photos_business",
        "business_photos",
        ["tenant_id", "business_id", "position"],
        unique=False,
    )
    op.create_index(
        op.f("ix_business_photos_tenant_id"), "business_photos", ["tenant_id"], unique=False
    )
    op.create_index(
        "uq_business_photos_one_cover",
        "business_photos",
        ["business_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'cover'"),
    )

    op.execute("ALTER TABLE business_photos ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE business_photos FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON business_photos "
        f"USING ({_TENANT}) WITH CHECK ({_TENANT})"
    )
    op.execute(
        """
        CREATE POLICY public_discovery ON business_photos
        FOR SELECT
        USING (
            current_setting('app.discovery_mode', true) = 'on'
            AND EXISTS (
                SELECT 1 FROM businesses b
                WHERE b.id = business_photos.business_id
                  AND b.is_deleted = false
                  AND b.is_active = true
                  AND b.is_listed = true
            )
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS public_discovery ON business_photos")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON business_photos")
    op.drop_index("uq_business_photos_one_cover", table_name="business_photos")
    op.drop_index(op.f("ix_business_photos_tenant_id"), table_name="business_photos")
    op.drop_index("ix_business_photos_business", table_name="business_photos")
    op.drop_table("business_photos")
