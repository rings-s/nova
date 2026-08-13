from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin


class Tenant(Base, UUIDPKMixin, TimestampMixin):
    """A business on NOVA (e.g. a salon or spa brand) — owns one or more branches."""

    __tablename__ = "tenants"

    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")

    branches: Mapped[list["Branch"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class Branch(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """A physical location belonging to a tenant."""

    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("tenant_id", "slug"),)

    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Riyadh")

    tenant: Mapped["Tenant"] = relationship(back_populates="branches")
