# Media Storage — Nextcloud Integration

**Not implemented.** `backend/app/integrations/storage/nextcloud.py` defines a `MediaStorage`
Protocol (`upload`, `get_url`) and `NotConfiguredMediaStorage`, which raises until a real
adapter exists.

## Design constraint

FastAPI/Postgres store **media references** (URLs or internal paths), never large binaries, in
the database — see [[../architecture/tech-stack]]. This adapter owns the actual
upload/retrieval against Nextcloud.

## To verify

- Auth model: app password (simpler, per-account) vs. OAuth (more setup, better for
  multi-user attribution).
- Share-link expiry and access control model — needed to decide whether media URLs served to
  customers should be time-limited.
- Per-tenant storage quota strategy, if any.
- WebDAV vs. Nextcloud's own REST API for uploads — affects the adapter implementation.

Do not implement against assumed API shapes — confirm against the actual Nextcloud instance
and version before writing the real adapter.
