"""media · PERSISTENCE layer — table shape.

Layer rule: sqlalchemy + `app.db` only. Must not import service or router.

Metadata only. There is deliberately no bytes column and never will be — the
binary lives in Nextcloud, and docs/09 #13 makes "FastAPI stores media
references only" an acceptance criterion.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.media.domain import MediaAssetKind


class MediaAssetRecord(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """A file in Nextcloud, described here, per docs/08 section 15."""

    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_assets_tenant_business", "tenant_id", "business_id"),
        Index("ix_media_assets_tenant_kind", "tenant_id", "kind"),
        CheckConstraint("size_bytes > 0", name="size_positive"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    kind: Mapped[MediaAssetKind] = mapped_column(
        Enum(MediaAssetKind, name="media_asset_kind", native_enum=False, length=32),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: Where the bytes actually are. The only pointer that matters.
    webdav_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: False until the browser confirms the upload landed. An asset that is not
    #: ready must never be rendered — a half-uploaded logo is a broken image on
    #: the storefront.
    is_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    upload_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
