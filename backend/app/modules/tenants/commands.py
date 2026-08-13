from dataclasses import dataclass
from uuid import UUID

from app.modules.tenants.domain import (
    generate_slug,
    require_bilingual_text,
    validate_gcc_phone,
    validate_timezone,
)
from app.modules.tenants.exceptions import DuplicateSlugError
from app.modules.tenants.models import Branch, Tenant
from app.modules.tenants.repository import BranchRepository, TenantRepository


@dataclass(frozen=True)
class CreateTenantCommand:
    name_en: str
    name_ar: str
    phone: str
    default_currency: str = "SAR"


async def handle_create_tenant(
    command: CreateTenantCommand,
    *,
    repository: TenantRepository,
    allowed_phone_country_codes: list[str],
) -> Tenant:
    require_bilingual_text(command.name_en, command.name_ar)
    validate_gcc_phone(command.phone, allowed_phone_country_codes)
    slug = generate_slug(command.name_en)

    if await repository.get_by_slug(slug) is not None:
        raise DuplicateSlugError(slug)

    tenant = Tenant(
        name_en=command.name_en,
        name_ar=command.name_ar,
        slug=slug,
        phone=command.phone,
        default_currency=command.default_currency,
    )
    repository.add(tenant)
    await repository.session.flush()
    return tenant


@dataclass(frozen=True)
class CreateBranchCommand:
    tenant_id: UUID
    name_en: str
    name_ar: str
    phone: str
    timezone: str = "Asia/Riyadh"


async def handle_create_branch(
    command: CreateBranchCommand,
    *,
    repository: BranchRepository,
    allowed_phone_country_codes: list[str],
) -> Branch:
    require_bilingual_text(command.name_en, command.name_ar)
    validate_gcc_phone(command.phone, allowed_phone_country_codes)
    validate_timezone(command.timezone)
    slug = generate_slug(command.name_en)

    if await repository.get_by_slug(slug) is not None:
        raise DuplicateSlugError(slug)

    branch = Branch(
        tenant_id=command.tenant_id,
        name_en=command.name_en,
        name_ar=command.name_ar,
        slug=slug,
        phone=command.phone,
        timezone=command.timezone,
    )
    repository.add(branch)
    await repository.session.flush()
    return branch
