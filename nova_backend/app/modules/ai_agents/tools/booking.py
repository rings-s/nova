"""ai_agents · tools — finding and holding a time, shared by the receptionist
and the marketplace assistant, which books the same way at a listing's tenant.
"""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.exceptions import NotFoundError

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices

from app.modules.ai_agents.tools.base import (
    _MAX_TIMES,
    _MIN_LEAD_MINUTES,
    Result,
    ToolkitBase,
    _fold,
    _local,
    _same_instant,
    _TimeNotFree,
)


class SlotTools(ToolkitBase):
    async def _branches(
        self, services: "TenantServices", business_id: UUID | None = None
    ) -> list[Any]:
        """A business's branches: the one named, the storefront's, or this tenant's."""
        business_id = business_id or self.deps.business_id
        if business_id is not None:
            business_ids = [business_id]
        else:
            business_ids = [b.id for b in await services.catalog.list_businesses(limit=5)]
        branches: list[Any] = []
        for business_id in business_ids:
            branches.extend(await services.catalog.list_locations(business_id))
        return branches

    async def _service_ref(
        self, services: "TenantServices", ref: str | UUID, business_id: UUID | None = None
    ) -> Any:
        """The business's service a model named, by id or by name.

        Live, qwen3-1.7b invented service ids. A name is what the customer said
        and what the model can repeat, so both resolve, and only among this
        business's own active services. An unknown one is refused with the list.
        """
        offered = [
            service
            for branch in await self._branches(services, business_id)
            for service in await services.catalog.list_services(branch.id)
            if service.is_active
        ]
        text = str(ref).strip()
        for service in offered:
            if str(service.id) == text:
                return service
        wanted = _fold(text)
        names = [(service, _fold(service.name_en), _fold(service.name_ar)) for service in offered]
        exact = [service for service, en, ar in names if wanted in (en, ar)]
        close = [
            service
            for service, en, ar in names
            if wanted and (wanted in en or wanted in ar or (en and en in wanted))
        ]
        if exact or close:
            return (exact or close)[0]
        listed = "; ".join(f"{self._name(s)} (service_id {s.id})" for s in offered[:12])
        raise NotFoundError(f"This business has no such service. It offers: {listed}.")

    async def _times_for_service(
        self,
        services: "TenantServices",
        service_id: UUID,
        days_ahead: int,
        limit: int | None = _MAX_TIMES,
    ) -> Result:
        """The booking service's free times for a service, across its providers."""
        service = await services.catalog.get_service(service_id)
        location = await services.catalog.get_location(service.location_id)
        now = datetime.now(UTC)
        slots = await services.booking.availability_for_service(
            service_id=service_id,
            date_from=now,
            date_to=now + timedelta(days=max(1, min(days_ahead, 14))),
            now=now,
            lead_time_minutes=_MIN_LEAD_MINUTES,
        )
        providers = {
            provider.id: provider
            for provider in await services.catalog.list_providers(service.location_id)
        }
        return {
            "service": self._name(service),
            "price": str(service.price),
            "currency": service.currency,
            "duration_minutes": service.duration_minutes,
            "available": len(slots),
            "timezone": location.timezone,
            "times": [
                {
                    "starts_at": slot.starts_at.isoformat(),
                    "local_time": _local(slot.starts_at, location.timezone),
                    "provider_id": str(slot.provider_id),
                    "provider": self._name(providers[slot.provider_id]),
                }
                for slot in slots[:limit]
            ],
        }

    async def _hold_details(self, services: "TenantServices", hold: Any) -> dict[str, str]:
        """Where and when a hold is, in words, for the model and for the reply."""
        location = await services.catalog.get_location(hold.location_id)
        business = self._name(await services.catalog.get_business(location.business_id))
        service = self._name(await services.catalog.get_service(hold.service_id))
        local_time = _local(hold.starts_at, location.timezone)
        return {
            "local_time": local_time,
            "business": business,
            "service": service,
            "label": f"{service} at {business}, {local_time}",
        }

    async def _free_provider(
        self,
        services: "TenantServices",
        service_id: UUID,
        starts_at: datetime,
        provider_id: UUID | None,
    ) -> UUID:
        """A qualified provider free at `starts_at`: the one named, if it is, else any.

        A small model names the wrong id (live: the service id as provider_id) or
        guesses a time. Rather than refuse the id, pick a provider who is free;
        rather than refuse the time bare, say which times are free.
        """
        found = await self._times_for_service(services, service_id, days_ahead=14, limit=None)
        free = [
            t
            for t in found["times"]
            if _same_instant(datetime.fromisoformat(t["starts_at"]), starts_at)
        ]
        if free:
            named = [t for t in free if t["provider_id"] == str(provider_id)]
            return UUID((named or free)[0]["provider_id"])
        upcoming = "; ".join(
            f"{t['local_time']} (starts_at {t['starts_at']})" for t in found["times"][:5]
        )
        raise _TimeNotFree(
            f"That time is not free. Free times: {upcoming}."
            if upcoming
            else "That time is not free, and nothing is free in the next two weeks."
        )
