"""Nextcloud WebDAV storage adapter.

Infrastructure only: WebDAV verbs, auth headers, and share-link creation. The
`media` module owns the domain and the path convention; this file owns the HTTP.

The important architectural point (docs/02 section 4, docs/09 #12-13): the
browser uploads *directly* to Nextcloud. Bytes never pass through FastAPI, so
a hundred salons uploading portfolios simultaneously costs the API server
nothing. What the API issues is a scoped, short-lived authorisation to write to
one exact path.

To verify against a live instance before go-live: whether this deployment
prefers per-user app passwords or OAuth, the share-link expiry policy, and the
per-tenant storage quota mechanism.
"""

import logging
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.integrations.base import IntegrationNotConfiguredError

logger = logging.getLogger(__name__)


class MediaStorage(Protocol):
    """Operations NOVA needs from Nextcloud."""

    def upload_url_for(self, *, webdav_path: str) -> str:
        """The absolute URL the browser should PUT to."""
        ...

    async def ensure_folder(self, *, folder_path: str) -> None: ...

    async def exists(self, *, webdav_path: str) -> bool: ...

    async def stat(self, *, webdav_path: str) -> dict[str, Any]: ...

    async def delete(self, *, webdav_path: str) -> None: ...

    async def create_share_link(self, *, webdav_path: str, expires_days: int = 7) -> str: ...


class NotConfiguredMediaStorage:
    """Placeholder used until Nextcloud credentials exist.

    Every other module stays developable without a storage account; anything
    that would actually touch a file fails loudly. `upload_url_for` is the one
    exception — it returns a path-shaped placeholder so the metadata flow can
    be exercised end to end in tests without a live server.
    """

    def upload_url_for(self, *, webdav_path: str) -> str:
        return f"nextcloud-not-configured:{webdav_path}"

    async def ensure_folder(self, *, folder_path: str) -> None:
        raise IntegrationNotConfiguredError("Nextcloud")

    async def exists(self, *, webdav_path: str) -> bool:
        raise IntegrationNotConfiguredError("Nextcloud")

    async def stat(self, *, webdav_path: str) -> dict[str, Any]:
        raise IntegrationNotConfiguredError("Nextcloud")

    async def delete(self, *, webdav_path: str) -> None:
        raise IntegrationNotConfiguredError("Nextcloud")

    async def create_share_link(self, *, webdav_path: str, expires_days: int = 7) -> str:
        raise IntegrationNotConfiguredError("Nextcloud")


class NextcloudStorage:
    """Live WebDAV adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        app_password: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.app_password = app_password
        self.timeout_seconds = timeout_seconds

    @property
    def _dav_root(self) -> str:
        return f"{self.base_url}/remote.php/dav/files/{quote(self.username)}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            auth=(self.username, self.app_password),
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    def upload_url_for(self, *, webdav_path: str) -> str:
        # `quote` with safe="/" keeps the path structure while escaping spaces
        # and anything else the filename sanitiser let through.
        return f"{self._dav_root}{quote(webdav_path, safe='/')}"

    async def ensure_folder(self, *, folder_path: str) -> None:
        """Creates the folder chain. MKCOL is not recursive, so walk it.

        A 405 means the collection already exists, which is success, not an
        error — this runs before every upload and folders are usually there.
        """
        segments = [s for s in folder_path.strip("/").split("/") if s]
        async with self._client() as client:
            accumulated = ""
            for segment in segments:
                accumulated = f"{accumulated}/{segment}"
                response = await client.request(
                    "MKCOL", f"{self._dav_root}{quote(accumulated, safe='/')}"
                )
                if response.status_code not in (201, 405):
                    response.raise_for_status()

    async def exists(self, *, webdav_path: str) -> bool:
        async with self._client() as client:
            response = await client.head(self.upload_url_for(webdav_path=webdav_path))
            return response.status_code == 200

    async def stat(self, *, webdav_path: str) -> dict[str, Any]:
        """Size and content type as Nextcloud sees them.

        Used to confirm what actually landed rather than trusting the client's
        claim about what it uploaded.
        """
        async with self._client() as client:
            response = await client.head(self.upload_url_for(webdav_path=webdav_path))
            response.raise_for_status()
            return {
                "size_bytes": int(response.headers.get("content-length", 0)),
                "content_type": response.headers.get("content-type"),
                "etag": response.headers.get("etag"),
            }

    async def delete(self, *, webdav_path: str) -> None:
        async with self._client() as client:
            response = await client.delete(self.upload_url_for(webdav_path=webdav_path))
            # 404 is the desired end state, not a failure.
            if response.status_code not in (204, 404):
                response.raise_for_status()

    async def create_share_link(self, *, webdav_path: str, expires_days: int = 7) -> str:
        """A public read-only link, via the OCS share API."""
        async with self._client() as client:
            response = await client.post(
                f"{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares",
                headers={"OCS-APIRequest": "true", "Accept": "application/json"},
                data={
                    "path": webdav_path,
                    # 3 = public link.
                    "shareType": 3,
                    # 1 = read only. A writable public link on a salon's
                    # portfolio folder would be an open upload endpoint.
                    "permissions": 1,
                },
            )
            response.raise_for_status()
            body = response.json()
            return body["ocs"]["data"]["url"]


def build_media_storage(
    *, base_url: str | None, username: str | None, app_password: str | None
) -> MediaStorage:
    if not (base_url and username and app_password):
        return NotConfiguredMediaStorage()
    return NextcloudStorage(base_url=base_url, username=username, app_password=app_password)
