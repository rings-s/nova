#!/usr/bin/env bash
# Gives `nova_app`, the role the API and worker connect as, its login.
#
# The `postgres` image makes POSTGRES_USER a superuser, and Postgres exempts a
# superuser from row-level security even under FORCE, so an app connected as
# POSTGRES_USER runs with every tenant policy off. `nova_app` is NOSUPERUSER
# NOBYPASSRLS; migration e1f2a3b4c5d6 grants it the schema. The migration also
# creates the role when it is missing, without a login, so this only has to make
# it able to log in.
#
# Runs once, when the volume is first initialised. For an existing volume:
#
#     make db-app-role
#
# Safe to re-run: it creates the role if missing and (re)sets the password.
set -eo pipefail

: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is unset, see infra/.env.example}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set app_password="$POSTGRES_APP_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE nova_app' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'nova_app')
\gexec
SELECT format(
    'ALTER ROLE nova_app WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %L',
    :'app_password'
)
\gexec
SQL
