"""What a customer-facing assistant knows about its business before it is asked.

Two things a small model got wrong live: it offered services nobody at the
business can perform (no qualified provider, or one with no working hours), and,
asked where the business is, it skipped the tool and gave the question back.
So every service is marked with whether it can actually be booked, and the
receptionist starts each turn with the business's branches and services in its
instructions: facts it can repeat without a tool call. Tools stay the way to
anything that changes (free times, the queue).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.modules.ai_agents.tools.base import _shown

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices


async def bookable_service_ids(services: "TenantServices", location_id: UUID) -> set[UUID]:
    """The branch's services a customer can actually book: at least one active
    provider there performs it and has working hours."""
    working = []
    for provider in await services.catalog.list_providers(location_id):
        if provider.is_active and await services.booking.get_provider_schedule(provider.id):
            working.append(provider.id)
    bookable: set[UUID] = set()
    for service in await services.catalog.list_services(location_id):
        if not service.is_active:
            continue
        for provider_id in working:
            if await services.catalog.is_provider_qualified(provider_id, service.id):
                bookable.add(service.id)
                break
    return bookable


def map_url(latitude: float | None, longitude: float | None) -> str | None:
    """A branch on OpenStreetMap (ADR-0012), the link the dashboard shows too;
    None for a branch never placed on the map."""
    if latitude is None or longitude is None:
        return None
    return (
        f"https://www.openstreetmap.org/?mlat={latitude:.6f}&mlon={longitude:.6f}"
        f"#map=17/{latitude:.6f}/{longitude:.6f}"
    )


#: Branch cities are free text, usually in English. For an Arabic reply the
#: model is given the Arabic name of the GCC cities NOVA serves (the same list
#: as the web app's `lib/map/cities.js`); live, it transliterated "Riyadh" as
#: "رعيده" when left to itself. A city not listed is passed through as written.
_ARABIC_CITY = {
    "riyadh": "الرياض",
    "jeddah": "جدة",
    "jiddah": "جدة",
    "makkah": "مكة المكرمة",
    "mecca": "مكة المكرمة",
    "madinah": "المدينة المنورة",
    "medina": "المدينة المنورة",
    "dammam": "الدمام",
    "al khobar": "الخبر",
    "khobar": "الخبر",
    "manama": "المنامة",
    "doha": "الدوحة",
    "kuwait city": "مدينة الكويت",
    "abu dhabi": "أبوظبي",
    "dubai": "دبي",
    "muscat": "مسقط",
}


def city_name(city: str | None, locale: str) -> str | None:
    shown = _shown(city)
    if not shown or locale != "ar":
        return shown
    return _ARABIC_CITY.get(" ".join(shown.casefold().split()), shown)


def _named(record: Any, locale: str) -> str:
    return _shown(record.name_ar if locale == "ar" else record.name_en) or ""


@dataclass(frozen=True)
class BusinessFacts:
    #: For the instructions: branches and services, each service marked bookable or not.
    text: str
    #: One line per branch ("Olaya Branch, Riyadh: <map link>"), for a reply
    #: written without the model when it gave nothing back.
    branches: tuple[str, ...]


async def business_facts(
    services: "TenantServices", business_id: UUID, locale: str
) -> BusinessFacts:
    """The business's branches and services, from its records."""
    business = await services.catalog.get_business(business_id)
    lines = [f"Facts about {_named(business, locale)}, from its records:", "Branches:"]
    branch_lines: list[str] = []
    for branch in await services.catalog.list_locations(business_id):
        link = map_url(branch.latitude, branch.longitude)
        city = city_name(branch.city, locale)
        where = ", ".join(part for part in (city, f"map: {link}" if link else None) if part)
        lines.append(f"- {_named(branch, locale)}" + (f" ({where})" if where else ""))
        branch_lines.append(
            ", ".join(p for p in (_named(branch, locale), city) if p)
            + (f": {link}" if link else "")
        )
        bookable = await bookable_service_ids(services, branch.id)
        for service in await services.catalog.list_services(branch.id):
            if not service.is_active:
                continue
            state = "bookable" if service.id in bookable else "not bookable right now"
            lines.append(
                f"  - {_named(service, locale)}: {service.duration_minutes} min, "
                f"{service.currency} {service.price} ({state})"
            )
    lines.append(
        "Answer questions about where the business is and what it offers from these facts. "
        "Never offer a service marked not bookable; say it cannot be booked right now."
    )
    return BusinessFacts(text="\n".join(lines), branches=tuple(branch_lines))
