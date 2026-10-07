#!/usr/bin/env bash
# The drill: restore the newest dump into a scratch database, look at it, drop
# it. A backup you have never restored is a hope. Safe to run any time; it never
# touches the live database.
set -euo pipefail

dir="${BACKUP_DIR:-/backups}"
scratch="nova_restore_check"
# shellcheck disable=SC2012
latest="$(ls -1t "$dir"/nova-*.dump 2> /dev/null | head -n 1 || true)"
[ -n "$latest" ] || { echo "no backup found in $dir" >&2; exit 1; }
echo "restoring $latest into $scratch"

# `postgres`, not the live database, for the admin connection.
psql --dbname=postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS $scratch" \
  -c "CREATE DATABASE $scratch"
trap 'psql --dbname=postgres -c "DROP DATABASE IF EXISTS '"$scratch"'" > /dev/null' EXIT

# `nova_app` must exist for the GRANTs in the dump; a fresh volume creates it
# (infra/postgres/initdb), and this runs against the same cluster.
pg_restore --dbname="$scratch" --exit-on-error "$latest"

psql --dbname="$scratch" -v ON_ERROR_STOP=1 -At <<'SQL'
SELECT 'alembic_version: ' || version_num FROM alembic_version;
SELECT 'tenants: ' || count(*) FROM tenants;
SELECT 'bookings: ' || count(*) FROM bookings;
SELECT 'payments: ' || count(*) FROM payments;
SELECT 'domain_events: ' || count(*) FROM domain_events;
SQL
echo "restore check passed"
