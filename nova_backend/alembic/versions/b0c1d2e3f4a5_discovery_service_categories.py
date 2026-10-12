"""Add beauty clinics and spa to marketplace service categories.

Revision ID: b0c1d2e3f4a5
Revises: 42eebceaeb1e
Create Date: 2026-10-10 20:12:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b0c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "42eebceaeb1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the missing marketplace categories, retaining any existing rows."""
    op.execute(
        """
        INSERT INTO service_categories (id, slug, name_en, name_ar, is_active)
        VALUES
            (gen_random_uuid(), 'beauty-clinics', 'Beauty clinics', 'عيادات التجميل', true),
            (gen_random_uuid(), 'spa', 'Spa', 'السبا', true)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE service_categories
        SET name_en = CASE slug
                WHEN 'beauty-clinics' THEN 'Beauty clinics'
                WHEN 'spa' THEN 'Spa'
            END,
            name_ar = CASE
                WHEN name_ar = name_en OR lower(name_ar) IN ('beauty clinics', 'spa')
                THEN CASE slug
                    WHEN 'beauty-clinics' THEN 'عيادات التجميل'
                    WHEN 'spa' THEN 'السبا'
                END
                ELSE name_ar
            END
        WHERE slug IN ('beauty-clinics', 'spa')
          AND lower(name_en) IN ('beauty clinics', 'spa')
        """
    )


def downgrade() -> None:
    """Keep the categories: they may now be assigned to services."""
    pass
