"""scope idempotency keys to the tenant and principal that sent them

SEC-08 of the 2026-09-15 security audit. A key was looked up by its value and
endpoint alone, so anyone who sent the same key and body as someone else, at any
tenant, was served that person's stored response: their booking, or their
payment intent and its checkout link.

`principal_id` joins `tenant_id`, which was carried but never used, in the
unique constraint and in every lookup. Rows written before this carry neither;
their NULLs match no lookup, and they expire within a day.

Revision ID: f2b3c4d5e6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-15

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b3c4d5e6a7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("idempotency_keys", sa.Column("principal_id", sa.UUID(), nullable=True))
    op.drop_constraint("uq_idempotency_keys_key_endpoint", "idempotency_keys", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_keys_scope",
        "idempotency_keys",
        ["idempotency_key", "endpoint", "tenant_id", "principal_id"],
    )


def downgrade() -> None:
    """Downgrade schema.

    The old constraint is narrower: two principals' rows sharing a key and an
    endpoint would violate it. The rows are a one-day replay cache, so they go.
    """
    op.execute("DELETE FROM idempotency_keys")
    op.drop_constraint("uq_idempotency_keys_scope", "idempotency_keys", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency_keys_key_endpoint", "idempotency_keys", ["idempotency_key", "endpoint"]
    )
    op.drop_column("idempotency_keys", "principal_id")
