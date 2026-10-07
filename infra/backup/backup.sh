#!/usr/bin/env bash
# One backup: dump, check the dump can be read back, then prune old ones.
#
# Runs as the database superuser on purpose. Every tenant table has FORCE row
# level security, so a dump as any role RLS applies to would come out empty (or
# pg_dump would refuse). The superuser is exempt, which is what a backup needs.
# That is why this lives in its own container and never in `backend`/`worker`.
set -euo pipefail
umask 077 # the dump holds customer phone numbers and emails

dir="${BACKUP_DIR:-/backups}"
keep="${BACKUP_KEEP:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
partial="$dir/.nova-$stamp.dump.partial"
final="$dir/nova-$stamp.dump"

mkdir -p "$dir"
trap 'rm -f "$partial"' EXIT

pg_dump --format=custom --compress=6 --file="$partial"

# A dump nobody can read back is not a backup. `--list` parses the whole table of
# contents, which catches a truncated or corrupt file.
pg_restore --list "$partial" > /dev/null
[ -s "$partial" ] || { echo "backup is empty" >&2; exit 1; }

mv "$partial" "$final"
trap - EXIT
echo "backup ok: $final ($(du -h "$final" | cut -f1))"

# Keep the newest `keep`, by count and not by age: if backups stop, nothing is
# deleted, so a stalled job cannot eat the history it was meant to protect.
# shellcheck disable=SC2012
ls -1t "$dir"/nova-*.dump 2> /dev/null | tail -n +"$((keep + 1))" | xargs -r rm --
