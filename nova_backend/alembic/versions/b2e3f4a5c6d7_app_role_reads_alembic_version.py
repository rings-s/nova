"""Let `nova_app` read `alembic_version`.

`alembic check` and `alembic current` begin by reading the table to learn which
revision the database is at. Only the schema owner could, so a developer's host
shell needed the owner's password just to ask "is the schema up to date?" —
exactly the credential the stack keeps out of every process but `migrate` and
`tools`. A revision id is not sensitive, and SELECT is all this grants: the app
role still cannot write it, so it cannot change what the migrations believe has
run.

Revision ID: b2e3f4a5c6d7
Revises: a1d2e3f4b5c6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2e3f4a5c6d7"
down_revision: str | None = "a1d2e3f4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE = "nova_app"


def upgrade() -> None:
    """Upgrade schema."""
    # A database without the role (a bare CI database) has nothing to grant to.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                GRANT SELECT ON alembic_version TO {_ROLE};
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{_ROLE}') THEN
                REVOKE SELECT ON alembic_version FROM {_ROLE};
            END IF;
        END
        $$;
        """
    )
