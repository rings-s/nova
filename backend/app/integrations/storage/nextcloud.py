from typing import Protocol

from app.integrations.base import IntegrationNotConfiguredError


class MediaStorage(Protocol):
    """Operations NOVA needs from Nextcloud for business media uploads.

    FastAPI stores only media references (paths/URLs) in Postgres, never large
    binaries — this adapter owns the actual upload/retrieval.
    To verify: auth model (app password vs OAuth), share-link expiry, per-tenant
    storage quota. See docs/integrations/storage-nextcloud.md.
    """

    async def upload(self, *, path: str, content: bytes, content_type: str) -> str:
        """Uploads media and returns a reference (URL or internal path) to store."""
        ...

    async def get_url(self, *, reference: str) -> str: ...


class NotConfiguredMediaStorage:
    """Placeholder used until Nextcloud credentials/integration exist."""

    async def upload(self, *, path: str, content: bytes, content_type: str) -> str:
        raise IntegrationNotConfiguredError("Nextcloud")

    async def get_url(self, *, reference: str) -> str:
        raise IntegrationNotConfiguredError("Nextcloud")
