"""media · DOMAIN layer — the rules.

Layer rule: stdlib, pydantic, and `app.core` values/exceptions only.
Must not import fastapi, sqlalchemy, or an HTTP client.

Pure-function style: a media asset has no lifecycle worth an entity class. It
is a record with field rules and one derived path, so validators and a path
builder are the whole domain (contrast `booking.domain`, which owns a real
state machine).

The rule this context exists to keep (docs/01, docs/07 section 9, docs/09 #13):
PostgreSQL stores metadata and a path. The binary NEVER passes through FastAPI —
the browser uploads straight to Nextcloud with a scoped URL, which is what keeps
the API server's memory flat regardless of how many salons upload portfolios.
"""

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.core.exceptions import ValidationDomainError


class MediaAssetKind(StrEnum):
    """docs/07 section 3."""

    LOGO = "logo"
    COVER = "cover"
    SERVICE_IMAGE = "service_image"
    PROVIDER_IMAGE = "provider_image"
    LOCATION_IMAGE = "location_image"
    PORTFOLIO = "portfolio"


#: Images only. A salon portfolio has no business accepting an executable, and
#: an allowlist is the only form of this check that stays correct as new
#: dangerous types appear.
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/avif",
        "image/gif",
        "application/pdf",
    }
)

_EXTENSION_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

#: Anything outside this is stripped from a filename. Path separators, "..",
#: control characters, and unicode direction marks all live outside it — a
#: filename is attacker-controlled text that becomes part of a storage path.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")

MAX_FILE_NAME_LENGTH = 120


class UnsupportedMediaTypeError(ValidationDomainError):
    code = "unsupported_media_type"

    def __init__(self, content_type: str) -> None:
        super().__init__(f"'{content_type}' is not an accepted media type.")


class MediaTooLargeError(ValidationDomainError):
    code = "media_too_large"

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"File is {size_bytes} bytes; the maximum is {max_bytes}.")


class MediaUploadUrlExpiredError(ValidationDomainError):
    code = "upload_url_expired"

    def __init__(self) -> None:
        super().__init__("This upload authorisation has expired. Request another.")


def validate_content_type(content_type: str) -> str:
    normalised = content_type.split(";")[0].strip().lower()
    if normalised not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedMediaTypeError(content_type)
    return normalised


def validate_size(size_bytes: int, *, max_bytes: int) -> int:
    if size_bytes <= 0:
        raise ValidationDomainError("File size must be greater than zero.")
    if size_bytes > max_bytes:
        raise MediaTooLargeError(size_bytes, max_bytes)
    return size_bytes


def sanitize_file_name(file_name: str, *, content_type: str) -> str:
    """Reduces a client-supplied filename to something safe to put in a path.

    Traversal is the obvious risk ("../../etc/passwd"), but the subtler one is
    a filename that *looks* fine and still breaks WebDAV — spaces, quotes,
    right-to-left override marks. Everything outside the allowlist becomes a
    hyphen, and an extension is restored from the declared content type so the
    stored object is still recognisable.
    """
    stem = file_name.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    cleaned = _UNSAFE_FILENAME_CHARS.sub("-", stem).strip("-.")

    if not cleaned:
        cleaned = "file"

    if "." not in cleaned:
        cleaned += _EXTENSION_BY_TYPE.get(content_type, "")

    if len(cleaned) > MAX_FILE_NAME_LENGTH:
        head, _, tail = cleaned.rpartition(".")
        keep = MAX_FILE_NAME_LENGTH - len(tail) - 1
        cleaned = f"{head[:keep]}.{tail}" if tail else cleaned[:MAX_FILE_NAME_LENGTH]

    return cleaned


def build_webdav_path(
    *,
    tenant_id: UUID,
    business_id: UUID,
    kind: MediaAssetKind,
    asset_id: UUID,
    file_name: str,
    root: str = "nova-media",
) -> str:
    """The Nextcloud path convention from docs/07 section 9 and docs/08 section 15.

        /nova-media/{tenant_id}/{business_id}/{kind}/{asset_id}/{file_name}

    Tenant id comes first deliberately: it makes a per-tenant Nextcloud ACL or
    quota a single directory rule, and it makes a path that has escaped its
    tenant obvious on sight. The asset id in the path means two files with the
    same name never collide.
    """
    return f"/{root.strip('/')}/{tenant_id}/{business_id}/{kind}/{asset_id}/{file_name}"


def assert_path_belongs_to_tenant(path: str, *, tenant_id: UUID, root: str = "nova-media") -> None:
    """Refuses a path that is not inside this tenant's folder.

    docs/07 section 9: "Business owners must not be able to access another
    tenant's media folder." The check is here rather than only at the query
    layer because a path can arrive from a webhook or a stored record, not just
    from a scoped repository.
    """
    expected_prefix = f"/{root.strip('/')}/{tenant_id}/"
    if not path.startswith(expected_prefix) or ".." in path:
        raise ValidationDomainError("That media path does not belong to this business.")


def sign_upload_authorisation(
    *,
    asset_id: UUID,
    tenant_id: UUID,
    webdav_path: str,
    expires_at: datetime,
    secret: str,
) -> str:
    """A short-lived token proving the server authorised this exact upload.

    Without it, `POST /media/{id}/complete` is an open invitation to mark
    arbitrary assets ready, or to point one at a path the server never issued.
    The signature covers the path, so a client cannot alter where its own file
    claims to live.
    """
    body = f"{asset_id}.{tenant_id}.{webdav_path}.{int(expires_at.timestamp())}"
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]


def verify_upload_authorisation(
    token: str,
    *,
    asset_id: UUID,
    tenant_id: UUID,
    webdav_path: str,
    expires_at: datetime,
    secret: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    if now >= expires_at:
        raise MediaUploadUrlExpiredError()

    expected = sign_upload_authorisation(
        asset_id=asset_id,
        tenant_id=tenant_id,
        webdav_path=webdav_path,
        expires_at=expires_at,
        secret=secret,
    )
    if not hmac.compare_digest(token, expected):
        raise ValidationDomainError("This upload authorisation is not valid.")


def upload_expiry(*, now: datetime, ttl_seconds: int) -> datetime:
    return now + timedelta(seconds=ttl_seconds)
