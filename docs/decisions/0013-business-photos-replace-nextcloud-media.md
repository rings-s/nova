# 0013 — Business Photos in Catalog, Stored Locally; the Nextcloud `media` Module Removed

## Status

Accepted — 2026-09-23. Supersedes the `media` section of ADR-0007 and the Nextcloud parts of
docs/01, 02, 06, 07, 08 and 09.

## Context

ADR-0007 built a `media` module on Nextcloud WebDAV. The API issued a signed authorisation for one
path, the browser PUT the bytes to Nextcloud, and `POST .../media/uploads/{asset_id}/complete`
checked them there. Nothing in the product ever consumed it. `businesses.logo_asset_id`,
`cover_asset_id` and `providers.image_asset_id` were read-only in every schema, and no code ever set
them. `businesses.nextcloud_folder_id` was never set either.

What the marketplace did need was a cover and a gallery on a business's storefront and search card.
That is a much narrower job than a general asset store, and it did not need a second server to run
and secure.

## Decision

### Remove `media` and Nextcloud (migration `a3b4c5d6e7f8`, 2026-09-17)

The `media` module, `app/integrations/storage/nextcloud.py`, its settings and the `media_assets`
table (with its `tenant_isolation` policy) are gone. The four `businesses`/`providers` columns that
pointed at it are dropped. No live data was lost, because nothing had ever written them.

### Photos belong to `catalog` (migration `c5d6e7f8a9b0`, 2026-09-23)

- **`business_photos`** (`catalog.models.BusinessPhoto`) indexes a business's photos: `kind`
  (`cover` or `gallery`), `position`, `storage_prefix`, `width` and `height`. A partial unique index
  (`uq_business_photos_one_cover`) allows one cover per business. The limit holds even when two
  uploads race. The gallery holds at most `MAX_GALLERY_PHOTOS` (12).
- **RLS**: the forced `tenant_isolation` policy, plus a SELECT-only `public_discovery` policy that
  matches only the photos of a live, active, listed business. That policy repeats the predicate from
  `businesses` because a policy on one table does not constrain a subquery against another.
- **The API receives the bytes itself.** `POST /tenants/{id}/catalog/businesses/{business_id}/photos`
  takes the raw image as the request body (JPEG, PNG or WebP; `?kind=cover|gallery`) and needs
  `manage_catalog`. The body is refused past `MEDIA_MAX_UPLOAD_BYTES` (10 MB by default) while it
  streams in, before it is held in full. `DELETE .../catalog/photos/{photo_id}` removes a photo, and
  `GET .../businesses/{business_id}/photos` lists them for staff.
- **Nothing is stored as uploaded.** `app/integrations/images.py` decodes every file with Pillow and
  re-encodes it as WebP in two sizes, `large` (1600 px) and `thumb` (480 px). This does three things:
  - A file that only claims to be an image fails to decode and is refused.
  - EXIF data, including the GPS position where the photo was taken, is dropped.
  - Images are sized for the web.

  The declared size is checked against a 40-megapixel cap before decoding, so a decompression bomb
  is refused before it can expand. Encoding runs off the event loop (`asyncio.to_thread`).

- **Storage** is `app/integrations/storage`. The `ImageStore` Protocol has `save`, `read` and
  `delete`, and `LocalImageStore` keeps files under `MEDIA_ROOT`. NOVA generates every key
  (`tenant/photo/variant.webp`), and a regex refuses any key that doesn't match that shape, so no
  request can name a path. Files are written before the row, so a row never points at a missing
  file; a failure in between leaves at worst an unreferenced file. Compose sets
  `MEDIA_ROOT=/app/.media`, a git-ignored directory in the bind mount. Production points it at a
  persistent volume.
- **Serving**: `GET /api/v1/discovery/photos/{photo_id}/{variant}` returns WebP under its own rate
  limit bucket (`DISCOVERY_PHOTO_POLICY`, 600 a minute). Without a signature it serves only photos
  of a listed business. The dashboard's preview links are signed (`t`, `exp`, `sig`) with an HMAC
  under the `photo_link` purpose key. Each link names one photo and tenant and expires after an
  hour, so an owner can preview a storefront before it is listed. The discovery card carries
  `cover_url`, and the storefront carries `photos`, with the cover first.

## Consequences

- One service fewer to run, patch and back up. Photos are backed up with `MEDIA_ROOT`, not with
  Postgres.
- Upload bandwidth and CPU now go through the API. Pillow is a backend dependency.
- **Local storage does not scale beyond one host.** A multi-host deployment adds an S3-compatible
  adapter that implements the same `ImageStore` Protocol. Nothing that stores or serves a photo
  changes.
- Logos and provider portraits are not modelled. They would be new `kind`s or a new table, not a
  revival of `media_assets`.
- Threat-model findings about the `media` module (docs/14) describe code that no longer exists.

## Alternatives considered

- **Keep Nextcloud and wire covers to `media_assets`.** Rejected. It keeps a second server and a
  direct-to-storage upload path for a job that needs one cover and twelve gallery images.
- **Store the uploaded bytes unchanged.** Rejected. That would serve unverified content from the
  platform's origin, and leak the EXIF location in every phone photo.
