import pytest

from app.core.exceptions import ValidationDomainError
from app.modules.tenants.domain import (
    generate_slug,
    require_bilingual_text,
    validate_gcc_phone,
    validate_timezone,
)

ALLOWED_CODES = ["966", "971"]


def test_validate_gcc_phone_accepts_valid_number() -> None:
    assert validate_gcc_phone("+966500000000", ALLOWED_CODES) == "+966500000000"


def test_validate_gcc_phone_rejects_unsupported_country_code() -> None:
    with pytest.raises(ValidationDomainError):
        validate_gcc_phone("+15550000000", ALLOWED_CODES)


def test_validate_gcc_phone_rejects_malformed_number() -> None:
    with pytest.raises(ValidationDomainError):
        validate_gcc_phone("0500000000", ALLOWED_CODES)


def test_validate_timezone_accepts_known_zone() -> None:
    assert validate_timezone("Asia/Riyadh") == "Asia/Riyadh"


def test_validate_timezone_rejects_unknown_zone() -> None:
    with pytest.raises(ValidationDomainError):
        validate_timezone("Not/AZone")


def test_require_bilingual_text_accepts_both_present() -> None:
    require_bilingual_text("Salon", "صالون")


def test_require_bilingual_text_rejects_missing_arabic() -> None:
    with pytest.raises(ValidationDomainError):
        require_bilingual_text("Salon", "   ")


def test_generate_slug_normalizes_text() -> None:
    assert generate_slug("Nova Beauty Center!") == "nova-beauty-center"
