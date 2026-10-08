"""ai_agents · tools — the marketplace assistant: listings by slug, times and
holds at the listing's tenant, and the walk-in queue.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.exceptions import DomainError, NotFoundError

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices
    from app.modules.discovery.service import DiscoveryService

from app.modules.ai_agents.tools.base import (
    _ASK_TO_CONFIRM,
    HeldSlot,
    QueuePlace,
    Result,
    _already_holding,
    _given,
    _held,
    _refuse,
    _shown,
)
from app.modules.ai_agents.tools.booking import SlotTools


class MarketplaceTools(SlotTools):
    async def search_businesses(
        self, query: str | None = None, city: str | None = None, category: str | None = None
    ) -> Result:
        """Listed businesses (salon, spa, massage, nails, barber…) by name, service, city
        or category, best rated first."""

        term, where, kind = _given(query), _given(city), _given(category)

        async def work(discovery: "DiscoveryService") -> Result:
            cards = await discovery.search(
                term=term, city=where, category=kind, sort="rating", limit=8
            )
            widened = False
            if not cards and (where or kind) and term:
                # A small model fills optional filters it was never told
                # ("city": "unknown"). Rather than report nothing, drop them.
                cards = await discovery.search(term=term, sort="rating", limit=8)
                widened = bool(cards)
            seen: set[str] = set()
            found = []
            for card in cards:
                business = card.business
                if business.slug in seen:
                    continue
                seen.add(business.slug)
                found.append(
                    {
                        "business_slug": business.slug,
                        "name": self._name(business),
                        "branch": self._name(card.location),
                        "city": _shown(card.location.city),
                        "rating_count": business.rating_count,
                    }
                )
            if not found:
                # Said outright: a small model otherwise repeats the same empty
                # search until its turn runs out.
                return {
                    "businesses": [],
                    "hint": "Nothing matched. Do not repeat this search. Try once with just a "
                    "service (spa, nails, haircut) or just the city, or ask the customer.",
                }
            if widened:
                return {
                    "businesses": found,
                    "note": "Nothing matched that city or category; these match anywhere.",
                }
            return {"businesses": found}

        return await self._call_discovery("search_businesses", work)

    async def get_business_details(self, business_slug: str) -> Result:
        """A listed business's branches and the services it sells, with prices."""

        async def work(discovery: "DiscoveryService") -> Result:
            storefront = await discovery.get_storefront(business_slug)
            return {
                "business_slug": storefront.business.slug,
                "name": self._name(storefront.business),
                "branches": [
                    {"location_id": str(loc.id), "name": self._name(loc), "city": _shown(loc.city)}
                    for loc in storefront.locations
                ],
                "services": [
                    {
                        "service_id": str(svc.id),
                        "name": self._name(svc),
                        "location_id": str(svc.location_id),
                        "duration_minutes": svc.duration_minutes,
                        "price": str(svc.price),
                        "currency": svc.currency,
                    }
                    for svc in storefront.services[:30]
                    if svc.is_active
                ],
            }

        return await self._call_discovery("get_business_details", work)

    async def _listing(self, business_slug: str) -> tuple[UUID, UUID]:
        """The tenant and business behind a listing, resolved by the server from the
        slug: only a live, listed business resolves."""
        discovery = self.deps.discovery
        if discovery is None:  # pragma: no cover
            raise NotFoundError("The marketplace is not available here.")
        async with discovery() as service:
            business = (await service.get_storefront(business_slug)).business
        return UUID(str(business.tenant_id)), UUID(str(business.id))

    async def find_times_at_business(
        self, business_slug: str, service_id: str, days_ahead: int = 7
    ) -> Result:
        """Free start times for one service at a listed business. service_id is the
        service's id, or its name ("Classic Manicure")."""
        try:
            tenant_id, business_id = await self._listing(business_slug)
        except DomainError as exc:
            code, message = exc.code, exc.message
            return await self._run("find_times_at_business", lambda: _refuse(code, message))

        async def work(services: "TenantServices") -> Result:
            service = await self._service_ref(services, service_id, business_id)
            return await self._times_for_service(services, service.id, days_ahead)

        return await self._call_in("find_times_at_business", self._tenant_scope(tenant_id), work)

    async def hold_slot_at_business(
        self,
        business_slug: str,
        service_id: str,
        starts_at: datetime,
        provider_id: UUID | None = None,
    ) -> Result:
        """Holds a free time at a listed business for the customer to confirm, once they
        asked to book it.

        Pass a starts_at that find_times_at_business returned. provider_id is optional.
        """
        if self.deps.artifacts.held_slots:
            # One hold per reply. Live, a small model held a time and then kept
            # holding others instead of answering; each refusal cost a minute.
            return await self._run("hold_slot_at_business", _already_holding)
        try:
            tenant_id, business_id = await self._listing(business_slug)
        except DomainError as exc:
            code, message = exc.code, exc.message
            return await self._run("hold_slot_at_business", lambda: _refuse(code, message))
        held: list[HeldSlot] = []

        async def work(services: "TenantServices") -> Result:
            service = await self._service_ref(services, service_id, business_id)
            chosen = await self._free_provider(services, service.id, starts_at, provider_id)
            hold = await services.booking.hold_slot(
                provider_id=chosen,
                service_id=service.id,
                starts_at=starts_at,
                principal=self.deps.principal,
                customer_id=self.deps.customer_id,
            )
            details = await self._hold_details(services, hold)
            held.append(
                _held(hold, tenant_id=tenant_id, slug=business_slug, label=details["label"])
            )
            return {
                "held": True,
                "starts_at": hold.starts_at.isoformat(),
                **{k: v for k, v in details.items() if k != "label"},
                "expires_at": hold.expires_at.isoformat(),
                "next_step": _ASK_TO_CONFIRM,
            }

        result = await self._call_in("hold_slot_at_business", self._tenant_scope(tenant_id), work)
        if "error" not in result:
            self.deps.artifacts.held_slots.extend(held)
        return result

    async def get_queue_length(self, queue_id: UUID) -> Result:
        """How many people are in a walk-in queue. Nobody's name, only the count."""

        async def work(services: "TenantServices") -> Result:
            entries = await services.queue.list_queue(queue_id)
            return {"queue_id": str(queue_id), "in_line": len(entries)}

        return await self._call("get_queue_length", work)

    async def join_queue(
        self,
        queue_id: UUID,
        service_id: UUID,
        provider_id: UUID | None = None,
        party_size: int = 1,
    ) -> Result:
        """Adds the caller to a walk-in queue, and says where they stand."""
        placed: list[QueuePlace] = []

        async def work(services: "TenantServices") -> Result:
            customer_id = self.deps.customer_id
            if customer_id is None:  # pragma: no cover - the router always resolves one
                raise NotFoundError("There is no customer to add to the queue.")
            position = await services.queue.join(
                queue_id=queue_id,
                customer_reference_id=customer_id,
                self_service=self.deps.self_service,
                service_id=service_id,
                provider_id=provider_id,
                party_size=max(1, min(party_size, 20)),
            )
            placed.append(
                QueuePlace(
                    entry_id=position.entry.id,
                    queue_id=queue_id,
                    place_in_line=position.place_in_line,
                    estimated_wait_minutes=position.estimated_wait_minutes,
                )
            )
            return {
                "entry_id": str(position.entry.id),
                "place_in_line": position.place_in_line,
                "estimated_wait_minutes": position.estimated_wait_minutes,
            }

        result = await self._call("join_queue", work)
        if "error" not in result:
            # Recorded only now that the unit of work has committed.
            self.deps.artifacts.queue_places.extend(placed)
        return result

    async def get_queue_position(self, entry_id: UUID) -> Result:
        """Where the caller's own queue entry stands, and the estimated wait."""

        async def work(services: "TenantServices") -> Result:
            await services.queue.assert_entry_visible_to(entry_id, self.deps.principal)
            position = await services.queue.position_of(entry_id)
            return {
                "entry_id": str(entry_id),
                "status": str(position.entry.status),
                "place_in_line": position.place_in_line,
                "estimated_wait_minutes": position.estimated_wait_minutes,
            }

        return await self._call("get_queue_position", work)
