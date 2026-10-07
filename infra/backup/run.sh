#!/usr/bin/env bash
# The scheduled loop: one backup now, then one every BACKUP_INTERVAL_SECONDS.
# A failed run is logged and retried at the next interval; it never stops the
# loop, and `restart: unless-stopped` covers the process itself.
set -uo pipefail

interval="${BACKUP_INTERVAL_SECONDS:-86400}"
while true; do
  bash /opt/backup/backup.sh || echo "BACKUP FAILED at $(date -u +%FT%TZ)" >&2
  sleep "$interval"
done
