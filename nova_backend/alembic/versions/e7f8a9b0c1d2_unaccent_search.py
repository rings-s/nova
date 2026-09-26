"""unaccent for marketplace search

Marketplace search matched names accent-sensitively: "Lumiere" did not find
"Lumière Spa", and neither did a model searching on a customer's behalf, which
then retried the same empty search until its turn ran out. `unaccent` lets the
search fold accents on both sides (`catalog.repository.PublicCatalogRepository`).

A trusted extension since PostgreSQL 13, so the database owner that runs
migrations can create it without being a superuser. Its function is executable
by PUBLIC, so `nova_app` needs no grant.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-23

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS unaccent")
