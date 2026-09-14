import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantOwnedMixin, TimestampMixin, UUIDPKMixin
from app.modules.identity.domain import MembershipRole


class Tenant(Base, UUIDPKMixin, TimestampMixin):
    """A business on NOVA (e.g. a salon or spa brand).

    The tenant is the isolation boundary for every other module — see
    `TenantOwnedMixin` and `TenantScopedRepository`, and ADR-0003 for the
    strategy and its known gap.

    Physical branches live in the `catalog` module as `Location`, not here:
    identity owns *who* the business is, catalog owns *where and what* it sells.
    """

    __tablename__ = "tenants"

    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")


class User(Base, UUIDPKMixin, TimestampMixin):
    """A person who can sign in.

    Distinct from a *customer*: a customer is someone a salon books, and does
    not necessarily have credentials. A user is an account.
    """

    __tablename__ = "users"
    __table_args__ = (
        # Case-insensitive uniqueness: Alice@x.com and alice@x.com are one
        # account. Declared here as well as in the migration so autogenerate
        # does not propose dropping it on every run.
        Index("uq_users_email_lower", text("lower(email)"), unique=True),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    #: Never the password. See app/core/passwords.py.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Throttles credential stuffing per-account, independent of the IP-based
    # rate limiter (which an attacker can spread across many addresses).
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Bumping this invalidates every token already issued to the user —
    # the revocation mechanism for stateless JWTs (logout-everywhere, password
    # change, suspected compromise).
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Membership(Base, UUIDPKMixin, TimestampMixin):
    """Links a user to a tenant with a role.

    This table is the source of truth behind `Principal.tenant_ids`. A user
    with no active membership for a tenant cannot touch its data, regardless
    of what a token claims — tokens are minted from these rows.
    """

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_memberships_user_tenant"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MembershipRole] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="memberships")


class Customer(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin, SoftDeleteMixin):
    """A person a salon books, per docs/08 section 9.

    Why identity and not a module of its own: docs/06 lists `Customer` as a core
    aggregate but never places it, and this context already owns the User/customer
    distinction (see `User` above). A customer is *who someone is*, which is this
    context's question; catalog answers "what is sold" and booking "when".

    Tenant-scoped on purpose. The same phone number at two different salons is two
    customer records with two separate consent states — one salon must not inherit
    a marketing opt-in the person gave to another. That is also why `phone` is
    unique per tenant rather than globally.

    `user_id` links the record to a sign-in account when the customer booked
    themselves through the PWA. It is null for walk-ins reception typed in, who
    have no credentials and never will.
    """

    __tablename__ = "customers"
    __table_args__ = (
        # docs/08 section 9: phone is the identity key within a tenant.
        # Partial on is_deleted so retiring a record frees the number for
        # re-registration instead of blocking it forever.
        Index(
            "uq_customers_tenant_phone",
            "tenant_id",
            "phone",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_customers_tenant_user", "tenant_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, default="ar")

    # PDPL: consent is per-channel and defaults to withheld. `notification`
    # refuses to send without the matching flag — never assume opt-in.
    marketing_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    whatsapp_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
