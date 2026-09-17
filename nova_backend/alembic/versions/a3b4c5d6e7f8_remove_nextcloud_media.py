"""remove nextcloud media

Nextcloud is no longer an integration NOVA supports. It existed to back one
thing — the `media` module's WebDAV storage — so removing it means removing
that module wholesale rather than swapping in a replacement adapter:

  - `media_assets` (and its `tenant_isolation` policy) is dropped; nothing
    else referenced it by foreign key (docs/01: "Not a ForeignKey").
  - `businesses.logo_asset_id`, `businesses.cover_asset_id`,
    `businesses.nextcloud_folder_id`, and `providers.image_asset_id` were
    references to `media_assets` rows and never anything else. None of them
    were ever set by application code — `logo_asset_id`/`cover_asset_id`/
    `image_asset_id` were read-only in every schema, and no writer for them
    existed anywhere in the codebase — so dropping them loses no live data.

Revision ID: a3b4c5d6e7f8
Revises: 4a6c151e23df
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "4a6c151e23df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    """Upgrade schema."""

    op.drop_column("providers", "image_asset_id")
    op.drop_column("businesses", "nextcloud_folder_id")
    op.drop_column("businesses", "cover_asset_id")
    op.drop_column("businesses", "logo_asset_id")

    # DROP TABLE removes the table's own policy and grants with it.
    op.drop_index("ix_media_assets_tenant_kind", table_name="media_assets")
    op.drop_index("ix_media_assets_tenant_business", table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_is_deleted"), table_name="media_assets")
    op.drop_index(op.f("ix_media_assets_tenant_id"), table_name="media_assets")
    op.drop_table("media_assets")


def downgrade() -> None:
    """Downgrade schema."""

    op.create_table(
        "media_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("webdav_path", sa.String(length=1000), nullable=False),
        sa.Column("thumbnail_path", sa.String(length=1000), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_ready", sa.Boolean(), nullable=False),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_media_assets_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_media_assets_size_positive")),
    )
    op.create_index(op.f("ix_media_assets_tenant_id"), "media_assets", ["tenant_id"])
    op.create_index(op.f("ix_media_assets_is_deleted"), "media_assets", ["is_deleted"])
    op.create_index(
        "ix_media_assets_tenant_business", "media_assets", ["tenant_id", "business_id"]
    )
    op.create_index("ix_media_assets_tenant_kind", "media_assets", ["tenant_id", "kind"])

    op.execute("ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE media_assets FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON media_assets
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

    op.add_column("businesses", sa.Column("logo_asset_id", sa.UUID(), nullable=True))
    op.add_column("businesses", sa.Column("cover_asset_id", sa.UUID(), nullable=True))
    op.add_column(
        "businesses", sa.Column("nextcloud_folder_id", sa.String(length=255), nullable=True)
    )
    op.add_column("providers", sa.Column("image_asset_id", sa.UUID(), nullable=True))
