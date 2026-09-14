"""app role under row level security

Every policy since `d4e5f6a7b8c9` was off in practice. Postgres exempts a
superuser, and any BYPASSRLS role, from row-level security even under `FORCE`,
and the compose stack connected the API, the worker and the test suite as
POSTGRES_USER, which the `postgres` image creates as a superuser. The
application-layer filters were the only isolation running, and no test could
have noticed.

This gives the app a role of its own: `nova_app`, NOSUPERUSER NOBYPASSRLS, with
DML on the schema and nothing more. It cannot create or alter a table, cannot
touch `alembic_version`, and sees only what the policies let it see. The owner
keeps running migrations (`MIGRATION_DATABASE_URL`).

A role belongs to the whole server, not to this database, so it is created only
when missing, and an existing `nova_app` able to bypass RLS stops the migration
instead of being granted the schema. Its password is not a schema concern and
is not set here: `infra/postgres/initdb` gives it a login on a new volume, and
`make db-app-role` on an existing one.

`ALTER DEFAULT PRIVILEGES` extends the grant to each table a later migration
creates, provided the same owner runs it. `tests/test_row_level_security.py`
fails when one is missed.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-14

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: `app.db.session.APP_DB_ROLE`, written out: a migration must keep meaning what
#: it meant when it ran.
_APP_ROLE = "nova_app"

_DML = "SELECT, INSERT, UPDATE, DELETE"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_APP_ROLE}') THEN
                CREATE ROLE {_APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
            ELSIF EXISTS (
                SELECT FROM pg_roles
                WHERE rolname = '{_APP_ROLE}' AND (rolsuper OR rolbypassrls)
            ) THEN
                RAISE EXCEPTION 'role {_APP_ROLE} bypasses row-level security';
            END IF;
        END
        $$
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}")
    op.execute(f"GRANT {_DML} ON ALL TABLES IN SCHEMA public TO {_APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_APP_ROLE}")
    # Migration state is the owner's. An app able to rewrite it could make the
    # next deploy skip a migration.
    op.execute(f"REVOKE ALL ON alembic_version FROM {_APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {_DML} ON TABLES TO {_APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {_APP_ROLE}"
    )


def downgrade() -> None:
    """Downgrade schema.

    Revokes the grants and leaves the role in place. It belongs to the server:
    another database beside this one (`nova_test` beside `nova`) may still grant
    it, and a running API may be logged in as it.
    """
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public"
        f" REVOKE USAGE, SELECT ON SEQUENCES FROM {_APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE {_DML} ON TABLES FROM {_APP_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {_APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {_APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {_APP_ROLE}")
