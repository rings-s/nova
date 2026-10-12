"""Add Massage and Salons categories, and retire Hair.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-10-10 20:42:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | Sequence[str] | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seed the new categories and retire Hair without changing existing services."""
    op.execute(
        """
        INSERT INTO service_categories (id, slug, name_en, name_ar, is_active)
        VALUES
            (gen_random_uuid(), 'massage', 'Massage', 'المساج', true),
            (gen_random_uuid(), 'salons', 'Salons', 'الصالونات', true)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE service_categories
        SET is_active = false
        WHERE slug = 'hair'
        """
    )


def downgrade() -> None:
    """Keep categories in place because services may now refer to them."""
    pass
