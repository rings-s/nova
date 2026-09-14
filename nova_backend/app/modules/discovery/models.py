"""discovery · PERSISTENCE layer — the marketplace referral table.

Layer rule: sqlalchemy and `app.db` only. No fastapi, no service, no domain.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantOwnedMixin, TimestampMixin, UUIDPKMixin


class MarketplaceReferral(Base, UUIDPKMixin, TimestampMixin, TenantOwnedMixin):
    """Evidence that NOVA sent a customer to a business.

    This is the record ADR-0008 said had to exist before any booking could
    honestly be called `MARKETPLACE`:

        "It has to be derived server-side from a marketplace attribution
        record — the 30-day click window in docs/11 section 3 rule 4 — and that
        needs the public discovery surface, which does not exist."

    It is a row rather than a signed token because its second job is to settle
    arguments. A commission line is money taken from a salon, and "our server
    signed something" is a weaker answer to a disputed invoice than a timestamped
    click with the storefront it landed on. Only NOVA can mint one either way;
    only the row can be shown afterwards.

    `tenant_id` is carried even though the row is created on a request with no
    tenant, because it is what lets booking read its own referrals back under
    ordinary RLS instead of needing another cross-tenant window.
    """

    __tablename__ = "marketplace_referrals"
    __table_args__ = (
        # The booking path looks a referral up by token and nothing else, on
        # every create that carries one. Unique rather than merely indexed:
        # two rows sharing a hash would make attribution ambiguous, and the
        # constraint is also what makes a token collision a database error
        # rather than a silent mis-attribution.
        Index("uq_marketplace_referrals_token_hash", "token_hash", unique=True),
        # Sweeping expired rows is the only other query this table serves.
        Index("ix_marketplace_referrals_expires_at", "expires_at"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    #: SHA-256 of the token handed to the customer. The token itself is never
    #: stored — see `domain.hash_referral_token`.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    #: When the click stops attributing. Stored rather than derived from
    #: `created_at` so that changing `REFERRAL_WINDOW_DAYS` later re-prices
    #: future clicks only, and never retroactively bills a salon for a booking
    #: whose referral had already expired under the old window.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Set when a booking is actually attributed to this referral, so the row
    #: reads as the audit trail it is: which booking, and when it claimed it.
    #: Null means the customer looked and did not book.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
