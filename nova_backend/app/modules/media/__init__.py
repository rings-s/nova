"""Bounded context: MEDIA — Nextcloud-backed asset metadata.

Aggregates      MediaAsset
Tables          media_assets
Depends on      identity, catalog
Status          implemented

Domain style: PURE FUNCTIONS. An asset record has no lifecycle worth an entity —
it is a set of field rules, a path convention, and a signature.

The rule that defines this context (docs/01, docs/07 section 9, docs/09 #12-13):
PostgreSQL stores metadata and a path. The binary NEVER passes through FastAPI.
The browser uploads straight to Nextcloud with a scoped, short-lived
authorisation, which is what keeps the API server's memory flat regardless of
how many salons upload portfolios. There is deliberately no endpoint here that
accepts a file body.

Path convention:
    /nova-media/{tenant_id}/{business_id}/{kind}/{asset_id}/{file_name}

Tenant id leads so a per-tenant ACL or quota is one directory rule, and so a
path that has escaped its tenant is obvious on sight. `assert_path_belongs_to_
tenant` enforces it on every read and write — a business must never be able to
reach another tenant's folder.

Public surface — what other modules may import:
    from app.modules.media.service import MediaService
    from app.modules.media.domain import MediaAssetKind
    from app.modules.media.events import MediaAssetReady

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Adapter: `app/integrations/storage/nextcloud.py`.
"""
