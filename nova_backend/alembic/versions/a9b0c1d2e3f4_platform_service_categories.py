"""service categories become a platform list; branches lose their phone

Categories were free text typed by each salon, so "Hair", "hair" and "Hair &
Beauty" were three filters on the marketplace. They are now rows in
`service_categories`, which only a superuser (`users.is_superuser`, set with
`make superuser`) may add to or change, and a service points at one.

Every distinct category already in use becomes a row, matched
case-insensitively, with its English text copied into `name_ar` until a
superuser translates it. The slug is the lowercased text with every run of
other characters turned into a hyphen; one that comes out empty (an
Arabic-only value) falls back to part of the new row's id.

`locations.phone` is dropped: a branch has no number of its own, the tenant's
is the business's contact. The downgrade restores the column empty.

`service_categories` is not tenant-owned, so it gets no RLS policy; `nova_app`
receives DML on it through the default privileges from `e1f2a3b4c5d6`.

Revision ID: a9b0c1d2e3f4
Revises: 616b7a77b40b
Create Date: 2026-09-24 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b0c1d2e3f4"
down_revision: str | Sequence[str] | None = "616b7a77b40b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.create_table(
        "service_categories",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False),
        sa.Column("name_ar", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_categories")),
        sa.UniqueConstraint("slug", name=op.f("uq_service_categories_slug")),
    )

    op.add_column("services", sa.Column("category_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_services_category_id_service_categories"),
        "services",
        "service_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # `services` is under FORCE row-level security, which binds the table owner
    # too: without the bypass these statements would see no rows at all.
    op.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    op.execute(
        """
        INSERT INTO service_categories (id, slug, name_en, name_ar, is_active)
        SELECT id,
               COALESCE(
                   NULLIF(
                       trim(BOTH '-' FROM regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')),
                       ''
                   ),
                   'category-' || left(id::text, 8)
               ),
               name, name, true
        FROM (
            SELECT gen_random_uuid() AS id, min(trim(category)) AS name
            FROM services
            WHERE category IS NOT NULL AND trim(category) <> ''
            GROUP BY lower(trim(category))
        ) AS distinct_categories
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE services
        SET category_id = c.id
        FROM service_categories AS c
        WHERE services.category IS NOT NULL
          AND (
              lower(trim(services.category)) = lower(c.name_en)
              -- Two spellings that slug alike ("Hair & Beauty", "hair-beauty")
              -- made one row; the second is found by its slug.
              OR c.slug = trim(BOTH '-' FROM regexp_replace(
                  lower(trim(services.category)), '[^a-z0-9]+', '-', 'g'))
          )
        """
    )

    op.drop_index("ix_services_tenant_category", table_name="services")
    op.drop_column("services", "category")
    op.create_index("ix_services_tenant_category", "services", ["tenant_id", "category_id"])

    op.drop_column("locations", "phone")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "locations",
        sa.Column("phone", sa.String(length=20), server_default="", nullable=False),
    )
    op.alter_column("locations", "phone", server_default=None)

    op.drop_index("ix_services_tenant_category", table_name="services")
    op.add_column("services", sa.Column("category", sa.String(length=120), nullable=True))
    op.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    op.execute(
        """
        UPDATE services
        SET category = c.name_en
        FROM service_categories AS c
        WHERE services.category_id = c.id
        """
    )
    op.create_index("ix_services_tenant_category", "services", ["tenant_id", "category"])
    op.drop_constraint(
        op.f("fk_services_category_id_service_categories"), "services", type_="foreignkey"
    )
    op.drop_column("services", "category_id")
    op.drop_table("service_categories")

    op.drop_column("users", "is_superuser")
