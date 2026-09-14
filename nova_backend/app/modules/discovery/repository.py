"""discovery · PERSISTENCE layer — referral queries.

Layer rule: models and `app.db` only. No fastapi, no service.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import TenantScopedRepository
from app.db.session import set_tenant_scope
from app.modules.discovery.models import MarketplaceReferral


class MarketplaceReferralRepository(TenantScopedRepository[MarketplaceReferral]):
    """Referrals for one tenant.

    Tenant-scoped like every other write in NOVA, even though the request that
    creates a referral arrives with no tenant. The trick is that it does not
    stay that way: by the time there is a row to write, the storefront lookup
    has already identified which business was clicked, and therefore which
    tenant owns the referral. `scoped_to` is where that transition happens.

    Keeping the write inside ordinary tenant isolation is what lets the
    `app.discovery_mode` RLS window stay `FOR SELECT` — the public path never
    needs permission to write across tenants, because by the time it writes it
    is no longer cross-tenant.
    """

    model = MarketplaceReferral

    @classmethod
    async def scoped_to(
        cls, session: AsyncSession, tenant_id: UUID
    ) -> "MarketplaceReferralRepository":
        """Binds the connection to `tenant_id`, then returns a repository for it.

        Called on the public discovery path once a storefront lookup has
        resolved which tenant a click belongs to. `SET LOCAL` semantics apply,
        so the binding ends with the transaction.
        """
        await set_tenant_scope(session, tenant_id)
        return cls(session, tenant_id)

    async def get_by_token_hash(self, token_hash: str) -> MarketplaceReferral | None:
        """The lookup every attributed booking makes.

        Scoped, so a referral for one salon cannot attribute a booking at
        another even if the token is genuine — the caller's tenant has to own
        it. `service.attributes_to_marketplace` checks the business too.
        """
        stmt = self._scope(self._base_select().where(MarketplaceReferral.token_hash == token_hash))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_live_for_business(
        self, business_id: UUID, *, now: datetime, limit: int = 20
    ) -> list[MarketplaceReferral]:
        """Unexpired referrals for one business — the billing audit trail."""
        stmt = (
            self._scope(
                self._base_select().where(
                    MarketplaceReferral.business_id == business_id,
                    MarketplaceReferral.expires_at > now,
                )
            )
            .order_by(MarketplaceReferral.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
