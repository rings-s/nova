# Backups

Postgres holds bookings, payments and customers' phone numbers and emails. This
is how it is dumped, checked and restored.

## What runs

| Command | What it does |
| --- | --- |
| `docker compose -f infra/docker-compose.yml --env-file infra/.env --profile backup up -d backup` | Starts the loop: one dump now, then one every `BACKUP_INTERVAL_SECONDS` (default a day). |
| `make backup` | One dump now, then exits. |
| `make restore-check` | Restores the newest dump into a scratch database, prints a few row counts, drops it. |

Dumps are `pg_dump --format=custom`, written to the `backup_data` volume as
`nova-<UTC timestamp>.dump`, mode 0600. Each is read back with `pg_restore
--list` before it is kept. The newest `BACKUP_KEEP` (default 14) are kept, by
count rather than age, so a job that stops cannot delete the history it was
protecting.

The `backup` service logs in as `POSTGRES_USER`, a superuser. That is required,
not a shortcut: every tenant table has `FORCE ROW LEVEL SECURITY`, so a dump as
`nova_app`, or as any role RLS applies to, comes out empty. Like `migrate` and
`tools`, it is never the API or the worker.

## What this does not do

- **It is not off-site.** The volume sits on the same disk as the database. A
  failed disk, a deleted volume or a stolen laptop takes both. Copy
  `/backups` somewhere else on a schedule (an object store, another machine).
  Dumps contain personal data, so encrypt them in transit and at rest
  (`age`, `gpg`, or the store's own encryption).
- **It is not point-in-time.** You can recover to the last dump, up to a day of
  bookings and payments behind. If that is too much, add WAL archiving
  (`archive_mode`, a base backup tool such as pgBackRest or WAL-G) rather than
  dumping more often.
- **Redis is not backed up.** It holds rate-limit windows, idempotency keys, AI
  conversation memory and the ARQ queue. Losing it loses none of the system of
  record. The outbox is in Postgres.
- **Business photos are not in the dump.** They live under `MEDIA_ROOT` and
  need their own copy.

## Restoring for real

1. Stop `backend` and `worker` so nothing writes during the restore.
2. Start Postgres on a **fresh** volume, so `infra/postgres/initdb` creates the
   `nova_app` login the dump's `GRANT`s refer to. On an old volume run
   `make db-app-role`.
3. Copy the dump into the `backup` container, or mount it, then:
   ```bash
   pg_restore --dbname=nova --exit-on-error --no-owner nova-<timestamp>.dump
   ```
   With the superuser from `infra/.env` (`PGUSER`/`PGPASSWORD`).
4. `make migrate`. The restored `alembic_version` is whatever the dump was
   taken at; this brings it to the code's head.
5. Start `backend` and `worker`. The worker re-dispatches any outbox event that
   was still pending in the dump; handlers are idempotent.

## Drill it

Run `make restore-check` after the first backup and then monthly. A passing
check means the newest dump restores cleanly and the tables are populated. It
does not prove your off-site copy is intact: restore from that copy at least
once, on another machine.
