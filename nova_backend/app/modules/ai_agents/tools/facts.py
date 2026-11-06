"""What a customer-facing assistant knows about its business before it is asked.

Two things a small model got wrong live: it offered services nobody at the
business can perform (no qualified provider, or one with no working hours), and,
asked where the business is, it skipped the tool and gave the question back.
So every service is marked with whether it can actually be booked, and the
receptionist starts each turn with the business's branches and services in its
instructions: facts it can repeat without a tool call. Tools stay the way to
anything that changes (free times, the queue).

This is the retrieval step of the customer agents. Everything a customer asks
about a business and its records can answer is read here, from the catalog,
the providers' working hours and the booking and payment policies, in one
pass (`read_catalog`), and rendered twice: as text for the instructions
(`business_facts`) and as JSON for the marketplace's `get_business_details`.
A question none of it answers (parking, products, a provider's experience) has
no record behind it, and the instructions say so rather than let the model
guess. Every number it states lands in the turn's grounded values, so the
reply may repeat a price or an hour from here and nothing else.

Tenant-written prose (a business's or a service's description) reaches the
model trimmed to one short line, and not at all when it reads like
instructions (`guardrails.detect_injection`): the marketplace shows one
business's words to another's customers, with booking tools attached.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.modules.ai_agents.guardrails import detect_injection
from app.modules.ai_agents.tools.base import _ARABIC_WEEKDAYS, _shown

if TYPE_CHECKING:  # pragma: no cover
    from app.modules.ai_agents.service import TenantServices
    from app.modules.booking.domain import WorkingWindow


#: Longest description handed to the model: what a service includes, not a
#: brochure. Longer is prompt a small CPU model reads on every call of a turn.
MAX_DESCRIPTION = 160
#: Providers named per service. "Sara, Huda and 4 others" says enough.
MAX_PROVIDERS_NAMED = 3

#: The GCC week starts on Sunday. `WorkingWindow.weekday` is Monday = 0.
_WEEK_FROM_SUNDAY = (6, 0, 1, 2, 3, 4, 5)
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


async def bookable_service_ids(services: "TenantServices", location_id: UUID) -> set[UUID]:
    """The branch's services a customer can actually book: at least one active
    provider there performs it and has working hours."""
    staff = await _branch_staff(services, location_id)
    return {service_id for service_id, names in staff.performers.items() if names}


@dataclass(frozen=True)
class _BranchStaff:
    #: Service id -> the working providers who perform it, by name (both languages).
    performers: dict[UUID, list[Any]]
    #: Every working provider's windows, for the branch's opening hours.
    windows: list["WorkingWindow"]


async def _branch_staff(services: "TenantServices", location_id: UUID) -> _BranchStaff:
    working: dict[UUID, Any] = {}
    windows: list[WorkingWindow] = []
    for provider in await services.catalog.list_providers(location_id):
        if not provider.is_active:
            continue
        schedule = await services.booking.get_provider_schedule(provider.id)
        if schedule:
            working[provider.id] = provider
            windows.extend(schedule)
    performers: dict[UUID, list[Any]] = defaultdict(list)
    for pair in await services.catalog.list_assignments(location_id):
        if pair.provider_id in working:
            performers[pair.service_id].append(working[pair.provider_id])
    return _BranchStaff(performers=dict(performers), windows=windows)


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


def described(record: Any, locale: str) -> str | None:
    """A record's description in the app's language, as the model may see it:
    one line, at most `MAX_DESCRIPTION` characters, and None when it reads as
    instructions rather than a description."""
    text = record.description_ar if locale == "ar" else record.description_en
    if not text or detect_injection(text):
        return None
    return _shown(text, limit=MAX_DESCRIPTION)


def _clock(minute: int) -> str:
    # 24:00 is how a window that runs to midnight ends.
    return f"{minute // 60:02d}:{minute % 60:02d}"


def opening_hours(windows: "list[WorkingWindow]", locale: str) -> tuple[str, ...]:
    """When a branch is open, from its working providers' hours, a Sunday-first
    week with alike days run together: `Sun-Thu 09:00-13:00, 16:00-21:00`,
    `Fri closed`.

    The union of everyone's windows: the branch is open while anyone works.
    Schedule exceptions (a holiday, a day off) are not in it; free times are
    the tool's to say."""
    if not windows:
        # Nobody has hours yet: unknown, which is not the same as closed.
        return ()
    by_day: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for window in windows:
        by_day[window.weekday].append((window.start_minute, window.end_minute))
    spans_by_day: dict[int, str] = {}
    for weekday in _WEEK_FROM_SUNDAY:
        merged: list[list[int]] = []
        for start, end in sorted(by_day.get(weekday, [])):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        closed = "مغلق" if locale == "ar" else "closed"
        spans_by_day[weekday] = (
            ", ".join(f"{_clock(s)}-{_clock(e)}" for s, e in merged) if merged else closed
        )
    names = _ARABIC_WEEKDAYS if locale == "ar" else _WEEKDAYS
    lines: list[str] = []
    run: list[int] = []
    for day in (*_WEEK_FROM_SUNDAY, None):
        if run and (day is None or spans_by_day[day] != spans_by_day[run[0]]):
            days = names[run[0]] if len(run) == 1 else f"{names[run[0]]}-{names[run[-1]]}"
            lines.append(f"{days} {spans_by_day[run[0]]}")
            run = []
        if day is not None:
            run.append(day)
    return tuple(lines)


@dataclass(frozen=True)
class ServiceFacts:
    service_id: UUID
    name: str
    description: str | None
    duration_minutes: int
    price: Decimal
    currency: str
    #: False: nobody here performs it, or they have no hours. Never offered.
    bookable: bool
    #: Who performs it, by name, at most `MAX_PROVIDERS_NAMED`.
    providers: tuple[str, ...]
    #: Everyone else who performs it, not named.
    more_providers: int


@dataclass(frozen=True)
class BranchFacts:
    location_id: UUID
    name: str
    city: str | None
    map_url: str | None
    #: `opening_hours`, or empty when nobody there has working hours yet.
    hours: tuple[str, ...]
    services: tuple[ServiceFacts, ...]


@dataclass(frozen=True)
class CatalogSnapshot:
    """One business as its records describe it, in the app's language."""

    name: str
    description: str | None
    #: The average of verified ratings, to one decimal; None before the first.
    rating: Decimal | None
    rating_count: int
    branches: tuple[BranchFacts, ...]
    #: A customer may cancel free of charge until this long before the start.
    free_cancellation_hours: int
    #: The share of the price asked as a deposit when paying online; 0 is none.
    deposit_percent: int


async def read_catalog(
    services: "TenantServices", business_id: UUID, locale: str
) -> CatalogSnapshot:
    """The business, its branches and services, who performs what and when the
    branches open, and the booking policies: everything its records can tell a
    customer, read once."""
    business = await services.catalog.get_business(business_id)
    branches: list[BranchFacts] = []
    for branch in await services.catalog.list_locations(business_id):
        staff = await _branch_staff(services, branch.id)
        offered: list[ServiceFacts] = []
        for service in await services.catalog.list_services(branch.id):
            if not service.is_active:
                continue
            performers = [_named(p, locale) for p in staff.performers.get(service.id, [])]
            offered.append(
                ServiceFacts(
                    service_id=service.id,
                    name=_named(service, locale),
                    description=described(service, locale),
                    duration_minutes=service.duration_minutes,
                    price=service.price,
                    currency=service.currency,
                    bookable=bool(performers),
                    providers=tuple(performers[:MAX_PROVIDERS_NAMED]),
                    more_providers=max(0, len(performers) - MAX_PROVIDERS_NAMED),
                )
            )
        branches.append(
            BranchFacts(
                location_id=branch.id,
                name=_named(branch, locale),
                city=city_name(branch.city, locale),
                map_url=map_url(branch.latitude, branch.longitude),
                hours=opening_hours(staff.windows, locale),
                services=tuple(offered),
            )
        )
    rating = (
        (Decimal(business.rating_sum) / business.rating_count).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        if business.rating_count
        else None
    )
    return CatalogSnapshot(
        name=_named(business, locale),
        description=described(business, locale),
        rating=rating,
        rating_count=business.rating_count,
        branches=tuple(branches),
        free_cancellation_hours=services.booking.cancellation_policy.free_cancellation_hours,
        deposit_percent=services.payment.default_deposit_percent,
    )


def _cancellation_rule(hours: int) -> str:
    if hours <= 0:
        return "A customer may cancel free of charge any time before the appointment starts."
    return f"A customer may cancel free of charge up to {hours} hours before the appointment."


def _deposit_rule(percent: int) -> str:
    if percent <= 0:
        return "No deposit is asked when booking."
    return f"Paying online, a deposit of {percent}% of the price confirms the booking."


def snapshot_json(snapshot: CatalogSnapshot) -> dict[str, Any]:
    """The snapshot as a tool result, for the marketplace's `get_business_details`."""
    return {
        "name": snapshot.name,
        "description": snapshot.description,
        "rating": str(snapshot.rating) if snapshot.rating is not None else None,
        "rating_count": snapshot.rating_count,
        "branches": [
            {
                "location_id": str(branch.location_id),
                "name": branch.name,
                "city": branch.city,
                "map_url": branch.map_url,
                "opening_hours": list(branch.hours),
            }
            for branch in snapshot.branches
        ],
        "services": [
            {
                "service_id": str(service.service_id),
                "name": service.name,
                "location_id": str(branch.location_id),
                "description": service.description,
                "duration_minutes": service.duration_minutes,
                "price": str(service.price),
                "currency": service.currency,
                "bookable": service.bookable,
                "providers": list(service.providers),
            }
            for branch in snapshot.branches
            for service in branch.services
        ][:30],
        "cancellation": _cancellation_rule(snapshot.free_cancellation_hours),
        "deposit": _deposit_rule(snapshot.deposit_percent),
    }


@dataclass(frozen=True)
class BusinessFacts:
    #: For the instructions: branches and services, each service marked bookable or not.
    text: str
    #: One line per branch ("Olaya Branch, Riyadh: <map link>"), for a reply
    #: written without the model when it gave nothing back.
    branches: tuple[str, ...]


def _service_line(service: ServiceFacts) -> str:
    state = "bookable" if service.bookable else "not bookable right now"
    if service.providers:
        by = ", ".join(service.providers)
        if service.more_providers:
            by += f" and {service.more_providers} more"
        state += f"; by {by}"
    line = (
        f"  - {service.name}: {service.duration_minutes} min, "
        f"{service.currency} {service.price} ({state})"
    )
    return line + (f". {service.description}" if service.description else "")


def facts_text(snapshot: CatalogSnapshot) -> str:
    lines = [f"Facts about {snapshot.name}, from its records:"]
    if snapshot.description:
        lines.append(f"About: {snapshot.description}")
    if snapshot.rating is not None:
        lines.append(
            f"Rating: {snapshot.rating} out of 5 from {snapshot.rating_count} verified reviews."
        )
    lines.append("Branches:")
    for branch in snapshot.branches:
        where = ", ".join(
            part
            for part in (branch.city, f"map: {branch.map_url}" if branch.map_url else None)
            if part
        )
        lines.append(f"- {branch.name}" + (f" ({where})" if where else ""))
        lines.append(
            "  Opening hours: " + ("; ".join(branch.hours) if branch.hours else "not set yet")
        )
        lines.append("  Services:")
        lines.extend(_service_line(service) for service in branch.services)
    lines += [
        "Policies:",
        f"- {_cancellation_rule(snapshot.free_cancellation_hours)}",
        f"- {_deposit_rule(snapshot.deposit_percent)}",
        "Answer questions about where the business is, when it opens, what it offers, who "
        "performs it and its policies from these facts, in the words and numbers they give. "
        "Never offer a service marked not bookable; say it cannot be booked right now. "
        "If these facts and the tools do not say (parking, products, a provider's experience, a "
        "discount), say you do not have that information and offer to pass the question to the "
        "business with escalate_to_human. Never guess.",
    ]
    return "\n".join(lines)


async def business_facts(
    services: "TenantServices", business_id: UUID, locale: str
) -> BusinessFacts:
    """The business's branches and services, from its records."""
    snapshot = await read_catalog(services, business_id, locale)
    branch_lines = tuple(
        ", ".join(p for p in (branch.name, branch.city) if p)
        + (f": {branch.map_url}" if branch.map_url else "")
        for branch in snapshot.branches
    )
    return BusinessFacts(text=facts_text(snapshot), branches=branch_lines)
