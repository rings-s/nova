"""Pure domain rules for the tenants module.

No SQLAlchemy or FastAPI imports here — these are plain functions over plain
values, independent of persistence and the web framework, per the project's
"domain rules independent from infra where practical" constraint.
"""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.exceptions import ValidationDomainError

_E164_PATTERN = re.compile(r"^\+(\d{1,3})(\d{6,12})$")
_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def validate_gcc_phone(phone: str, allowed_country_codes: list[str]) -> str:
    """Validates an E.164 phone number against the configured GCC country codes.

    Returns the phone number unchanged if valid. Raises ValidationDomainError
    otherwise. To verify: full list of GCC country codes NOVA should accept.
    """
    match = _E164_PATTERN.match(phone)
    if not match:
        raise ValidationDomainError(
            f"Phone number '{phone}' must be in E.164 format, e.g. +9665XXXXXXXX."
        )
    country_code = match.group(1)
    if country_code not in allowed_country_codes:
        raise ValidationDomainError(
            f"Phone country code '+{country_code}' is not a supported GCC code."
        )
    return phone


def validate_timezone(timezone: str) -> str:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValidationDomainError(f"Unknown timezone '{timezone}'.") from exc
    return timezone


def require_bilingual_text(name_en: str, name_ar: str, *, field: str = "name") -> None:
    """Arabic and English are both mandatory identity fields for a GCC product."""
    if not name_en.strip():
        raise ValidationDomainError(f"{field}_en is required.")
    if not name_ar.strip():
        raise ValidationDomainError(f"{field}_ar is required.")


def generate_slug(text: str) -> str:
    slug = _SLUG_INVALID_CHARS.sub("-", text.strip().lower()).strip("-")
    if not slug:
        raise ValidationDomainError(f"Could not derive a slug from '{text}'.")
    return slug
